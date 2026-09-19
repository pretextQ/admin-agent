# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""中间件测试：TraceId 注入与审计落库。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.core.auth.jwt_token import create_access_token
from app.admin_ai.db.database import get_db_session
from app.admin_ai.main import create_app
from app.admin_ai.middleware.audit import _parse_path


def test_parse_path_action_and_resource() -> None:
    assert _parse_path("/api/v1/chat/send") == ("chat.send", "chat", None)
    # 健康检查不在 /api/v1 下，前缀保持原样（GET 不会落审计，仅单测解析逻辑）
    assert _parse_path("/api/health") == ("api.health", "api", None)


def test_parse_path_extracts_uuid_resource_id() -> None:
    task_id = "0b6e2a52-1d6f-4c1e-9d3a-8b1f2c3d4e5f"
    action, resource_type, resource_id = _parse_path(f"/api/v1/tasks/{task_id}")
    assert action == f"tasks.{task_id}"
    assert resource_type == "tasks"
    assert resource_id == task_id


def test_parse_path_action_segment_not_resource_id() -> None:
    # 末段不是 UUID 时不应误判为资源 id
    assert _parse_path("/api/v1/chat/confirm/conv-abc")[2] is None


def _install_endpoint_db(app) -> AsyncMock:
    """端点依赖的数据库桩：查不到会话、无历史消息。"""
    db = AsyncMock(spec=AsyncSession)
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=result)
    app.dependency_overrides[get_db_session] = lambda: db
    return db


async def test_trace_id_header_present() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.headers["X-Request-Id"]


async def test_trace_id_reuses_incoming_header() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(
            "/api/health", headers={"X-Request-Id": "trace-123"}
        )
    assert response.headers["X-Request-Id"] == "trace-123"


async def test_audit_writes_row_for_rejected_post(stub_audit_db) -> None:
    """无效 token 的 POST 也应写审计行，并记为 rejected。"""
    app = create_app()
    orchestrator = AsyncMock()
    orchestrator.process.return_value = {"content": "你好，我是行政助手"}
    app.state.orchestrator = orchestrator
    _install_endpoint_db(app)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat/send",
            json={"message": "你好"},
            headers={"Authorization": "Bearer invalid"},
        )

    assert response.status_code == 401
    stub_audit_db.add.assert_called_once()
    row = stub_audit_db.add.call_args[0][0]
    assert row.action == "chat.send"
    assert row.resource_type == "chat"
    assert row.input_data == {"message": "你好"}
    assert row.decision == "rejected(401)"
    assert row.user_id is None


async def test_audit_records_success_with_user(stub_audit_db) -> None:
    """有效 token 的成功请求，审计行记录用户与 success。"""
    app = create_app()
    orchestrator = AsyncMock()
    orchestrator.process.return_value = {"content": "ok"}
    app.state.orchestrator = orchestrator
    _install_endpoint_db(app)

    token = create_access_token({"sub": "user1", "employee_id": "E1", "role": "employee"})
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/chat/send",
            json={"message": "你好"},
            headers={"Authorization": f"Bearer {token}"},
        )

    stub_audit_db.add.assert_called_once()
    row = stub_audit_db.add.call_args[0][0]
    assert row.user_id == "user1"
    assert row.decision == "success"
    assert row.conversation_id is None or isinstance(row.conversation_id, str)
