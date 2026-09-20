# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""智能体编排器。"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog

from app.admin_ai.core.agent.dialog import DialogManager
from app.admin_ai.core.agent.intent import IntentRecognizer
from app.admin_ai.core.agent.prompt import REPLY_PROMPT
from app.admin_ai.core.agent.slot import SlotExtractor
from app.admin_ai.core.rules.engine import RuleEngine
from app.admin_ai.core.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)


def compose_policy_answer(docs: list[dict[str, Any]]) -> str:
    """把 RAG 检索结果拼装为带引用来源的制度问答回复。

    未接回复生成 LLM 前，先用模板保证回答可溯源。
    """
    lines = ["根据知识库检索，为您找到以下相关制度内容："]
    sources: list[str] = []
    for i, doc in enumerate(docs, 1):
        meta = doc.get("metadata") or {}
        title = meta.get("title") or "未命名文档"
        content = (doc.get("content") or "").strip()
        excerpt = content[:200] + ("…" if len(content) > 200 else "")
        lines.append(f"{i}. 《{title}》：{excerpt}")
        source_uri = meta.get("source_uri")
        if source_uri:
            sources.append(source_uri)
    if sources:
        lines.append(f"来源：{'；'.join(dict.fromkeys(sources))}")
    return "\n".join(lines)


# 意图到业务类型的映射
INTENT_TO_BUSINESS = {
    "leave_request": "leave",
    "expense_request": "expense",
    "travel_request": "travel",
    "meeting_room_booking": "meeting_room",
    "material_request": "material",
    "asset_request": "asset",
    "seal_request": "seal",
    "certificate_request": "certificate",
    "onboarding_request": "onboarding",
}

# 高风险业务类型
HIGH_RISK_TYPES = {"expense", "seal"}

# 缺失槽位对应的追问话术
SLOT_QUESTIONS = {
    "leave_type": "请问您要请什么假？（年假/调休/事假/病假）",
    "expense_type": "请问是什么类型的费用？（酒店/餐饮/交通/差旅）",
    "amount": "请问金额是多少？",
    "invoice": "请上传对应的发票附件。",
    "start_date": "请问开始日期是哪天？",
    "end_date": "请问结束日期是哪天？",
    "destination": "请问目的地是哪里？",
    "purpose": "请问用途是什么？",
    "item_name": "请问您要领用什么物资？",
    "quantity": "请问需要多少？",
    "document_name": "请问需要盖章的文件名称是什么？",
    "seal_type": "请问需要什么类型的印章？（公章/合同章/财务章/法人章）",
    "copies": "请问需要盖章几份？",
    "certificate_type": "请问需要开具什么证明？（在职证明/收入证明/离职证明）",
    "date": "请问是哪一天？",
    "start_time": "请问开始时间是？",
    "end_time": "请问结束时间是？",
    "capacity": "请问需要容纳多少人？",
    "asset_name": "请问需要哪种资产？",
    "action": "请问是领用还是归还？",
    "employee_name": "请问员工的姓名是？",
    "onboard_date": "请问入职/离职日期是哪天？",
}


class AgentState(str, Enum):
    """智能体状态。"""
    IDLE = "idle"
    INTENT_RECOGNIZING = "intent_recognizing"
    SLOT_FILLING = "slot_filling"
    VALIDATING = "validating"
    EXECUTING = "executing"
    CONFIRMING = "confirming"
    COMPLETED = "completed"
    FAILED = "failed"
    TRANSFERRED = "transferred"


@dataclass
class AgentContext:
    """智能体上下文。"""
    user_id: str
    conversation_id: str
    state: AgentState = AgentState.IDLE
    intent: Optional[str] = None
    business_type: Optional[str] = None
    slots: dict[str, Any] = field(default_factory=dict)
    rag_results: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    risk_level: str = "low"
    confirmed: bool = False
    awaiting_slots: bool = False


class Orchestrator:
    """智能体编排器。

    职责：
    1. 协调意图识别、槽位抽取、规则校验、工具调用
    2. 管理对话状态流转
    3. 处理高风险确认流程与多轮槽位续填
    """

    def __init__(
        self,
        intent_recognizer: IntentRecognizer,
        slot_extractor: SlotExtractor,
        dialog_manager: DialogManager,
        rule_engine: RuleEngine,
        tool_registry: ToolRegistry,
        retriever: Any = None,
        llm_client: Any = None,
        model: str = "gpt-4o-mini",
    ) -> None:
        self.intent_recognizer = intent_recognizer
        self.slot_extractor = slot_extractor
        self.dialog_manager = dialog_manager
        self.rule_engine = rule_engine
        self.tool_registry = tool_registry
        self.retriever = retriever
        self._llm = llm_client
        self._model = model

    async def process(
        self,
        user_message: str,
        context: AgentContext,
        attachments: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """处理用户消息的主流程。"""
        try:
            # 0. 确认恢复：跳过意图识别直接从工具执行继续
            if context.confirmed and context.business_type:
                return await self._execute_confirmed(context)

            # 正在续填槽位时，不再重新识别意图，直接在既有业务上继续抽取
            resume_slot_filling = bool(context.business_type and context.awaiting_slots)

            if not resume_slot_filling:
                # 1. 意图识别
                # 只记长度不记内容：对话属 L3 个人数据，SECURITY §6.2 禁止日志写入明文
                logger.info(
                    "开始处理", user_id=context.user_id, message_length=len(user_message)
                )
                context.state = AgentState.INTENT_RECOGNIZING
                intent_result = await self.intent_recognizer.recognize(
                    user_message, session_key=context.conversation_id
                )
                context.intent = intent_result["intent"]
                context.business_type = INTENT_TO_BUSINESS.get(context.intent)

                # 2. 问候直接回复
                if context.intent == "greeting":
                    context.state = AgentState.COMPLETED
                    return {"content": "你好，我是行政助手，请问有什么可以帮您？"}

                # 3. 制度查询走 RAG：检索到则返回带引用的回答，否则交由上层处理
                if context.intent == "policy_query":
                    context.state = AgentState.COMPLETED
                    if self.retriever is not None:
                        docs = await self.retriever.retrieve(user_message, top_k=3)
                        if docs:
                            return {
                                "content": compose_policy_answer(docs),
                                "rag_sources": [d.get("metadata") or {} for d in docs],
                            }
                    return {"content": "正在为您查询相关制度...", "needs_rag": True}

                # 4. 状态查询
                if context.intent == "status_query":
                    context.state = AgentState.COMPLETED
                    return {"content": "正在为您查询状态...", "needs_status_query": True}

                # 5. 未知意图走转人工
                if context.intent == "other" or (
                    context.business_type is None
                    and context.intent not in ("greeting", "policy_query", "status_query")
                ):
                    context.state = AgentState.TRANSFERRED
                    return {
                        "content": "抱歉，我暂时无法理解您的需求，正在为您转接人工客服。",
                        "transfer_to_human": True,
                    }

            # 6. 槽位抽取
            context.state = AgentState.SLOT_FILLING
            slots = await self.slot_extractor.extract(
                user_message,
                context.intent or "",
                context.business_type,
                context.slots,
                attachments,
                session_key=context.conversation_id,
            )
            context.slots.update(slots)

            # 7. 检查完整性
            missing = self.slot_extractor.check_completeness(
                context.business_type or "", context.slots
            )
            if missing:
                context.awaiting_slots = True
                return {
                    "content": SLOT_QUESTIONS.get(missing[0], f"请提供{missing[0]}信息"),
                    "requires_action": True,
                    "missing_slots": missing,
                }
            context.awaiting_slots = False

            # 8. 规则校验
            context.state = AgentState.VALIDATING
            validation = await self.rule_engine.validate(
                context.business_type or "", context.slots, context.user_id
            )
            if not validation.passed:
                return {"content": "校验不通过：" + "；".join(validation.errors)}

            # 9. 风险评估与确认
            context.state = AgentState.CONFIRMING
            if context.business_type in HIGH_RISK_TYPES and not context.confirmed:
                context.risk_level = "high"
                return {
                    "content": "请确认以下操作",
                    "card_data": {
                        "type": "confirmation",
                        "title": "请确认以下操作",
                        "data": context.slots,
                        "actions": ["confirm", "cancel"],
                        "warning": "此操作将产生重要影响，请仔细核对",
                    },
                    "requires_action": True,
                }

            # 10. 执行工具调用
            return await self._execute_tool(context)

        except Exception as e:
            logger.error("处理异常", error=str(e), context=context)
            context.state = AgentState.FAILED
            return {"content": "抱歉，处理过程中出现错误，请稍后重试"}

    async def _execute_confirmed(self, context: AgentContext) -> dict[str, Any]:
        """确认后恢复执行工具。"""
        context.state = AgentState.EXECUTING
        return await self._execute_tool(context)

    async def _compose_reply(self, context: AgentContext, fallback: str) -> str:
        """把执行结果交给 LLM 转成自然语言；未配置或调用失败时回退模板。

        回复生成属于锦上添花，失败不得影响业务结果，故异常一律降级处理。
        """
        if self._llm is None:
            return fallback
        try:
            tool_output = ""
            if context.tool_calls:
                tool_output = str(context.tool_calls[-1].get("output", ""))
            prompt = REPLY_PROMPT.format(
                intent=context.intent or "",
                slots=json.dumps(context.slots, ensure_ascii=False),
                tool_result=tool_output,
            )
            content = await self._llm.chat(
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": "请生成给用户的回复"},
                ],
                purpose="reply_generation",
                session_key=context.conversation_id,
                business_type=context.business_type,
                temperature=0,
            )
            return (content or "").strip() or fallback
        except Exception as exc:  # noqa: BLE001 - 回复生成失败不影响业务流程
            logger.warning("LLM 回复生成失败，回退模板", error=str(exc))
            return fallback

    async def _execute_tool(self, context: AgentContext) -> dict[str, Any]:
        """执行当前业务对应的工具并返回结果信封。"""
        context.state = AgentState.EXECUTING
        context.awaiting_slots = False
        tool = self.tool_registry.get_tool(context.business_type or "")
        if tool:
            result = await tool.execute(context.slots, context.user_id)
            context.tool_calls.append({
                "tool": context.business_type,
                "input": context.slots,
                "output": result.content,
            })
            if result.is_error:
                context.state = AgentState.TRANSFERRED
                return {
                    "content": (
                        f"系统暂时无法完成您的请求，已为您转接人工客服。错误：{result.content}"
                    ),
                    "transfer_to_human": True,
                    "transfer_task_data": {
                        "business_type": context.business_type,
                        "slots": context.slots,
                        "user_id": context.user_id,
                    },
                }

        context.state = AgentState.COMPLETED
        return {
            "content": await self._compose_reply(context, "操作已完成"),
            "task_type": context.business_type,
            "slots": context.slots,
        }
