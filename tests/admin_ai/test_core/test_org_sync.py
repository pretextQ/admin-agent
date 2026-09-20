# Copyright 2026  Admin AI Team, All rights reserved.
"""组织架构上游同步测试（评审 B-2 / 设计 §3、T-8、T-9）。

覆盖：CSV 解析、纯函数同步计划（新建/更新/软删）、失败降级（沿用旧快照、不清空组织数据）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from app.admin_ai.core.approval.sync import (
    DepartmentRecord,
    ExistingDepartment,
    OrgSyncError,
    load_csv_records,
    parse_departments_csv,
    parse_employees_csv,
    plan_org_sync,
    sync_org,
)

DEPARTMENTS_CSV = """external_id,name,parent_external_id,manager_employee_id
D100,公司,,gm001
D200,技术部,D100,admin001
D300,后端组,D200,
"""

EMPLOYEES_CSV = """employee_id,name,department_external_id,is_active
emp999,张三,D300,true
admin001,李四,D200,true
ghost001,王五,D200,true
"""


# ---------------------------------------------------------------- CSV 解析

def test_parse_departments_csv() -> None:
    """部门 CSV：空父级表示根节点。"""
    departments = parse_departments_csv(DEPARTMENTS_CSV)
    assert [(d.external_id, d.name, d.parent_external_id) for d in departments] == [
        ("D100", "公司", None),
        ("D200", "技术部", "D100"),
        ("D300", "后端组", "D200"),
    ]
    assert departments[1].manager_employee_id == "admin001"


def test_parse_employees_csv() -> None:
    """员工 CSV：is_active 支持常见写法。"""
    employees = parse_employees_csv(EMPLOYEES_CSV)
    assert [(e.employee_id, e.department_external_id) for e in employees] == [
        ("emp999", "D300"),
        ("admin001", "D200"),
        ("ghost001", "D200"),
    ]
    assert all(e.is_active for e in employees)


def test_load_csv_records_missing_directory_raises(tmp_path) -> None:
    """CSV 目录不存在 → OrgSyncError（调用方转失败降级，不猜组织数据）。"""
    try:
        load_csv_records(tmp_path / "not-exists")
    except OrgSyncError as exc:
        assert "不存在" in str(exc)
    else:  # pragma: no cover - 保护性断言
        raise AssertionError("应抛出 OrgSyncError")


def test_load_csv_records_from_files(tmp_path) -> None:
    """从目录读取两个 CSV 文件。"""
    (tmp_path / "departments.csv").write_text(DEPARTMENTS_CSV, encoding="utf-8")
    (tmp_path / "employees.csv").write_text(EMPLOYEES_CSV, encoding="utf-8")
    departments, employees = load_csv_records(tmp_path)
    assert len(departments) == 3
    assert len(employees) == 3


# ---------------------------------------------------------------- 同步计划

def _existing(
    dept_id: str, external_id: str | None, name: str, path: str, level: int = 1,
    parent_id: str | None = None, is_active: bool = True,
) -> ExistingDepartment:
    return ExistingDepartment(
        id=dept_id,
        external_id=external_id,
        name=name,
        path=path,
        level=level,
        parent_id=parent_id,
        manager_id=None,
        is_active=is_active,
    )


def test_plan_creates_departments_with_materialized_path() -> None:
    """新建部门时计算物化路径与层级。"""
    departments = parse_departments_csv(DEPARTMENTS_CSV)
    plan = plan_org_sync(
        departments=departments,
        employees=[],
        existing_departments=[],
        user_ids_by_employee_id={"gm001": "u-gm", "admin001": "u-admin"},
    )
    assert [(d.external_id, d.path, d.level) for d in plan.departments_to_create] == [
        ("D100", "/公司", 1),
        ("D200", "/公司/技术部", 2),
        ("D300", "/公司/技术部/后端组", 3),
    ]
    manager = {d.external_id: d.manager_id for d in plan.departments_to_create}
    assert manager == {"D100": "u-gm", "D200": "u-admin", "D300": None}


def test_plan_updates_renamed_and_moved_department() -> None:
    """部门改名或换上级 → 更新路径与层级。"""
    existing = [_existing("dept-1", "D100", "公司", "/公司")]
    departments = [
        DepartmentRecord(external_id="D100", name="集团"),
        DepartmentRecord(external_id="D200", name="技术部", parent_external_id="D100"),
    ]
    plan = plan_org_sync(
        departments=departments,
        employees=[],
        existing_departments=existing,
        user_ids_by_employee_id={},
    )
    assert plan.departments_to_create and plan.departments_to_create[0].external_id == "D200"
    assert [(dept_id, d.name, d.path) for dept_id, d in plan.departments_to_update] == [
        ("dept-1", "集团", "/集团")
    ]


def test_plan_deactivates_department_removed_upstream() -> None:
    """T-9 上游已删除的部门 → 本地软删（保留历史审批可追溯）。"""
    existing = [
        _existing("dept-1", "D100", "公司", "/公司"),
        _existing("dept-old", "D900", "已撤销部门", "/已撤销部门"),
        _existing("dept-manual", None, "手工维护部门", "/手工维护部门"),  # 无 external_id
    ]
    plan = plan_org_sync(
        departments=[DepartmentRecord(external_id="D100", name="公司")],
        employees=[],
        existing_departments=existing,
        user_ids_by_employee_id={},
    )
    assert plan.departments_to_deactivate == ("dept-old",)


def test_plan_updates_employee_department_and_flags_unmatched() -> None:
    """员工调动 → 更新部门；本地查无此人 → 计入未匹配不新建用户。"""
    existing = [_existing("dept-300", "D300", "后端组", "/公司/技术部/后端组", level=3)]
    plan = plan_org_sync(
        departments=[],
        employees=parse_employees_csv(EMPLOYEES_CSV),
        existing_departments=existing,
        user_ids_by_employee_id={"emp999": "u-emp", "admin001": "u-admin"},
    )
    assert [(user_id, e.department_external_id) for user_id, e in plan.employees_to_update] == [
        ("u-emp", "D300"),
        ("u-admin", "D200"),
    ]
    assert plan.employees_unmatched == ("ghost001",)


def test_plan_survives_missing_parent_reference() -> None:
    """上游父节点缺失或成环 → 挂到根，不抛异常（组织数据问题不应阻断同步）。"""
    departments = [
        DepartmentRecord(external_id="A", name="甲", parent_external_id="MISSING"),
        DepartmentRecord(external_id="B", name="乙", parent_external_id="C"),
        DepartmentRecord(external_id="C", name="丙", parent_external_id="B"),
    ]
    plan = plan_org_sync(
        departments=departments,
        employees=[],
        existing_departments=[],
        user_ids_by_employee_id={},
    )
    assert {d.external_id: d.level for d in plan.departments_to_create} == {
        "A": 1,
        "B": 1,
        "C": 1,
    }


# ---------------------------------------------------------------- 失败降级

def _mock_db() -> AsyncMock:
    db = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=result)
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


async def test_sync_failure_keeps_previous_snapshot() -> None:
    """T-8 同步失败：返回 ok=False、**不触碰数据库**（沿用上次快照）。"""
    db = _mock_db()
    summary = await sync_org(db, provider="csv", csv_dir="data/org/not-exists")

    assert summary.ok is False
    assert summary.provider == "csv"
    assert summary.error
    db.add.assert_not_called()
    db.commit.assert_not_awaited()


async def test_sync_applies_records_on_success(tmp_path) -> None:
    """同步成功：写入部门与员工调动摘要。"""
    (tmp_path / "departments.csv").write_text(DEPARTMENTS_CSV, encoding="utf-8")
    (tmp_path / "employees.csv").write_text(EMPLOYEES_CSV, encoding="utf-8")

    db = _mock_db()
    # 组织查询：部门表为空、用户表返回两个用户
    admin = MagicMock()
    admin.id = "u-admin"
    admin.employee_id = "admin001"
    admin.department_id = None
    admin.name = "李四"
    admin.is_active = True
    emp = MagicMock()
    emp.id = "u-emp"
    emp.employee_id = "emp999"
    emp.department_id = None
    emp.name = "张三"
    emp.is_active = True

    dept_result = MagicMock()
    dept_result.scalars.return_value.all.return_value = []
    user_result = MagicMock()
    user_result.scalars.return_value.all.return_value = [admin, emp]
    db.execute = AsyncMock(side_effect=[dept_result, user_result])

    summary = await sync_org(db, provider="csv", csv_dir=tmp_path)

    assert summary.ok is True
    assert summary.departments_created == 3
    assert summary.departments_deactivated == 0
    assert summary.employees_updated == 2
    assert summary.employees_unmatched == 1
    db.commit.assert_awaited()
    assert emp.department_id is not None


async def test_sync_unknown_provider_fails_safely() -> None:
    """未知 provider 取值 → 失败降级而不是崩溃。"""
    db = _mock_db()
    summary = await sync_org(db, provider="carrier-pigeon")
    assert summary.ok is False
    assert "provider" in (summary.error or "")
    db.add.assert_not_called()
