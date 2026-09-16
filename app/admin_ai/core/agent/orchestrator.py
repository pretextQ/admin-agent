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

logger = structlog.get_logger(__name__)


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
    """智能体编排器。"""

    def __init__(
        self,
        intent_recognizer: IntentRecognizer,
        slot_extractor: SlotExtractor,
        dialog_manager: DialogManager,
    ) -> None:
        self.intent_recognizer = intent_recognizer
        self.slot_extractor = slot_extractor
        self.dialog_manager = dialog_manager

    async def process(
        self,
        user_message: str,
        context: AgentContext,
        attachments: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """处理用户消息的主流程。"""
        try:
            # 1. 意图识别
            intent_result = await self.intent_recognizer.recognize(user_message)
            context.intent = intent_result["intent"]
            context.business_type = intent_result.get("business_type")

            # 2. 问候直接回复
            if context.intent == "greeting":
                return {"content": "你好，我是行政助手，请问有什么可以帮您？"}

            # 3. 制度查询走 RAG
            if context.intent == "policy_query":
                return {"content": "正在为您查询相关制度...", "needs_rag": True}

            # 4. 槽位抽取
            slots = await self.slot_extractor.extract(
                user_message, context.intent, context.business_type, context.slots, attachments
            )
            context.slots.update(slots)

            # 5. 检查完整性
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
                }
                return {
                    "content": questions.get(missing[0], f"请提供{missing[0]}信息"),
                    "requires_action": True,
                }

            # 6. 风险评估
            high_risk = ["expense", "seal"]
            if context.business_type in high_risk and not context.confirmed:
                return {
                    "content": "请确认以下操作",
                    "card_data": {
                        "type": "confirmation",
                        "data": context.slots,
                        "warning": "此操作将产生重要影响，请仔细核对",
                    },
                    "requires_action": True,
                }

            # 7. 执行
            return {
                "content": f"操作已完成：{context.business_type}",
                "task_id": "task_demo",
            }

        except Exception as e:
            logger.error("处理异常", error=str(e))
            return {"content": "抱歉，处理过程中出现错误，请稍后重试"}