# Copyright 2026  Admin AI Team, All rights reserved.
"""组织架构上游同步（评审 B-2 / 设计 §3）。

原则：部门与汇报线以 **HR 系统为权威源**（D-3 决策），本系统只做同步与缓存，
不在本地重复维护（避免两套真相）。上游没有接口时退化为 CSV 导入，仍保留 `external_id`
以便将来对接。

失败语义（设计 §3.2 / T-8）：同步失败**沿用上次快照**并告警，绝不清空组织数据；
连续失败达到阈值时升级告警。

拆分为「纯计划」+「落库」两层：`plan_org_sync` 不触碰数据库，便于脱离 PG 测试。
"""

from __future__ import annotations

import csv
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.db.models import DepartmentModel, UserModel, generate_uuid
from app.admin_ai.services.notification_service import notify_admins

logger = structlog.get_logger(__name__)

# 连续失败达到该次数时升级告警（设计 §3.2）
FAILURE_ESCALATION_THRESHOLD = 3
FAILURE_STREAK_KEY = "org:sync:fail_streak"

CSV_DEPARTMENTS_FILE = "departments.csv"
CSV_EMPLOYEES_FILE = "employees.csv"


class OrgSyncError(Exception):
    """组织数据获取失败（网络/文件/格式）；调用方应沿用旧快照并告警。"""


@dataclass(frozen=True)
class DepartmentRecord:
    """上游部门记录。"""
    external_id: str
    name: str
    parent_external_id: str | None = None
    manager_employee_id: str | None = None


@dataclass(frozen=True)
class EmployeeRecord:
    """上游员工记录。"""
    employee_id: str
    name: str | None = None
    department_external_id: str | None = None
    is_active: bool = True


@dataclass(frozen=True)
class ExistingDepartment:
    """本地部门现状（同步计划输入）。"""
    id: str
    external_id: str | None
    name: str
    path: str
    level: int
    parent_id: str | None = None
    manager_id: str | None = None
    is_active: bool = True


@dataclass(frozen=True)
class ResolvedDepartment:
    """解析后的部门（含物化路径与层级）。"""
    external_id: str
    name: str
    parent_external_id: str | None
    manager_id: str | None
    path: str
    level: int


@dataclass(frozen=True)
class SyncPlan:
    """同步计划：新建/更新/软删的部门，以及员工调动。"""
    departments_to_create: tuple[ResolvedDepartment, ...] = ()
    departments_to_update: tuple[tuple[str, ResolvedDepartment], ...] = ()
    departments_to_deactivate: tuple[str, ...] = ()
    employees_to_update: tuple[tuple[str, EmployeeRecord], ...] = ()
    employees_unmatched: tuple[str, ...] = ()
    local_id_by_external: Mapping[str, str] = field(default_factory=dict)


@dataclass
class SyncSummary:
    """同步结果摘要（写入日志与审计，不记录个人身份信息）。"""
    provider: str
    ok: bool = True
    departments_created: int = 0
    departments_updated: int = 0
    departments_deactivated: int = 0
    employees_updated: int = 0
    employees_unmatched: int = 0
    error: str | None = None
    escalated: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "ok": self.ok,
            "departments_created": self.departments_created,
            "departments_updated": self.departments_updated,
            "departments_deactivated": self.departments_deactivated,
            "employees_updated": self.employees_updated,
            "employees_unmatched": self.employees_unmatched,
            "escalated": self.escalated,
        }


# ---------------------------------------------------------------- 数据获取

def _truthy(value: str | None, default: bool = True) -> bool:
    """解析 CSV 里的布尔列。"""
    if value is None or value.strip() == "":
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "是"}


def parse_departments_csv(text: str) -> list[DepartmentRecord]:
    """解析部门 CSV：`external_id,name,parent_external_id,manager_employee_id`。"""
    records: list[DepartmentRecord] = []
    for row in csv.DictReader(io.StringIO(text)):
        external_id = (row.get("external_id") or "").strip()
        name = (row.get("name") or "").strip()
        if not external_id or not name:
            continue
        records.append(
            DepartmentRecord(
                external_id=external_id,
                name=name,
                parent_external_id=(row.get("parent_external_id") or "").strip() or None,
                manager_employee_id=(row.get("manager_employee_id") or "").strip() or None,
            )
        )
    return records


def parse_employees_csv(text: str) -> list[EmployeeRecord]:
    """解析员工 CSV：`employee_id,name,department_external_id,is_active`。"""
    records: list[EmployeeRecord] = []
    for row in csv.DictReader(io.StringIO(text)):
        employee_id = (row.get("employee_id") or "").strip()
        if not employee_id:
            continue
        records.append(
            EmployeeRecord(
                employee_id=employee_id,
                name=(row.get("name") or "").strip() or None,
                department_external_id=(row.get("department_external_id") or "").strip() or None,
                is_active=_truthy(row.get("is_active")),
            )
        )
    return records


def load_csv_records(directory: str | Path) -> tuple[list[DepartmentRecord], list[EmployeeRecord]]:
    """从目录读取部门与员工 CSV；缺目录/缺文件一律抛 OrgSyncError。"""
    path = Path(directory)
    if not path.is_dir():
        raise OrgSyncError(f"组织数据目录不存在：{path}")
    departments_file = path / CSV_DEPARTMENTS_FILE
    employees_file = path / CSV_EMPLOYEES_FILE
    if not departments_file.is_file():
        raise OrgSyncError(f"缺少部门文件：{departments_file}")
    if not employees_file.is_file():
        raise OrgSyncError(f"缺少员工文件：{employees_file}")
    try:
        departments = parse_departments_csv(departments_file.read_text(encoding="utf-8-sig"))
        employees = parse_employees_csv(employees_file.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, csv.Error) as exc:
        raise OrgSyncError(f"组织数据解析失败：{exc}") from exc
    return departments, employees


async def fetch_http_records(
    base_url: str, *, token: str = "", timeout: float = 10.0
) -> tuple[list[DepartmentRecord], list[EmployeeRecord]]:
    """从 HR 系统的组织接口拉取数据（设计 §3.3 的 /internal/org/* 约定）。"""
    import httpx

    if not base_url:
        raise OrgSyncError("未配置 HR 组织接口地址（HR_ORG_BASE_URL）")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    try:
        async with httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout, headers=headers
        ) as client:
            department_resp = await client.get("/internal/org/departments")
            employee_resp = await client.get("/internal/org/employees")
            department_resp.raise_for_status()
            employee_resp.raise_for_status()
            department_payload = department_resp.json()
            employee_payload = employee_resp.json()
    except Exception as exc:  # noqa: BLE001 - 统一转 OrgSyncError 由调用方降级
        raise OrgSyncError(f"HR 组织接口调用失败：{exc}") from exc

    departments = [
        DepartmentRecord(
            external_id=str(item.get("external_id") or ""),
            name=str(item.get("name") or ""),
            parent_external_id=item.get("parent_external_id") or None,
            manager_employee_id=item.get("manager_employee_id") or None,
        )
        for item in department_payload
        if item.get("external_id") and item.get("name")
    ]
    employees = [
        EmployeeRecord(
            employee_id=str(item.get("employee_id") or ""),
            name=item.get("name") or None,
            department_external_id=item.get("department_external_id") or None,
            is_active=bool(item.get("is_active", True)),
        )
        for item in employee_payload
        if item.get("employee_id")
    ]
    return departments, employees


# ---------------------------------------------------------------- 纯计划

def plan_org_sync(
    *,
    departments: Sequence[DepartmentRecord],
    employees: Sequence[EmployeeRecord],
    existing_departments: Sequence[ExistingDepartment],
    user_ids_by_employee_id: Mapping[str, str],
) -> SyncPlan:
    """计算同步计划（纯函数）。

    - 部门按上游 `external_id` 幂等 upsert，物化路径与层级由上游父子关系重算；
    - 上游不再返回的部门 → 软删（`is_active=false`）；
    - **无 `external_id` 的本地部门不动**（手工维护或开发种子的数据不受同步影响）；
    - 本地查无此人的员工记录只计数不建号（避免同步出无角色、无权限的空用户）。
    """
    by_external = {d.external_id: d for d in existing_departments if d.external_id}
    resolved = _resolve_departments(departments, by_external, user_ids_by_employee_id)

    create: list[ResolvedDepartment] = []
    update: list[tuple[str, ResolvedDepartment]] = []
    for resolved_department in resolved.values():
        existing = by_external.get(resolved_department.external_id)
        if existing is None:
            create.append(resolved_department)
        elif _department_changed(existing, resolved_department):
            update.append((existing.id, resolved_department))

    deactivate = tuple(
        existing.id
        for external_id, existing in by_external.items()
        if external_id not in resolved and existing.is_active
    )

    local_id_by_external = {
        external_id: existing.id for external_id, existing in by_external.items()
    }
    local_id_by_external.update(
        {d.external_id: "" for d in create}  # 新建部门 ID 由落库时分配
    )

    employees_to_update: list[tuple[str, EmployeeRecord]] = []
    employees_unmatched: list[str] = []
    for record in employees:
        user_id = user_ids_by_employee_id.get(record.employee_id)
        if user_id is None:
            employees_unmatched.append(record.employee_id)
            continue
        employees_to_update.append((user_id, record))

    return SyncPlan(
        departments_to_create=tuple(create),
        departments_to_update=tuple(update),
        departments_to_deactivate=deactivate,
        employees_to_update=tuple(employees_to_update),
        employees_unmatched=tuple(employees_unmatched),
        local_id_by_external=local_id_by_external,
    )


def _resolve_departments(
    departments: Sequence[DepartmentRecord],
    by_external: Mapping[str, ExistingDepartment],
    user_ids_by_employee_id: Mapping[str, str],
) -> dict[str, ResolvedDepartment]:
    """自顶向下解析部门路径与层级；父节点缺失或成环时挂到根（不抛异常）。"""
    pending = {record.external_id: record for record in departments}
    resolved: dict[str, ResolvedDepartment] = {}

    while pending:
        progressed = False
        for external_id, record in list(pending.items()):
            parent_path: str | None = None
            parent_level = 0
            parent_external_id = record.parent_external_id
            if parent_external_id:
                if parent_external_id in resolved:
                    parent_path = resolved[parent_external_id].path
                    parent_level = resolved[parent_external_id].level
                elif parent_external_id in by_external:
                    parent_path = by_external[parent_external_id].path
                    parent_level = by_external[parent_external_id].level
                else:
                    continue  # 父节点尚未解析（或上游/本地都没有）→ 下一轮再试
            resolved[external_id] = ResolvedDepartment(
                external_id=external_id,
                name=record.name,
                parent_external_id=parent_external_id,
                manager_id=(
                    user_ids_by_employee_id.get(record.manager_employee_id)
                    if record.manager_employee_id
                    else None
                ),
                path=f"{parent_path}/{record.name}" if parent_path else f"/{record.name}",
                level=parent_level + 1 if parent_path else 1,
            )
            del pending[external_id]
            progressed = True
        if not progressed:
            # 剩余节点父级缺失或成环：挂到根并告警，避免同步整体失败
            for external_id, record in pending.items():
                resolved[external_id] = ResolvedDepartment(
                    external_id=external_id,
                    name=record.name,
                    parent_external_id=None,
                    manager_id=(
                        user_ids_by_employee_id.get(record.manager_employee_id)
                        if record.manager_employee_id
                        else None
                    ),
                    path=f"/{record.name}",
                    level=1,
                )
            if pending:
                logger.warning(
                    "上游部门层级异常，已挂到根节点", count=len(pending)
                )
            break
    return resolved


def _department_changed(existing: ExistingDepartment, resolved: ResolvedDepartment) -> bool:
    """部门是否需要落库更新。"""
    return any(
        [
            existing.name != resolved.name,
            existing.path != resolved.path,
            existing.level != resolved.level,
            existing.manager_id != resolved.manager_id,
            not existing.is_active,  # 上游重新出现的部门需要复活
        ]
    )


# ---------------------------------------------------------------- 落库

async def sync_org(
    db: AsyncSession,
    *,
    provider: str = "csv",
    csv_dir: str | Path = "data/org",
    base_url: str = "",
    token: str = "",
    timeout: float = 10.0,
) -> SyncSummary:
    """执行一次组织同步。任何失败都返回 `ok=False` 且不修改数据库。"""
    try:
        departments, employees = await _fetch_records(
            provider, csv_dir=csv_dir, base_url=base_url, token=token, timeout=timeout
        )
    except OrgSyncError as exc:
        return await _handle_failure(db, provider=provider, error=str(exc))
    except Exception as exc:  # noqa: BLE001 - 同步失败不得影响业务，统一降级
        return await _handle_failure(db, provider=provider, error=f"{type(exc).__name__}: {exc}")

    department_models = (await db.execute(select(DepartmentModel))).scalars().all()
    user_models = (
        await db.execute(select(UserModel).where(UserModel.is_deleted == False))  # noqa: E712
    ).scalars().all()

    plan = plan_org_sync(
        departments=departments,
        employees=employees,
        existing_departments=[_existing_from_model(m) for m in department_models],
        user_ids_by_employee_id={m.employee_id: m.id for m in user_models},
    )
    summary = _apply_plan(db, plan, department_models, user_models)
    summary.provider = provider
    await db.commit()

    await _clear_failure_streak()
    logger.info("组织同步完成", **summary.as_dict())
    return summary


async def _fetch_records(
    provider: str, *, csv_dir: str | Path, base_url: str, token: str, timeout: float
):
    """按 provider 取上游记录。"""
    if provider == "csv":
        return load_csv_records(csv_dir)
    if provider == "http":
        return await fetch_http_records(base_url, token=token, timeout=timeout)
    if provider == "disabled":
        raise OrgSyncError("组织同步已关闭（ORG_SYNC_PROVIDER=disabled）")
    raise OrgSyncError(f"未知的 provider: {provider}（支持 csv / http / disabled）")


def _existing_from_model(model: DepartmentModel) -> ExistingDepartment:
    return ExistingDepartment(
        id=model.id,
        external_id=model.external_id,
        name=model.name,
        path=model.path,
        level=model.level or 1,
        parent_id=model.parent_id,
        manager_id=model.manager_id,
        is_active=bool(model.is_active),
    )


def _apply_plan(
    db: AsyncSession,
    plan: SyncPlan,
    department_models: Sequence[DepartmentModel],
    user_models: Sequence[UserModel],
) -> SyncSummary:
    """把计划落到 ORM 对象上（调用方负责 commit）。"""
    summary = SyncSummary(provider="")
    department_by_id = {m.id: m for m in department_models}
    id_by_external = dict(plan.local_id_by_external)

    # 新建：按层级升序，保证父节点先建立
    for resolved in sorted(plan.departments_to_create, key=lambda d: (d.level, d.path)):
        parent_id = (
            id_by_external.get(resolved.parent_external_id) if resolved.parent_external_id else None
        )
        department = DepartmentModel(
            id=generate_uuid(),
            name=resolved.name,
            parent_id=parent_id or None,
            path=resolved.path,
            level=resolved.level,
            manager_id=resolved.manager_id,
            external_id=resolved.external_id,
        )
        db.add(department)
        id_by_external[resolved.external_id] = department.id
        summary.departments_created += 1

    for department_id, resolved in plan.departments_to_update:
        department = department_by_id.get(department_id)
        if department is None:
            continue
        department.name = resolved.name
        department.parent_id = (
            id_by_external.get(resolved.parent_external_id) if resolved.parent_external_id else None
        )
        department.path = resolved.path
        department.level = resolved.level
        department.manager_id = resolved.manager_id
        department.is_active = True
        summary.departments_updated += 1

    for department_id in plan.departments_to_deactivate:
        department = department_by_id.get(department_id)
        if department is None:
            continue
        department.is_active = False  # 软删：历史审批记录仍需可追溯
        summary.departments_deactivated += 1

    user_by_id = {m.id: m for m in user_models}
    for user_id, record in plan.employees_to_update:
        user = user_by_id.get(user_id)
        if user is None:
            continue
        if record.name:
            user.name = record.name
        user.is_active = record.is_active
        if record.department_external_id:
            department_id = id_by_external.get(record.department_external_id)
            if department_id:
                user.department_id = department_id
                # 兼容期双写旧列（设计 §2.2），Contract 阶段移除
                user.department = _department_name(record.department_external_id, plan)
        summary.employees_updated += 1

    summary.employees_unmatched = len(plan.employees_unmatched)
    return summary


def _department_name(external_id: str, plan: SyncPlan) -> str | None:
    """新建/更新的部门名（用于兼容期双写 `users.department`）。"""
    for resolved in plan.departments_to_create:
        if resolved.external_id == external_id:
            return resolved.name
    for _, resolved in plan.departments_to_update:
        if resolved.external_id == external_id:
            return resolved.name
    return None


# ---------------------------------------------------------------- 失败处理

async def _handle_failure(db: AsyncSession, *, provider: str, error: str) -> SyncSummary:
    """同步失败：告警（含连续失败升级）并返回摘要；不修改任何组织数据。"""
    streak = await _bump_failure_streak()
    escalated = streak >= FAILURE_ESCALATION_THRESHOLD
    logger.warning("组织同步失败，沿用上次快照", provider=provider, error=error, streak=streak)
    await notify_admins(
        db,
        title="组织架构同步失败" + ("（已连续失败）" if escalated else ""),
        content=f"同步来源 {provider} 失败：{error}。系统继续使用上次成功的组织快照，请检查上游接口。",
    )
    return SyncSummary(provider=provider, ok=False, error=error, escalated=escalated)


async def _bump_failure_streak() -> int:
    """连续失败计数；Redis 不可用时降级为 1（不阻断告警）。"""
    try:
        from app.admin_ai.db.redis import get_redis

        client = await get_redis()
        streak = await client.incr(FAILURE_STREAK_KEY)
        await client.expire(FAILURE_STREAK_KEY, 7 * 24 * 3600)
        return int(streak)
    except Exception as exc:  # noqa: BLE001 - 计数器不可用不应影响同步本身
        logger.warning("组织同步失败计数不可用", error=str(exc))
        return 1


async def _clear_failure_streak() -> None:
    """同步成功后清零连续失败计数。"""
    try:
        from app.admin_ai.db.redis import get_redis

        client = await get_redis()
        await client.delete(FAILURE_STREAK_KEY)
    except Exception as exc:  # noqa: BLE001
        logger.warning("组织同步失败计数清理失败", error=str(exc))
