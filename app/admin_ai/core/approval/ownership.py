# Copyright 2026  Admin AI Team, All rights reserved.
"""数据归属与查询范围（SECURITY §4.3 / 设计 §5）。

落地「按角色 + 数据归属 + 范围判定权限」：查询类接口必须把归属条件**下推到 SQL**
（禁止先查全量再在内存过滤）；财务/HR/管理员可看全量，但每次访问写审计。

| scope  | 可见范围              | 谁可以                        |
|--------|-----------------------|-------------------------------|
| `my`   | 本人                  | 所有登录用户（默认）          |
| `dept` | 本部门及所有子部门    | 该部门主管                    |
| `all`  | 全量                  | admin / finance / hr（受审计）|
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import ColumnElement, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.api.response import BusinessError
from app.admin_ai.db.models import DepartmentModel, TaskModel, UserModel

# 可查看全量数据的角色（每次访问记审计）
FULL_SCOPE_ROLES = frozenset({"admin", "finance", "hr"})
VALID_SCOPES = ("my", "dept", "all")


@dataclass(frozen=True)
class OwnershipPlan:
    """一次查询的归属计划。"""
    scope: str
    condition: ColumnElement[bool] | None
    department_ids: tuple[str, ...] = ()
    audited: bool = False


async def managed_department_ids(db: AsyncSession, user_id: str) -> list[str]:
    """该用户担任主管的部门 ID。"""
    return list(
        (
            await db.execute(
                select(DepartmentModel.id).where(
                    DepartmentModel.manager_id == user_id,
                    DepartmentModel.is_active == True,  # noqa: E712
                )
            )
        ).scalars().all()
    )


async def subtree_department_ids(db: AsyncSession, department_ids: list[str]) -> list[str]:
    """部门及其所有子部门 ID（借助物化路径前缀匹配，无需递归 CTE）。"""
    if not department_ids:
        return []
    paths = (
        await db.execute(
            select(DepartmentModel.path).where(DepartmentModel.id.in_(department_ids))
        )
    ).scalars().all()
    if not paths:
        return []
    conditions = [
        DepartmentModel.path.like(f"{_escape_like(path)}%", escape="\\")
        for path in paths
        if path
    ]
    if not conditions:
        return []
    return list(
        (
            await db.execute(
                select(DepartmentModel.id).where(
                    or_(*conditions),
                    DepartmentModel.is_active == True,  # noqa: E712
                )
            )
        ).scalars().all()
    )


def _escape_like(value: str) -> str:
    """转义 LIKE 通配符，避免部门名中的 % / _ 改变匹配范围。"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def build_ownership_plan(
    db: AsyncSession, *, user_id: str, role: str, scope: str = "my"
) -> OwnershipPlan:
    """按请求范围构建归属计划；越权范围直接拒绝而不是降级放行。"""
    if scope not in VALID_SCOPES:
        raise BusinessError(code=40001, message=f"非法 scope: {scope}，仅支持 {VALID_SCOPES}")

    if scope == "my":
        return OwnershipPlan(scope="my", condition=TaskModel.user_id == user_id)

    if scope == "all":
        if role not in FULL_SCOPE_ROLES:
            raise BusinessError(code=40003, message="无权查看全量任务")
        return OwnershipPlan(scope="all", condition=None, audited=True)

    # scope == "dept"
    department_ids = await managed_department_ids(db, user_id)
    if not department_ids:
        raise BusinessError(code=40003, message="您不是任何部门的主管，无权按部门范围查询")
    department_ids = await subtree_department_ids(db, department_ids)
    if not department_ids:
        raise BusinessError(code=40004, message="所辖部门不存在或已停用")
    members = select(UserModel.id).where(UserModel.department_id.in_(department_ids))
    return OwnershipPlan(
        scope="dept",
        condition=TaskModel.user_id.in_(members),
        department_ids=tuple(department_ids),
        audited=True,
    )
