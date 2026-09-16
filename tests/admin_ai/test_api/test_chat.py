# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""对话接口测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from app.admin_ai.core.auth.jwt_token import create_access_token
from app.admin_ai.main import create_app


def _make_auth_headers() -> dict[str, str]:
    token = create_access_token({"sub": "user1", "employee_id": "EMP001", "role": "employee"})
    return {"Authorization": f"Bearer {token}"}


def _make_mock_orchestrator() -> AsyncMock:
    orch = AsyncMock()
    orch.process.return_value = {"content": "请问您要请什么假？", "requires_action": True}
    return orch


async def test_send_message_no_token_returns_401() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/chat/send", json={"message": "你好"})
    assert response.status_code == 401
    data = response.json()
    assert data["code"] == 40002


async def test_send_message_with_token() -> None:
    app = create_app()
    app.state.orchestrator = _make_mock_orchestrator()
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat/send",
            json={"message": "你好"},
            headers=headers,
        )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 0
    assert "conversation_id" in data["data"]
    assert data["data"]["content"] == "请问您要请什么假？"
    assert data["data"]["requires_action"] is True


async def test_history_requires_auth() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/chat/history/conv-001")
    assert response.status_code == 401
    data = response.json()
    assert data["code"] == 40002


async def test_confirm_requires_auth() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat/confirm/task-001",
            json={"confirmed": True},
        )
    assert response.status_code == 401
    data = response.json()
    assert data["code"] == 40002


async def test_transfer_requires_auth() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat/transfer/conv-001",
            json={},
        )
    assert response.status_code == 401
    data = response.json()
    assert data["code"] == 40002