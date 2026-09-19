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

@pytest.mark.asyncio
async def test_awaiting_slots_skips_intent_recognition(orchestrator: Orchestrator) -> None:
    """续填槽位时不重新识别意图，直接执行工具。"""
    orchestrator.slot_extractor.extract.return_value = {}
    orchestrator.slot_extractor.check_completeness.return_value = []
    mock_tool = AsyncMock()
    mock_tool.execute.return_value = ToolResult.text("ok")
    orchestrator.tool_registry.get_tool.return_value = mock_tool
    validation = MagicMock()
    validation.passed = True
    validation.errors = []
    orchestrator.rule_engine.validate.return_value = validation

    context = AgentContext(
        user_id="u1",
        conversation_id="c1",
        business_type="leave",
        intent="leave_request",
        awaiting_slots=True,
        slots={"leave_type": "年假", "start_date": "2026-09-20", "end_date": "2026-09-21"},
    )
    result = await orchestrator.process("年假 2026-09-20 到 2026-09-21", context)

    orchestrator.intent_recognizer.recognize.assert_not_called()
    assert context.state == AgentState.COMPLETED
    assert "操作已完成" in result["content"]
    assert context.awaiting_slots is False


@pytest.mark.asyncio
async def test_missing_slots_sets_awaiting_slots(orchestrator: Orchestrator) -> None:
    """槽位缺失时返回追问并标记 awaiting_slots。"""
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "leave_request",
        "confidence": 0.95,
    }
    orchestrator.slot_extractor.extract.return_value = {}
    orchestrator.slot_extractor.check_completeness.return_value = ["start_date"]

    context = AgentContext(user_id="u1", conversation_id="c1")
    result = await orchestrator.process("我要请假", context)

    assert result.get("requires_action") is True
    assert context.awaiting_slots is True
    assert "开始日期" in result["content"]
    assert result.get("missing_slots") == ["start_date"]


@pytest.mark.asyncio
async def test_confirmation_card_uses_spec_fields(orchestrator: Orchestrator) -> None:
    """高风险确认卡片符合 API 规格字段。"""
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "expense_request",
        "confidence": 0.95,
    }
    orchestrator.slot_extractor.extract.return_value = {}
    orchestrator.slot_extractor.check_completeness.return_value = []
    validation = MagicMock()
    validation.passed = True
    validation.errors = []
    orchestrator.rule_engine.validate.return_value = validation

    context = AgentContext(user_id="u1", conversation_id="c1")
    result = await orchestrator.process("我要报销 500 元", context)

    card = result["card_data"]
    assert card["type"] == "confirmation"
    assert card["data"] == context.slots
    assert card["title"]
    assert card["warning"]
    assert card["actions"] == ["confirm", "cancel"]
    assert result["requires_action"] is True


@pytest.mark.asyncio
async def test_policy_query_without_retriever_flags_rag(orchestrator: Orchestrator) -> None:
    """未接入检索器时制度查询仍返回 needs_rag 标记。"""
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "policy_query",
        "confidence": 0.9,
    }
    context = AgentContext(user_id="u1", conversation_id="c1")
    result = await orchestrator.process("报销标准是什么", context)

    assert result.get("needs_rag") is True
    assert context.state == AgentState.COMPLETED


@pytest.mark.asyncio
async def test_policy_query_with_retriever_returns_citations(
    orchestrator: Orchestrator,
) -> None:
    """接入检索器后制度查询返回带引用来源的回答。"""
    orchestrator.retriever = AsyncMock()
    orchestrator.retriever.retrieve.return_value = [
        {
            "content": "年假天数按司龄计算，满一年五天，满十年十天。",
            "metadata": {"title": "考勤制度", "source_uri": "hr/attendance.pdf"},
            "distance": 0.2,
        },
    ]
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "policy_query",
        "confidence": 0.9,
    }
    context = AgentContext(user_id="u1", conversation_id="c1")
    result = await orchestrator.process("年假怎么算", context)

    retriever = orchestrator.retriever
    retriever.retrieve.assert_awaited_once()
    assert "《考勤制度》" in result["content"]
    assert "来源：hr/attendance.pdf" in result["content"]
    assert result["rag_sources"][0]["title"] == "考勤制度"


@pytest.mark.asyncio
async def test_policy_query_retriever_empty_falls_back(orchestrator: Orchestrator) -> None:
    """检索器无命中时回退 needs_rag 标记。"""
    orchestrator.retriever = AsyncMock()
    orchestrator.retriever.retrieve.return_value = []
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "policy_query",
        "confidence": 0.9,
    }
    context = AgentContext(user_id="u1", conversation_id="c1")
    result = await orchestrator.process("报销标准是什么", context)

    assert result.get("needs_rag") is True


def test_compose_policy_answer_formats_citations() -> None:
    """引用拼装：长内容截断、来源去重。"""
    from app.admin_ai.core.agent.orchestrator import compose_policy_answer

    docs = [
        {"content": "很长" * 200, "metadata": {"title": "A", "source_uri": "a.pdf"}},
        {"content": "短内容", "metadata": {"title": "B", "source_uri": "a.pdf"}},
    ]
    answer = compose_policy_answer(docs)
    assert "《A》" in answer and "《B》" in answer
    assert "…" in answer
    assert answer.count("a.pdf") == 1
