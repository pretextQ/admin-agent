# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""意图识别模块。"""

from __future__ import annotations

import json
from typing import Any, Optional

import structlog

from app.admin_ai.core.agent.prompt import INTENT_PROMPT

logger = structlog.get_logger(__name__)

VALID_INTENTS = {
    "policy_query", "meeting_room_booking", "status_query",
    "material_request", "leave_request", "certificate_request",
    "expense_request", "travel_request", "asset_request",
    "seal_request", "onboarding_request", "greeting", "other",
}


class IntentRecognizer:
    """意图识别器。"""

    def __init__(self, llm_client: Any = None, model: str = "gpt-4o-mini") -> None:
        self._llm = llm_client
        self._model = model

    async def recognize(
        self,
        message: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """识别用户意图。"""
        if self._llm is None:
            return self._fallback_recognize(message)

        try:
            response = await self._llm.chat.completions.create(
                model=self._model,
                messages=[
                    {"role": "system", "content": INTENT_PROMPT},
                    {"role": "user", "content": message},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            intent = result.get("intent", "other")
            if intent not in VALID_INTENTS:
                intent = "other"
            result["intent"] = intent
            return result
        except Exception as e:
            logger.error("意图识别失败", error=str(e))
            return {"intent": "other", "confidence": 0.0}

    def _fallback_recognize(self, message: str) -> dict[str, Any]:
        """无 LLM 时的规则回退。"""
        keywords = {
            "请假": "leave_request",
            "报销": "expense_request",
            "会议室": "meeting_room_booking",
            "物资": "material_request",
            "证明": "certificate_request",
            "差旅": "travel_request",
            "资产": "asset_request",
            "盖章": "seal_request",
            "入职": "onboarding_request",
            "离职": "onboarding_request",
            "你好": "greeting",
        }
        for keyword, intent in keywords.items():
            if keyword in message:
                return {"intent": intent, "confidence": 0.7}
        return {"intent": "other", "confidence": 0.5}