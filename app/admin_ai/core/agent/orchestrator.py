# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""智能体编排器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog

from app.admin_ai.core.agent.dialog import DialogManager
from app.admin_ai.core.agent.intent import IntentRecognizer
from app.admin_ai.core.agent.slot import SlotExtractor
from app.admin_ai.core.rules.engine import RuleEngine
from app.admin_ai.core.tools.registry import ToolRegistry

logger = structlog.get_logger(__name__)

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


class Orchestrator:
    """智能体编排器。

    职责：
    1. 协调意图识别、槽位抽取、规则校验、工具调用
    2. 管理对话状态流转
    3. 处理高风险确认流程
    """

    def __init__(
        self,
        intent_recognizer: IntentRecognizer,
        slot_extractor: SlotExtractor,
        dialog_manager: DialogManager,
        rule_engine: RuleEngine,
        tool_registry: ToolRegistry,
    ) -> None:
        self.intent_recognizer = intent_recognizer
        self.slot_extractor = slot_extractor
        self.dialog_manager = dialog_manager
        self.rule_engine = rule_engine
        self.tool_registry = tool_registry

    async def process(
        self,
        user_message: str,
        context: AgentContext,
        attachments: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """处理用户消息的主流程。"""
        try:
            # 1. 意图识别
            logger.info("开始处理", user_id=context.user_id, message=user_message[:50])
            context.state = AgentState.INTENT_RECOGNIZING
            intent_result = await self.intent_recognizer.recognize(user_message)
            context.intent = intent_result["intent"]
            context.business_type = INTENT_TO_BUSINESS.get(context.intent)

            # 2. 问候直接回复
            if context.intent == "greeting":
                context.state = AgentState.COMPLETED
                return {"content": "你好，我是行政助手，请问有什么可以帮您？"}

            # 3. 制度查询走 RAG
            if context.intent == "policy_query":
                context.state = AgentState.COMPLETED
                return {"content": "正在为您查询相关制度...", "needs_rag": True}

            # 4. 状态查询
            if context.intent == "status_query":
                context.state = AgentState.COMPLETED
                return {"content": "正在为您查询状态...", "needs_status_query": True}

            # 5. 槽位抽取
            context.state = AgentState.SLOT_FILLING
            slots = await self.slot_extractor.extract(
                user_message, context.intent, context.business_type, context.slots, attachments
            )
            context.slots.update(slots)

            # 6. 检查完整性
            missing = self.slot_extractor.check_completeness(
                context.business_type or "", context.slots
            )
            if missing:
                questions = {
                    "leave_type": "请问您要请什么假？（年假/调休/事假/病假）",
                    "start_date": "请问开始日期是哪天？",
                    "end_date": "请问结束日期是哪天？",
                    "amount": "请问金额是多少？",
                    "destination": "请问目的地是哪里？",
                    "item_name": "请问您要领用什么物资？",
                    "quantity": "请问需要多少？",
                    "document_name": "请问需要盖章的文件名称是什么？",
                    "seal_type": "请问需要什么类型的印章？（公章/合同章/财务章/法人章）",
                    "certificate_type": "请问需要开具什么证明？（在职证明/收入证明/离职证明）",
                    "purpose": "请问用途是什么？",
                }
                return {
                    "content": questions.get(missing[0], f"请提供{missing[0]}信息"),
                    "requires_action": True,
                }

            # 7. 规则校验
            context.state = AgentState.VALIDATING
            validation = await self.rule_engine.validate(
                context.business_type or "", context.slots, context.user_id
            )
            if not validation.passed:
                return {"content": "校验不通过：" + "；".join(validation.errors)}

            # 8. 风险评估与确认
            context.state = AgentState.CONFIRMING
            if context.business_type in HIGH_RISK_TYPES and not context.confirmed:
                context.risk_level = "high"
                return {
                    "content": "请确认以下操作",
                    "card_data": {
                        "type": "confirmation",
                        "business_type": context.business_type,
                        "data": context.slots,
                        "warning": "此操作将产生重要影响，请仔细核对",
                    },
                    "requires_action": True,
                }

            # 9. 执行工具调用
            context.state = AgentState.EXECUTING
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
                        "content": f"系统暂时无法完成您的请求，已为您转接人工客服。错误：{result.content}",
                        "transfer_to_human": True,
                    }

            # 10. 完成
            context.state = AgentState.COMPLETED
            return {
                "content": f"操作已完成",
                "task_type": context.business_type,
                "slots": context.slots,
            }

        except Exception as e:
            logger.error("处理异常", error=str(e), context=context)
            context.state = AgentState.FAILED
            return {"content": "抱歉，处理过程中出现错误，请稍后重试"}