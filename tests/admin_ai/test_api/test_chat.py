# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""对话接口测试。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.core.agent.dialog import DialogManager
from app.admin_ai.core.agent.intent import IntentRecognizer
from app.admin_ai.core.agent.orchestrator import Orchestrator
from app.admin_ai.core.agent.slot import SlotExtractor
from app.admin_ai.core.agent.state_store import (
    ConversationState,
    InMemoryConversationStateStore,
)
from app.admin_ai.core.approval.router import ApprovalStep, RoutingError, RoutingOutcome
from app.admin_ai.core.auth.jwt_token import create_access_token
from app.admin_ai.core.rules.engine import RuleEngine
from app.admin_ai.core.tools.base import ToolResult
from app.admin_ai.core.tools.registry import ToolRegistry
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import (
    ApprovalModel,
    ConversationModel,
    ConversationStatus,
    MessageModel,
    MessageRole,
    TaskModel,
    TaskStatus,
    TaskType,
    UserModel,
)
from app.admin_ai.main import create_app


def _make_auth_headers(user_id: str = "user1") -> dict[str, str]:
    token = create_access_token({"sub": user_id, "employee_id": "EMP001", "role": "employee"})
    return {"Authorization": f"Bearer {token}"}


def _make_mock_orchestrator() -> AsyncMock:
    orch = AsyncMock()
    orch.process.return_value = {"content": "请问您要请什么假？", "requires_action": True}
    return orch


class _MockResult:
    """模拟 SQLAlchemy execute 结果。"""

    def __init__(self, value: Any = None, rows: list[Any] | None = None) -> None:
        self._value = value
        self._rows = rows or []

    def scalar_one_or_none(self) -> Any:
        return self._value

    def scalars(self) -> "_MockResult":
        return self

    def all(self) -> list[Any]:
        return self._rows


def _install_permissive_db(
    app, conversation=None, messages: list[Any] | None = None, extra_results: list[Any] | None = None
) -> AsyncMock:
    """覆盖数据库依赖：默认查不到会话、无历史消息，额外查询返回 extra_results。"""
    db = AsyncMock(spec=AsyncSession)
    queue = [_MockResult(value=conversation), _MockResult(rows=messages or [])]
    queue.extend(extra_results or [])

    def _execute(*args: Any, **kwargs: Any) -> Any:
        return queue.pop(0) if queue else _MockResult(value=None)

    db.execute = AsyncMock(side_effect=_execute)
    db.add = MagicMock()
    db.commit = AsyncMock()
    app.dependency_overrides[get_db_session] = lambda: db
    return db


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
    _install_permissive_db(app)
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


async def test_send_rejects_foreign_conversation() -> None:
    """他人会话不能通过 send 劫持继续对话。"""
    app = create_app()
    app.state.orchestrator = _make_mock_orchestrator()
    store = InMemoryConversationStateStore()
    await store.save("conv-foreign", ConversationState(user_id="owner", intent="other"))
    app.state.state_store = store
    transport = ASGITransport(app=app)
    headers = _make_auth_headers(user_id="intruder")
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat/send",
            json={"message": "你好", "conversation_id": "conv-foreign"},
            headers=headers,
        )
    assert response.status_code == 403
    assert response.json()["code"] == 40003


async def test_history_requires_auth() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/chat/history/conv-001")
    assert response.status_code == 401
    data = response.json()
    assert data["code"] == 40002


async def test_history_returns_persisted_messages() -> None:
    """history 应返回落库的消息，并还原 meta 中的卡片与确认标记。"""
    app = create_app()
    conversation = MagicMock(spec=ConversationModel)
    conversation.id = "conv-hist"
    conversation.user_id = "user1"
    user_msg = MagicMock(spec=MessageModel)
    user_msg.id = "m1"
    user_msg.role = "user"
    user_msg.content = "我要报销"
    user_msg.meta = None
    user_msg.created_at = datetime(2026, 9, 19, 1, 0, tzinfo=timezone.utc)
    assistant_msg = MagicMock(spec=MessageModel)
    assistant_msg.id = "m2"
    assistant_msg.role = "assistant"
    assistant_msg.content = "请确认以下操作"
    assistant_msg.meta = {"card_data": {"type": "confirmation"}, "requires_action": True}
    assistant_msg.created_at = datetime(2026, 9, 19, 1, 1, tzinfo=timezone.utc)

    _install_permissive_db(app, conversation=conversation, messages=[user_msg, assistant_msg])
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/chat/history/conv-hist", headers=headers)

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 2
    assert data["messages"][0]["content"] == "我要报销"
    assert data["messages"][1]["requires_action"] is True
    assert data["messages"][1]["card_data"] == {"type": "confirmation"}


async def test_history_rejects_non_owner() -> None:
    """非会话属主查询历史返回 40003。"""
    app = create_app()
    conversation = MagicMock(spec=ConversationModel)
    conversation.id = "conv-hist"
    conversation.user_id = "owner"
    _install_permissive_db(app, conversation=conversation)
    transport = ASGITransport(app=app)
    headers = _make_auth_headers(user_id="intruder")
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/chat/history/conv-hist", headers=headers)
    assert response.status_code == 403
    assert response.json()["code"] == 40003


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


async def test_transfer_marks_conversation_transferred() -> None:
    """转人工应把会话标记为 transferred 并写一条消息进历史。"""
    app = create_app()
    conversation = MagicMock(spec=ConversationModel)
    conversation.id = "conv-transfer"
    conversation.user_id = "user1"
    db = _install_permissive_db(app, conversation=conversation)
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat/transfer/conv-transfer",
            json={"reason": "需要人工协助"},
            headers=headers,
        )

    assert response.status_code == 200
    assert response.json()["code"] == 0
    assert conversation.status == ConversationStatus.TRANSFERRED
    message_adds = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], MessageModel)]
    assert len(message_adds) == 1
    assert message_adds[0].conversation_id == "conv-transfer"
    assert message_adds[0].role == MessageRole.ASSISTANT
    db.commit.assert_awaited()


async def test_transfer_rejects_non_owner() -> None:
    """非会话属主不能把他人会话转人工。"""
    app = create_app()
    conversation = MagicMock(spec=ConversationModel)
    conversation.id = "conv-transfer"
    conversation.user_id = "owner"
    _install_permissive_db(app, conversation=conversation)
    transport = ASGITransport(app=app)
    headers = _make_auth_headers(user_id="intruder")
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat/transfer/conv-transfer", json={}, headers=headers
        )
    assert response.status_code == 403
    assert response.json()["code"] == 40003


async def test_transfer_unknown_conversation_returns_404() -> None:
    """会话不存在时转人工返回 40004，而不是谎报成功。"""
    app = create_app()
    _install_permissive_db(app)
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/chat/transfer/conv-missing", json={}, headers=headers)
    assert response.status_code == 404
    assert response.json()["code"] == 40004


async def test_transfer_clears_pending_confirmation() -> None:
    """转人工后清除待确认状态，避免人工介入期间仍能确认执行高风险操作。"""
    app = create_app()
    store = InMemoryConversationStateStore()
    await store.save(
        "conv-transfer",
        ConversationState(
            user_id="user1",
            business_type="expense",
            slots={"expense_type": "酒店", "amount": 500},
            pending_confirmation=True,
        ),
    )
    app.state.state_store = store
    conversation = MagicMock(spec=ConversationModel)
    conversation.id = "conv-transfer"
    conversation.user_id = "user1"
    _install_permissive_db(app, conversation=conversation)
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/v1/chat/transfer/conv-transfer", json={}, headers=headers)

    state = await store.get("conv-transfer")
    assert state is None or state.pending_confirmation is False


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
    db = _install_permissive_db(app)
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

    # 成功执行应创建任务记录（低风险自动完成），供任务列表展示
    task_adds = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], TaskModel)]
    assert len(task_adds) == 1
    assert task_adds[0].type == TaskType.LEAVE
    assert "年假" in task_adds[0].title
    assert task_adds[0].conversation_id == "conv-multi"
    assert task_adds[0].risk_level == "low"
    assert task_adds[0].status == TaskStatus.COMPLETED


def _confirm_orchestrator(captured: list[Any]) -> AsyncMock:
    """构造会记录上下文的高风险确认编排器桩。"""
    orch = AsyncMock()

    async def _process(message: str, context: Any, attachments: Any = None) -> dict[str, Any]:
        captured.append(context)
        if context.confirmed:
            return {
                "content": "操作已完成",
                "task_type": "expense",
                "slots": {"expense_type": "酒店", "amount": 500},
            }
        context.intent = "expense_request"
        context.business_type = "expense"
        context.slots = {"expense_type": "酒店", "amount": 500}
        return {
            "content": "请确认以下操作",
            "card_data": {
                "type": "confirmation",
                "title": "请确认以下操作",
                "data": {"expense_type": "酒店", "amount": 500},
                "actions": ["confirm", "cancel"],
                "warning": "此操作将产生重要影响，请仔细核对",
            },
            "requires_action": True,
        }

    orch.process.side_effect = _process
    return orch


async def test_confirm_resumes_pending_action() -> None:
    """高风险操作确认后应携带原槽位恢复执行，并按路由结果生成审批链。"""
    app = create_app()
    captured: list[Any] = []
    app.state.orchestrator = _confirm_orchestrator(captured)
    app.state.state_store = InMemoryConversationStateStore()
    db = _install_permissive_db(app)
    outcome = RoutingOutcome(steps=(
        ApprovalStep(step=1, approver_id="director-1", source="parent_dept_manager"),
        ApprovalStep(step=2, approver_id="manager-1", source="self_dept_manager"),
    ))
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()

    with patch(
        "app.admin_ai.api.chat.route_approval", AsyncMock(return_value=outcome)
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            send = await client.post(
                "/api/v1/chat/send",
                json={"message": "我要报销", "conversation_id": "conv-confirm"},
                headers=headers,
            )
            assert send.json()["data"]["requires_action"] is True

            confirm = await client.post(
                "/api/v1/chat/confirm/conv-confirm",
                json={"confirmed": True},
                headers=headers,
            )

    assert confirm.json()["data"]["content"] == "操作已完成"
    confirm_context = captured[-1]
    assert confirm_context.confirmed is True
    assert confirm_context.business_type == "expense"
    assert confirm_context.slots == {"expense_type": "酒店", "amount": 500}

    # 确认执行成功后创建高风险任务，审批链来自路由结果（不再是「首个管理员」）
    task_adds = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], TaskModel)]
    assert len(task_adds) == 1
    assert task_adds[0].type == TaskType.EXPENSE
    assert task_adds[0].risk_level == "high"
    assert task_adds[0].requires_confirmation is True
    assert task_adds[0].status == TaskStatus.APPROVING
    assert task_adds[0].approver_id == "director-1"

    approval_adds = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], ApprovalModel)]
    assert [(a.step, a.approver_id) for a in approval_adds] == [
        (1, "director-1"),
        (2, "manager-1"),
    ]
    assert all(a.status == "pending" for a in approval_adds)
    assert [a.approver_source for a in approval_adds] == [
        "parent_dept_manager",
        "self_dept_manager",
    ]


async def test_routing_failure_marks_task_for_manual_assignment() -> None:
    """路由解析不出审批人时不猜测：任务置 PROCESSING、记录原因并通知行政专员。"""
    app = create_app()
    captured: list[Any] = []
    app.state.orchestrator = _confirm_orchestrator(captured)
    app.state.state_store = InMemoryConversationStateStore()
    db = _install_permissive_db(app)
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()

    with patch(
        "app.admin_ai.api.chat.route_approval",
        AsyncMock(side_effect=RoutingError("no_manager", "部门「技术部」未设置主管")),
    ):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            await client.post(
                "/api/v1/chat/send",
                json={"message": "我要报销", "conversation_id": "conv-manual"},
                headers=headers,
            )
            await client.post(
                "/api/v1/chat/confirm/conv-manual",
                json={"confirmed": True},
                headers=headers,
            )

    task_adds = [c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], TaskModel)]
    assert len(task_adds) == 1
    assert task_adds[0].status == TaskStatus.PROCESSING
    assert task_adds[0].data["_routing"]["status"] == "manual_assign_required"
    assert task_adds[0].data["_routing"]["reason"] == "no_manager"
    # 槽位数据保留，人工指派后仍可继续办理
    assert task_adds[0].data["expense_type"] == "酒店"
    # 不生成任何审批记录（避免"猜"一个审批人出来）
    assert not [
        c.args[0] for c in db.add.call_args_list if isinstance(c.args[0], ApprovalModel)
    ]


async def test_confirm_false_cancels_without_executing() -> None:
    """取消确认不执行工具，并清除待确认状态。"""
    app = create_app()
    captured: list[Any] = []
    orchestrator = _confirm_orchestrator(captured)
    app.state.orchestrator = orchestrator
    app.state.state_store = InMemoryConversationStateStore()
    _install_permissive_db(app)
    transport = ASGITransport(app=app)
    headers = _make_auth_headers()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post(
            "/api/v1/chat/send",
            json={"message": "我要报销", "conversation_id": "conv-cancel"},
            headers=headers,
        )
        confirm = await client.post(
            "/api/v1/chat/confirm/conv-cancel",
            json={"confirmed": False},
            headers=headers,
        )

    assert "已取消" in confirm.json()["data"]["content"]
    assert orchestrator.process.await_count == 1


async def test_confirm_rejects_non_owner() -> None:
    """非会话属主不能确认/取消他人的高风险操作。"""
    app = create_app()
    orchestrator = _make_mock_orchestrator()
    app.state.orchestrator = orchestrator
    store = InMemoryConversationStateStore()
    await store.save("conv-owned", ConversationState(
        user_id="owner",
        business_type="expense",
        pending_confirmation=True,
    ))
    app.state.state_store = store
    transport = ASGITransport(app=app)
    headers = _make_auth_headers(user_id="intruder")
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/chat/confirm/conv-owned",
            json={"confirmed": True},
            headers=headers,
        )
    assert response.status_code == 403
    assert response.json()["code"] == 40003
    assert orchestrator.process.await_count == 0, "未授权的确认不应触达编排器"
