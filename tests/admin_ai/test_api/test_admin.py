# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""管理后台接口测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.core.auth.jwt_token import create_access_token
from app.admin_ai.core.tools.base import BaseTool, ToolResult
from app.admin_ai.core.tools.registry import ToolRegistry
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import (
    ApprovalDelegationModel,
    ApprovalMode,
    ApprovalRuleModel,
    ApproverType,
    AuditLogModel,
)
from app.admin_ai.main import create_app


def _headers(role: str = "employee") -> dict[str, str]:
    token = create_access_token({
        "sub": "user1",
        "employee_id": "EMP001",
        "role": role,
    })
    return {"Authorization": f"Bearer {token}"}


class _MockResult:
    """模拟 SQLAlchemy execute 结果。"""

    def __init__(self, value=None, rows=None) -> None:
        self._value = value
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _install_db(app, scalars: int = 0, execute_rows=None) -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    db.scalar = AsyncMock(return_value=scalars)
    db.execute = AsyncMock(return_value=_MockResult(rows=execute_rows or []))
    app.dependency_overrides[get_db_session] = lambda: db
    return db


async def test_admin_requires_token() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/dashboard")
    assert response.status_code == 401
    assert response.json()["code"] == 40002


async def test_admin_forbidden_for_employee() -> None:
    """普通员工访问管理接口返回 40003。"""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/dashboard", headers=_headers("employee"))
    assert response.status_code == 403
    assert response.json()["code"] == 40003


async def test_admin_dashboard_with_admin() -> None:
    """管理员可访问仪表盘，数据来自数据库统计。"""
    app = create_app()
    db = _install_db(app, scalars=5)
    db.execute = AsyncMock(return_value=_MockResult(rows=[("leave_request", 3)]))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/dashboard", headers=_headers("admin"))

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["today_conversations"] == 5
    assert data["top_intents"] == [{"intent": "leave_request", "count": 3}]
    app.dependency_overrides.clear()


async def test_admin_audit_logs_returns_rows() -> None:
    """审计日志查询返回落库记录。"""
    app = create_app()
    log = MagicMock(spec=AuditLogModel)
    log.id = "log1"
    log.user_id = "user1"
    log.conversation_id = None
    log.action = "chat.send"
    log.resource_type = "chat"
    log.resource_id = None
    log.input_data = {"message": "你好"}
    log.decision = "success"
    log.ip_address = "127.0.0.1"
    log.created_at = datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc)

    db = _install_db(app, scalars=1)
    db.execute = AsyncMock(return_value=_MockResult(rows=[log]))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/v1/admin/audit-logs", headers=_headers("admin")
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["logs"][0]["action"] == "chat.send"
    assert data["logs"][0]["input_data"] == {"message": "你好"}
    app.dependency_overrides.clear()


class _StubTool(BaseTool):
    name = "leave"
    description = "stub"

    async def execute(self, params, user_id: str) -> ToolResult:
        return ToolResult.text("ok")


async def test_admin_tools_lists_registry() -> None:
    """工具列表来自工具注册中心。"""
    app = create_app()
    registry = ToolRegistry()
    registry.register("leave", _StubTool())
    app.state.tool_registry = registry
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/tools", headers=_headers("admin"))

    assert response.status_code == 200
    assert response.json()["data"]["tools"] == [
        {"name": "leave", "description": "stub"}
    ]


# ---------------------------------------------------------------- 审批规则与委派维护（评审 B-2 / 决策 D-5）


async def test_approval_rules_requires_admin() -> None:
    """审批规则维护入口必须鉴权：普通员工访问返回 40003。"""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        listed = await client.get("/api/v1/admin/approval-rules", headers=_headers("employee"))
        created = await client.post(
            "/api/v1/admin/approval-rules",
            json={"business_type": "expense", "approver_type": "self_dept_manager"},
            headers=_headers("employee"),
        )
    assert listed.status_code == 403
    assert created.status_code == 403


async def test_list_approval_rules_returns_rows() -> None:
    """管理员可列出审批规则（含金额区间与审批人类型）。"""
    app = create_app()
    rule = MagicMock()
    rule.id = "r1"
    rule.business_type = "expense"
    rule.amount_min = Decimal("0")
    rule.amount_max = Decimal("2000")
    rule.step_order = 1
    rule.approver_type = ApproverType.SELF_DEPT_MANAGER
    rule.approver_param = None
    rule.approval_mode = ApprovalMode.ANY_ONE
    rule.required = True
    rule.enabled = True
    rule.remark = "APR-001"

    db = _install_db(app, execute_rows=[rule])
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/approval-rules", headers=_headers("admin"))
    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["business_type"] == "expense"
    assert item["amount_max"] == 2000.0
    assert item["approver_type"] == "self_dept_manager"
    assert item["approval_mode"] == "any_one"


async def test_create_approval_rule_validates_approver_type() -> None:
    """非法 approver_type → 40001（配置错误会导致审批链解析失败）。"""
    app = create_app()
    db = _install_db(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/approval-rules",
            json={"business_type": "expense", "approver_type": "whoever"},
            headers=_headers("admin"),
        )
    assert response.status_code == 400
    assert response.json()["code"] == 40001


async def test_create_approval_rule_requires_param_for_role() -> None:
    """role 类型必须给 approver_param。"""
    app = create_app()
    db = _install_db(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/approval-rules",
            json={"business_type": "expense", "approver_type": "role"},
            headers=_headers("admin"),
        )
    assert response.status_code == 400
    assert "approver_param" in response.json()["message"]


async def test_create_approval_rule_validates_amount_range() -> None:
    """amount_min 必须小于 amount_max。"""
    app = create_app()
    db = _install_db(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/approval-rules",
            json={
                "business_type": "expense",
                "approver_type": "self_dept_manager",
                "amount_min": 2000,
                "amount_max": 2000,
            },
            headers=_headers("admin"),
        )
    assert response.status_code == 400
    assert "amount_min" in response.json()["message"]


async def test_create_approval_rule_persists() -> None:
    """新增规则落库并返回完整字段。"""
    app = create_app()
    db = _install_db(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/approval-rules",
            json={
                "business_type": "expense",
                "approver_type": "role",
                "approver_param": "finance",
                "approval_mode": "all_must",
                "amount_min": 2000,
            },
            headers=_headers("admin"),
        )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["approver_param"] == "finance"
    assert data["approval_mode"] == "all_must"
    assert data["amount_min"] == 2000.0
    assert data["amount_max"] is None
    added = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], ApprovalRuleModel)]
    assert len(added) == 1
    db.commit.assert_awaited()


async def test_delete_approval_rule_missing_returns_404() -> None:
    """删除不存在的规则返回 40004。"""
    app = create_app()
    db = _install_db(app)
    db.execute = AsyncMock(return_value=_MockResult(value=None))
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.delete(
            "/api/v1/admin/approval-rules/not-exist", headers=_headers("admin")
        )
    assert response.status_code == 404
    assert response.json()["code"] == 40004


async def test_create_delegation_rejects_self_delegation() -> None:
    """不能把审批权委派给自己。"""
    app = create_app()
    db = _install_db(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/approval-delegations",
            json={
                "delegator_id": "u1",
                "delegate_id": "u1",
                "start_at": "2026-09-20T00:00:00",
                "end_at": "2026-09-27T00:00:00",
            },
            headers=_headers("admin"),
        )
    assert response.status_code == 400
    assert response.json()["code"] == 40001


async def test_create_delegation_persists() -> None:
    """新增委派落库（主管休假期间的代理审批）。"""
    app = create_app()
    db = _install_db(app)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/admin/approval-delegations",
            json={
                "delegator_id": "u1",
                "delegate_id": "u2",
                "start_at": "2026-09-20T00:00:00",
                "end_at": "2026-09-27T00:00:00",
                "business_types": ["expense"],
            },
            headers=_headers("admin"),
        )
    assert response.status_code == 200
    assert response.json()["data"]["delegate_id"] == "u2"
    added = [
        c.args[0]
        for c in db.add.call_args_list
        if isinstance(c.args[0], ApprovalDelegationModel)
    ]
    assert len(added) == 1


async def test_list_departments_returns_manager_info() -> None:
    """部门列表带主管信息，便于核对组织数据完整性。"""
    app = create_app()
    dept = MagicMock()
    dept.id = "dept-1"
    dept.name = "技术部"
    dept.parent_id = "dept-0"
    dept.path = "/公司/技术部"
    dept.level = 2
    dept.external_id = "D200"
    dept.is_active = True
    dept.manager_id = "u-admin"

    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock(side_effect=[
        _MockResult(rows=[dept]),
        _MockResult(rows=[("u-admin", "admin001", "管理员")]),
    ])
    app.dependency_overrides[get_db_session] = lambda: db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/admin/departments", headers=_headers("admin"))
    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert item["manager"]["employee_id"] == "admin001"
    assert item["external_id"] == "D200"
