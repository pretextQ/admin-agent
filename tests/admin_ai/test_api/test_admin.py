# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""管理后台接口测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.core.auth.jwt_token import create_access_token
from app.admin_ai.core.tools.base import BaseTool, ToolResult
from app.admin_ai.core.tools.registry import ToolRegistry
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import AuditLogModel
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
