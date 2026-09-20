# Copyright 2026  Admin AI Team, All rights reserved.
"""开发环境组织架构种子数据（评审 B-2）。

建立一套能跑通审批路由的最小组织：

    公司（主管 gm001）
    └── 技术部（主管 admin001）
         成员：emp999

因此端到端冒烟能覆盖真实路由而非「首个管理员」：
`emp999` 提交报销 → 路由到部门主管 `admin001`；单笔 >2000 元则为两级（gm001 → admin001）。

幂等：用户按 `employee_id`、部门按 `external_id`（无则按 `path`）复用已有行。
部门的 `external_id` 与 `scripts/sample_org/*.csv` 对齐，因此后续用
`scripts/sync_org.py --provider csv --dir scripts/sample_org` 演练同步时是更新而非重复建部门。
生产环境的部门与汇报线应从 HR 同步（`scripts/sync_org.py`），本脚本只用于开发与联调。
"""

from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.db.database import get_session_factory
from app.admin_ai.db.models import DepartmentModel, UserModel

# (employee_id, 姓名, 角色)
DEMO_USERS = [
    ("gm001", "总经理", "manager"),
    ("admin001", "管理员", "admin"),
    ("emp999", "开发用户-emp999", "employee"),
]
# (部门名, 上级部门名, 主管 employee_id, 上游部门 ID)
DEMO_DEPARTMENTS = [
    ("公司", None, "gm001", "D100"),
    ("技术部", "公司", "admin001", "D200"),
]
# 部门成员
DEMO_MEMBERSHIPS = [("admin001", "技术部"), ("emp999", "技术部"), ("gm001", "公司")]


async def _ensure_user(db: AsyncSession, employee_id: str, name: str, role: str) -> UserModel:
    """按 employee_id 取用户，不存在则创建（不改动已有用户的姓名与角色）。"""
    user = (
        await db.execute(select(UserModel).where(UserModel.employee_id == employee_id))
    ).scalar_one_or_none()
    if user is None:
        user = UserModel(employee_id=employee_id, name=name, role=role)
        db.add(user)
        await db.flush()
    return user


async def _ensure_department(
    db: AsyncSession,
    name: str,
    parent: DepartmentModel | None,
    manager_id: str | None,
    external_id: str | None,
) -> DepartmentModel:
    """按上游 ID（优先）或物化路径取部门，不存在则创建。"""
    department = None
    if external_id:
        department = (
            await db.execute(
                select(DepartmentModel).where(DepartmentModel.external_id == external_id)
            )
        ).scalar_one_or_none()
    path = f"{parent.path}/{name}" if parent else f"/{name}"
    if department is None:
        department = (
            await db.execute(select(DepartmentModel).where(DepartmentModel.path == path))
        ).scalar_one_or_none()
    if department is None:
        department = DepartmentModel(
            name=name,
            parent_id=parent.id if parent else None,
            path=path,
            level=(parent.level + 1) if parent else 1,
            manager_id=manager_id,
            external_id=external_id,
        )
        db.add(department)
        await db.flush()
    else:
        if manager_id and department.manager_id != manager_id:
            department.manager_id = manager_id
        if external_id and not department.external_id:
            department.external_id = external_id
    return department


async def seed() -> None:
    """写入开发环境组织数据（幂等）。"""
    factory = get_session_factory()
    async with factory() as db:
        users = {emp: await _ensure_user(db, emp, name, role) for emp, name, role in DEMO_USERS}

        departments: dict[str, DepartmentModel] = {}
        for name, parent_name, manager_employee_id, external_id in DEMO_DEPARTMENTS:
            department = await _ensure_department(
                db,
                name=name,
                parent=departments.get(parent_name) if parent_name else None,
                manager_id=users[manager_employee_id].id,
                external_id=external_id,
            )
            departments[name] = department

        for employee_id, department_name in DEMO_MEMBERSHIPS:
            department = departments[department_name]
            user = users[employee_id]
            user.department_id = department.id
            # 兼容期双写旧列，Contract 阶段移除（设计 §2.2）
            user.department = department.name

        await db.commit()

        for name, department in departments.items():
            manager = next(
                (u for u in users.values() if u.id == department.manager_id), None
            )
            print(
                f"部门 {name}（{department.path}，level={department.level}）"
                f" 主管={manager.employee_id if manager else '未设置'}"
            )
        print("组织种子数据就绪：公司(gm001) → 技术部(admin001)，成员 admin001 / emp999")


if __name__ == "__main__":
    asyncio.run(seed())
