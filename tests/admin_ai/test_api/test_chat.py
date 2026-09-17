# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""对话接口测试。"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

from httpx import ASGITransport, AsyncClient

from app.admin_ai.core.agent.dialog import DialogManager
from app.admin_ai.core.agent.intent import IntentRecognizer
from app.admin_ai.core.agent.orchestrator import Orchestrator
from app.admin_ai.core.agent.slot import SlotExtractor
from app.admin_ai.core.agent.state_store import InMemoryConversationStateStore
from app.admin_ai.core.auth.jwt_token import create_access_token
from app.admin_ai.core.rules.engine import RuleEngine
from app.admin_ai.core.tools.base import ToolResult
from app.admin_ai.core.tools.registry import ToolRegistry
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


class _StubTool:
    """记录调用的工具桩。"""

    name = "leave"
    description = "stub"

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def execute(self, params: dict[str, Any], user_id: str) -> ToolResult:
        self.calls.append(params)
        return ToolResult.text("ok")


def _real_orchestrator(business_type: str = "leave") -> tuple[Orchestrator, _StubTool]:
    tool = _StubTool()
    registry = ToolRegistry()
    registry.register(business_type, tool)
    orchestrator = Orchestrator(
        intent_recognizer=IntentRecognizer(llm_client=None),
        slot_extractor=SlotExtractor(llm_client=None),
        dialog_manager=DialogManager(),
        rule_engine=RuleEngine(),
        tool_registry=registry,
    )
    return orchestrator, tool


async def test_multi_turn_slot_filling_completes() -> None:
    """同一会话内多轮补全槽位后应执行工具，而不是转人工。"""
    app = create_app()
    orchestrator, tool = _real_orchestrator()
    app.state.orchestrator = orchestrator
    app.state.state_store = InMemoryConversationStateStore()
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        first = await client.post(
            "/api/v1/chat/send",
            json={"message": "我要请假", "conversation_id": "conv-multi"},
            headers=headers,
        )
        assert first.json()["data"]["requires_action"] is True

        second = await client.post(
            "/api/v1/chat/send",
            json={
                "message": "年假 2026-09-20 到 2026-09-21",
                "conversation_id": "conv-multi",
            },
            headers=headers,
        )

    body = second.json()["data"]
    assert "操作已完成" in body["content"]
    assert body.get("requires_action") is not True
    assert tool.calls, "补齐槽位后应调用工具"
