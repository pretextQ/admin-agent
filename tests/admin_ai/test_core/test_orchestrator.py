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


def _llm_stub(text_or_error: object) -> Any:
    """构造 LLM 网关桩：`chat()` 返回固定文本，或抛出指定异常。

    网关接口为 `await gateway.chat(messages, purpose=..., session_key=...) -> str`。
    """
    llm = AsyncMock()
    if isinstance(text_or_error, Exception):
        llm.chat.side_effect = text_or_error
    else:
        llm.chat.return_value = text_or_error
    return llm


def _orchestrator_with_tool(llm_client: Any = None) -> Orchestrator:
    """构造注册了"执行成功"工具的编排器，用于验证回复生成。"""
    slot_extractor = MagicMock()
    slot_extractor.check_completeness = MagicMock(return_value=[])
    tool_registry = MagicMock()
    mock_tool = AsyncMock()
    mock_tool.execute.return_value = ToolResult.text("ok")
    tool_registry.get_tool.return_value = mock_tool
    return Orchestrator(
        intent_recognizer=MagicMock(),
        slot_extractor=slot_extractor,
        dialog_manager=MagicMock(),
        rule_engine=MagicMock(),
        tool_registry=tool_registry,
        llm_client=llm_client,
        model="deepseek-flash",
    )


def _confirmed_leave_context() -> AgentContext:
    return AgentContext(
        user_id="u1",
        conversation_id="c1",
        confirmed=True,
        business_type="leave",
        slots={"leave_type": "年假", "start_date": "2026-09-20", "end_date": "2026-09-21"},
    )


@pytest.mark.asyncio
async def test_tool_success_reply_generated_by_llm() -> None:
    """接入 LLM 后，执行成功的回复应由 LLM 生成，而不是固定模板。"""
    orchestrator = _orchestrator_with_tool(_llm_stub("您的年假申请已提交，9月20日至21日共2天。"))
    result = await orchestrator.process("", _confirmed_leave_context())

    assert result["content"] == "您的年假申请已提交，9月20日至21日共2天。"
    assert "操作已完成" not in result["content"]


@pytest.mark.asyncio
async def test_tool_success_reply_falls_back_without_llm() -> None:
    """未配置 LLM 时回退固定模板（保持既有行为）。"""
    orchestrator = _orchestrator_with_tool(None)
    result = await orchestrator.process("", _confirmed_leave_context())

    assert result["content"] == "操作已完成"


@pytest.mark.asyncio
async def test_tool_success_reply_falls_back_on_llm_error() -> None:
    """LLM 调用失败时回退模板，且不阻断主流程（任务仍算完成）。"""
    orchestrator = _orchestrator_with_tool(_llm_stub(RuntimeError("api down")))
    context = _confirmed_leave_context()
    result = await orchestrator.process("", context)

    assert result["content"] == "操作已完成"
    assert context.state == AgentState.COMPLETED


@pytest.mark.asyncio
async def test_llm_reply_prompt_receives_execution_result() -> None:
    """发给 LLM 的提示词应包含业务数据与工具执行结果，便于生成准确回复。"""
    llm = _llm_stub("好的")
    orchestrator = _orchestrator_with_tool(llm)
    await orchestrator.process("", _confirmed_leave_context())

    prompt = llm.chat.call_args.kwargs["messages"][0]["content"]
    assert "年假" in prompt  # 业务槽位
    assert "ok" in prompt  # 工具返回内容


@pytest.mark.asyncio
async def test_tool_receipt_id_returned_for_task() -> None:
    """工具返回的受理编号要随结果回传，API 层才能落到任务的 external_id。

    回复里已经把「受理编号 MOCK-xxxx」告诉了用户，用户就得能拿这个编号查进度。
    """
    orchestrator = _orchestrator_with_tool(None)
    orchestrator.tool_registry.get_tool.return_value.execute.return_value = ToolResult.text(
        str({"code": 0, "data": {"external_id": "MOCK-2046C424"}})
    )
    result = await orchestrator.process("", _confirmed_leave_context())

    assert result["external_id"] == "MOCK-2046C424"


@pytest.mark.asyncio
async def test_no_receipt_id_when_tool_returns_plain_text() -> None:
    """下游没给编号时不硬塞 external_id 字段。"""
    orchestrator = _orchestrator_with_tool(None)
    result = await orchestrator.process("", _confirmed_leave_context())

    assert "external_id" not in result


@pytest.mark.asyncio
async def test_orchestrator_never_logs_user_message() -> None:
    """应用日志不得写入用户消息原文。

    SECURITY §6.2 要求「日志禁止写入 L3/L4 明文」——对话内容属 L3，
    一旦进日志就脱离了 LLM 脱敏层的保护范围。
    """
    import json

    from structlog.testing import capture_logs

    orchestrator = _orchestrator_with_tool(None)
    orchestrator.intent_recognizer.recognize = AsyncMock(
        return_value={"intent": "policy_query", "confidence": 0.9}
    )
    context = AgentContext(user_id="u1", conversation_id="c1")

    with capture_logs() as logs:
        await orchestrator.process("我的手机号是 13812345678，帮我查制度", context)

    dumped = json.dumps(logs, ensure_ascii=False, default=str)
    assert "13812345678" not in dumped, "日志中出现用户原文（L3 明文禁令）"
    assert "帮我查制度" not in dumped, "日志中出现用户原文（L3 明文禁令）"


# ------------------------------------------------------- 状态查询（场景 REQ-03）


@pytest.mark.asyncio
async def test_status_query_marks_for_api_layer(orchestrator: Orchestrator) -> None:
    """状态查询不在编排器内查库：返回标记与查询类型，由 API 层用真实结果填充。"""
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "status_query",
        "confidence": 0.95,
    }
    context = AgentContext(user_id="u1", conversation_id="c1")
    result = await orchestrator.process("我的报销到哪一步了", context)

    assert result.get("needs_status_query") is True
    assert result["status_query"]["query_type"] == "报销状态"
    assert context.state == AgentState.COMPLETED
    # 查询参数不得写进 slots：slots 会持久化并随下轮业务混入任务 data
    assert context.slots == {}
    # 状态查询是只读的，不得走工具调用
    orchestrator.tool_registry.get_tool.assert_not_called()
    orchestrator.rule_engine.validate.assert_not_called()


@pytest.mark.asyncio
async def test_status_query_without_type_asks(orchestrator: Orchestrator) -> None:
    """未指定查询类型时追问，不猜某一类（场景 03 TC008）。"""
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "status_query",
        "confidence": 0.9,
    }
    context = AgentContext(user_id="u1", conversation_id="c1")
    result = await orchestrator.process("查询状态", context)

    assert result.get("needs_status_query") is not True
    assert result.get("requires_action") is True
    assert result.get("missing_slots") == ["query_type"]
    assert "查询哪方面" in result["content"]
    assert context.awaiting_slots is True
    assert context.state == AgentState.SLOT_FILLING


@pytest.mark.asyncio
async def test_status_query_resumes_without_reintent(orchestrator: Orchestrator) -> None:
    """追问后用户只回「假期余额」：不再识别意图，直接按状态查询继续。

    status_query 没有 business_type，若按旧口径判续填会退回意图识别，
    把补充的类型当成新请求（历史上其他业务有同类前科）。
    """
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "other",
        "confidence": 0.3,
    }
    context = AgentContext(
        user_id="u1",
        conversation_id="c1",
        intent="status_query",
        business_type=None,
        awaiting_slots=True,
    )
    result = await orchestrator.process("假期余额", context)

    orchestrator.intent_recognizer.recognize.assert_not_called()
    assert result.get("needs_status_query") is True
    assert result["status_query"]["query_type"] == "假期余额"
    assert context.awaiting_slots is False


@pytest.mark.asyncio
async def test_status_query_extracts_task_ref(orchestrator: Orchestrator) -> None:
    """消息里带单据号时一并带出，供 API 层精确查询。"""
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "status_query",
        "confidence": 0.95,
    }
    context = AgentContext(user_id="u1", conversation_id="c1")
    result = await orchestrator.process("查询任务 MOCK-2046C424 的状态", context)

    assert result["status_query"]["task_id"] == "MOCK-2046C424"


@pytest.mark.asyncio
async def test_status_query_uses_llm_hint(orchestrator: Orchestrator) -> None:
    """意图识别给出的 query_type 优先于关键词推断。"""
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "status_query",
        "query_type": "任务进度",
        "confidence": 0.95,
    }
    context = AgentContext(user_id="u1", conversation_id="c1")
    result = await orchestrator.process("我的报销到哪一步了", context)

    assert result["status_query"]["query_type"] == "任务进度"


@pytest.mark.asyncio
async def test_status_query_creates_no_task(orchestrator: Orchestrator) -> None:
    """状态查询不得返回 task_type，否则 API 层会为只读查询建一条任务记录。"""
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "status_query",
        "confidence": 0.95,
    }
    context = AgentContext(user_id="u1", conversation_id="c1")
    result = await orchestrator.process("我的任务进度", context)

    assert result.get("task_type") is None
    assert result.get("slots") is None


@pytest.mark.asyncio
async def test_status_query_ignores_stale_query_type(orchestrator: Orchestrator) -> None:
    """上一轮的查询类型不得影响本轮：用户改问另一类时按新问题回答。"""
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "status_query",
        "confidence": 0.95,
    }
    context = AgentContext(
        user_id="u1",
        conversation_id="c1",
        slots={"query_type": "报销状态", "task_id": "MOCK-OLD"},
    )
    result = await orchestrator.process("我还剩几天年假", context)

    assert result["status_query"]["query_type"] == "假期余额"
    # 单据号只在本轮消息里出现才有效，否则会退化成上一轮的精确查询
    assert result["status_query"]["task_id"] is None


@pytest.mark.asyncio
async def test_status_query_resume_falls_back_to_new_intent(
    orchestrator: Orchestrator,
) -> None:
    """等查询类型时用户改口提新请求：不该继续追问类型，应按新请求重新识别。"""
    orchestrator.intent_recognizer.recognize.return_value = {
        "intent": "leave_request",
        "confidence": 0.95,
    }
    orchestrator.slot_extractor.extract.return_value = {}
    orchestrator.slot_extractor.check_completeness.return_value = ["start_date"]

    context = AgentContext(
        user_id="u1", conversation_id="c1", intent="status_query", awaiting_slots=True
    )
    result = await orchestrator.process("我要请假", context)

    orchestrator.intent_recognizer.recognize.assert_called_once()
    assert result.get("needs_status_query") is not True
    assert result.get("missing_slots") == ["start_date"]
