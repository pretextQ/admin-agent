# Copyright 2026  Admin AI Team, All rights reserved.
"""任务查询的数据归属校验测试（SECURITY §4.3 / 设计 §5、T-6）。

要点：employee 只能看本人；部门主管可看本部门及子部门；财务/HR/管理员看全量但**每次访问记审计**。
归属条件必须下推到 SQL（禁止先查全量再在内存过滤）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

from app.admin_ai.core.auth.jwt_token import create_access_token
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import AuditLogModel, DepartmentModel
from app.admin_ai.main import create_app


def _headers(user_id: str = "user1", role: str = "employee") -> dict[str, str]:
    token = create_access_token({"sub": user_id, "employee_id": "EMP001", "role": role})
    return {"Authorization": f"Bearer {token}"}


class _Result:
    """通用 mock 查询结果：同时支持 scalar_one_or_none 与 scalars().all()。"""

    def __init__(self, value=None, rows=None):
        self._value = value
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _db(results: list[_Result] | None = None, scalars: list[int] | None = None) -> AsyncMock:
    """按调用顺序返回结果的 mock session（`scalars` 对应分页统计的 count 查询）。"""
    db = AsyncMock()
    queue = list(results or [])
    count_queue = list(scalars or [])
    db.execute = AsyncMock(side_effect=lambda *a, **k: queue.pop(0) if queue else _Result())
    db.scalar = AsyncMock(
        side_effect=lambda *a, **k: count_queue.pop(0) if count_queue else 0
    )
    db.add = MagicMock()
    db.commit = AsyncMock()
    return db


def _department(dept_id: str = "dept-1", path: str = "/公司/技术部") -> MagicMock:
    dept = MagicMock(spec=DepartmentModel)
    dept.id = dept_id
    dept.path = path
    dept.is_active = True
    return dept


async def _get_my_tasks(
    db, *, scope: str | None = None, role: str = "employee", user_id: str = "user1"
):
    """调用 /tasks/my 并返回响应。"""
    app = create_app()

    async def _override_db():
        yield db

    app.dependency_overrides[get_db_session] = _override_db
    url = "/api/v1/tasks/my" if scope is None else f"/api/v1/tasks/my?scope={scope}"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(url, headers=_headers(user_id=user_id, role=role))
    app.dependency_overrides.clear()
    return response


async def test_default_scope_is_owner_only() -> None:
    """默认只返回本人任务（不传 scope 时保持原有行为）。"""
    db = _db(results=[_Result(rows=[])], scalars=[3, 0, 1])
    response = await _get_my_tasks(db)
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 3


async def test_all_scope_rejected_for_employee() -> None:
    """普通员工请求全量范围 → 40003。"""
    response = await _get_my_tasks(_db(), scope="all")
    assert response.status_code == 403
    assert response.json()["code"] == 40003


async def test_dept_scope_rejected_for_non_manager() -> None:
    """非部门主管请求部门范围 → 40003（不允许越权升格为全量）。"""
    response = await _get_my_tasks(_db(results=[_Result(rows=[])]), scope="dept")
    assert response.status_code == 403
    assert response.json()["code"] == 40003


async def test_unknown_scope_rejected() -> None:
    """非法 scope 取值 → 40001。"""
    response = await _get_my_tasks(_db(), scope="everything")
    assert response.status_code == 400
    assert response.json()["code"] == 40001


async def test_dept_scope_works_for_manager_and_is_audited() -> None:
    """部门主管可按本部门及子部门查询，且该次访问写入审计。"""
    dept = _department()
    db = _db(
        results=[
            _Result(rows=[dept]),       # 所辖部门
            _Result(rows=[dept.path]),  # 所辖部门路径
            _Result(rows=["dept-1"]),   # 子树部门 ID
            _Result(rows=[]),           # 任务列表
        ],
        scalars=[2, 1, 1],
    )
    response = await _get_my_tasks(db, scope="dept", role="manager", user_id="mgr-1")

    assert response.status_code == 200
    assert response.json()["data"]["total"] == 2
    audits = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], AuditLogModel)]
    assert len(audits) == 1
    assert audits[0].action == "task_scope_query"
    assert "dept" in (audits[0].decision or "")
    assert audits[0].user_id == "mgr-1"
    db.commit.assert_awaited()


async def test_all_scope_allowed_for_admin_and_audited() -> None:
    """管理员可查全量，且该次访问写入审计。"""
    db = _db(results=[_Result(rows=[])], scalars=[9, 0, 0])
    response = await _get_my_tasks(db, scope="all", role="admin", user_id="admin-1")

    assert response.status_code == 200
    assert response.json()["data"]["total"] == 9
    audits = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], AuditLogModel)]
    assert len(audits) == 1
    assert audits[0].user_id == "admin-1"
    assert "all" in (audits[0].decision or "")


async def test_all_scope_allowed_for_finance_role() -> None:
    """财务角色可查全量（受审计）。"""
    db = _db(results=[_Result(rows=[])], scalars=[4, 0, 0])
    response = await _get_my_tasks(db, scope="all", role="finance", user_id="fin-1")
    assert response.status_code == 200
    assert response.json()["data"]["total"] == 4


async def test_owner_scope_does_not_write_audit() -> None:
    """本人范围查询无需审计（避免审计表被高频自查看淹没）。"""
    db = _db(results=[_Result(rows=[])], scalars=[1, 0, 0])
    await _get_my_tasks(db, scope="my")
    assert not [
        c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], AuditLogModel)
    ]
