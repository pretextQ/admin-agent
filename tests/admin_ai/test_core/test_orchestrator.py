# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""编排器测试。"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.admin_ai.core.agent.orchestrator import Orchestrator, AgentContext, AgentState
from app.admin_ai.core.tools.base import ToolResult


@pytest.fixture
def orchestrator() -> Orchestrator:
    intent_recognizer = MagicMock()
    intent_recognizer.recognize = AsyncMock()
    slot_extractor = MagicMock()
    slot_extractor.extract = AsyncMock()
    slot_extractor.check_completeness = MagicMock(return_value=[])
    dialog_manager = MagicMock()
    rule_engine = MagicMock()
    rule_engine.validate = AsyncMock()
    tool_registry = MagicMock()
    return Orchestrator(
        intent_recognizer=intent_recognizer,
        slot_extractor=slot_extractor,
        dialog_manager=dialog_manager,
        rule_engine=rule_engine,
        tool_registry=tool_registry,
    )


@pytest.mark.asyncio
async def test_unknown_intent_transfers_to_human(orchestrator: Orchestrator) -> None:
    """未知意图走转人工分支。"""
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "other",
        "confidence": 0.5,
    }
    context = AgentContext(user_id="u1", conversation_id="c1")
    result = await orchestrator.process("一些随机文本", context)

    assert result.get("transfer_to_human") is True
    assert context.state == AgentState.TRANSFERRED
    assert "转接人工客服" in result["content"]


@pytest.mark.asyncio
async def test_no_business_type_transfers_to_human(orchestrator: Orchestrator) -> None:
    """意图无 business_type 映射时走转人工。"""
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "unknown_intent",
        "confidence": 0.6,
    }
    context = AgentContext(user_id="u1", conversation_id="c1")
    result = await orchestrator.process("帮我订机票", context)

    assert result.get("transfer_to_human") is True
    assert context.state == AgentState.TRANSFERRED


@pytest.mark.asyncio
async def test_confirmed_resumes_execution(orchestrator: Orchestrator) -> None:
    """确认恢复路径：跳过意图识别直接执行工具。"""
    mock_tool = AsyncMock()
    mock_tool.execute.return_value = ToolResult.text("ok")
    orchestrator.tool_registry.get_tool.return_value = mock_tool

    context = AgentContext(
        user_id="u1",
        conversation_id="c1",
        confirmed=True,
        business_type="leave",
        slots={"leave_type": "年假", "start_date": "2026-09-20", "end_date": "2026-09-21"},
    )
    result = await orchestrator.process("", context)

    assert context.state == AgentState.COMPLETED
    assert "操作已完成" in result["content"]
    orchestrator.intent_recognizer.recognize.assert_not_called()


@pytest.mark.asyncio
async def test_confirmed_tool_error_transfers(orchestrator: Orchestrator) -> None:
    """确认恢复路径中工具报错走转人工并携带 transfer_task_data。"""
    mock_tool = AsyncMock()
    mock_tool.execute.return_value = ToolResult.error("服务不可用")
    orchestrator.tool_registry.get_tool.return_value = mock_tool

    context = AgentContext(
        user_id="u1",
        conversation_id="c1",
        confirmed=True,
        business_type="leave",
        slots={"leave_type": "年假", "start_date": "2026-09-20", "end_date": "2026-09-21"},
    )
    result = await orchestrator.process("", context)

    assert context.state == AgentState.TRANSFERRED
    assert result.get("transfer_to_human") is True
    assert result.get("transfer_task_data") is not None
    assert result["transfer_task_data"]["business_type"] == "leave"
    assert result["transfer_task_data"]["user_id"] == "u1"
    assert result["transfer_task_data"]["slots"] == context.slots


@pytest.mark.asyncio
async def test_normal_flow_tool_error_transfers_with_task_data(
    orchestrator: Orchestrator,
) -> None:
    """正常流程中工具报错也应携带 transfer_task_data。"""
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "leave_request",
        "confidence": 0.95,
    }
    orchestrator.slot_extractor.extract.return_value = {}

    mock_validation = MagicMock()
    mock_validation.passed = True
    mock_validation.errors = []
    orchestrator.rule_engine.validate.return_value = mock_validation

    mock_tool = AsyncMock()
    mock_tool.execute.return_value = ToolResult.error("OA 系统超时")
    orchestrator.tool_registry.get_tool.return_value = mock_tool

    context = AgentContext(
        user_id="u1",
        conversation_id="c1",
        slots={"leave_type": "年假", "start_date": "2026-09-20", "end_date": "2026-09-21"},
    )
    result = await orchestrator.process("请年假", context)

    assert context.state == AgentState.TRANSFERRED
    assert result.get("transfer_to_human") is True
    assert result.get("transfer_task_data") is not None
    assert result["transfer_task_data"]["business_type"] == "leave"