# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""槽位抽取模块。"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

import structlog

from app.admin_ai.core.agent.prompt import SLOT_PROMPT

logger = structlog.get_logger(__name__)

SLOT_SCHEMAS = {
    "leave": ["leave_type", "start_date", "end_date"],
    "expense": ["expense_type", "amount", "invoice"],
    "travel": ["destination", "start_date", "end_date", "purpose"],
    "meeting_room": ["date", "start_time", "end_time", "capacity"],
    "vehicle": ["date", "start_time", "end_time", "destination"],
    "material": ["item_name", "quantity"],
    "asset": ["asset_name", "quantity", "action"],
    "seal": ["document_name", "seal_type", "copies"],
    "certificate": ["certificate_type", "purpose"],
    "onboarding": ["employee_name", "onboard_date", "action"],
}

# 回退抽取使用的枚举关键词
SLOT_ENUM_KEYWORDS: dict[str, list[str]] = {
    "leave_type": ["年假", "调休", "事假", "病假"],
    "expense_type": ["酒店", "餐饮", "交通", "办公用品", "差旅"],
    "seal_type": ["公章", "合同章", "财务章", "法人章"],
    "certificate_type": ["在职证明", "收入证明", "离职证明"],
}

# 数量：3个 / 2件 / 5台 / 1份 ...
QUANTITY_PATTERN = re.compile(r"(\d+)\s*(?:个|件|台|箱|支|本|套|份|张|瓶|包)")
# 金额：500元 / 500.5 元
AMOUNT_PATTERN = re.compile(r"(\d+(?:\.\d+)?)\s*元")


class SlotExtractor:
    """槽位抽取器。"""

    def __init__(self, llm_client: Any = None, model: str = "gpt-4o-mini") -> None:
        self._llm = llm_client
        self._model = model

    async def extract(
        self,
        message: str,
        intent: str,
        business_type: Optional[str] = None,
        existing_slots: Optional[dict[str, Any]] = None,
        attachments: Optional[list[str]] = None,
        session_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """从消息中抽取槽位，并合并已有槽位。

        始终先执行规则回退抽取（成本低、保证有基础结果），
        若 LLM 可用则用其结构化结果覆盖，LLM 失败时静默降级。
        `session_key` 用于脱敏占位符的会话内一致性。
        """
        existing = dict(existing_slots or {})
        fallback = self._fallback_extract(message, business_type, existing)

        if self._llm is None or not business_type:
            return self._apply_attachment_slots(fallback, business_type, attachments)

        try:
            llm_slots = await self._llm_extract(message, business_type, existing, session_key)
        except Exception as exc:  # LLM 不可用时不得阻断主流程（含 L4 拦截与涉密业务）
            logger.warning("槽位抽取未走 LLM，回退规则抽取", error=str(exc))
            fallback = self._apply_attachment_slots(fallback, business_type, attachments)
            return fallback

        merged = {**fallback, **llm_slots}
        return self._apply_attachment_slots(merged, business_type, attachments)

    @staticmethod
    def _apply_attachment_slots(
        slots: dict[str, Any],
        business_type: Optional[str],
        attachments: Optional[list[str]],
    ) -> dict[str, Any]:
        """把附件映射到对应槽位（如报销的发票凭证）。"""
        if business_type == "expense" and attachments and "invoice" not in slots:
            slots["invoice"] = attachments[0]
        return slots

    async def _llm_extract(
        self,
        message: str,
        business_type: str,
        existing: dict[str, Any],
        session_key: Optional[str] = None,
    ) -> dict[str, Any]:
        """调用 LLM 抽取槽位（经统一网关脱敏；命中 L4 会抛 LLMCallBlockedError 由上层回退）。"""
        schema = self.get_required_slots(business_type)
        prompt = SLOT_PROMPT.format(
            slot_schema=json.dumps({business_type: schema}, ensure_ascii=False)
        )
        content = await self._llm.chat(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": message},
            ],
            purpose="slot",
            session_key=session_key,
            business_type=business_type,
            temperature=0,
            response_format={"type": "json_object"},
        )
        data = json.loads(content)
        slots = data.get("slots", {})
        if not isinstance(slots, dict):
            return {}
        return {key: value for key, value in slots.items() if value is not None}

    def _fallback_extract(
        self,
        message: str,
        business_type: Optional[str],
        existing: dict[str, Any],
    ) -> dict[str, Any]:
        """规则回退抽取。"""
        slots = dict(existing)

        date_match = re.findall(r"\d{4}-\d{2}-\d{2}", message)
        if date_match:
            if "start_date" not in slots:
                slots["start_date"] = date_match[0]
            if len(date_match) > 1 and "end_date" not in slots:
                slots["end_date"] = date_match[1]

        days_match = re.search(r"(\d+)\s*天", message)
        if days_match and "days" not in slots:
            slots["days"] = int(days_match.group(1))

        quantity_match = QUANTITY_PATTERN.search(message)
        if quantity_match and "quantity" not in slots:
            value = int(quantity_match.group(1))
            if business_type == "seal":
                # 用印业务的份数槽位
                slots["copies"] = value
            else:
                slots["quantity"] = value

        # 单据名：《劳动合同》 -> document_name=劳动合同
        doc_match = re.search(r"《([^《》]+)》", message)
        if doc_match and "document_name" not in slots:
            slots["document_name"] = doc_match.group(1)

        amount_match = AMOUNT_PATTERN.search(message)
        if amount_match and "amount" not in slots:
            slots["amount"] = float(amount_match.group(1))

        for slot_name, keywords in SLOT_ENUM_KEYWORDS.items():
            if slot_name in slots:
                continue
            for keyword in keywords:
                if keyword in message:
                    slots[slot_name] = keyword
                    break

        return slots

    def get_required_slots(self, business_type: str) -> list[str]:
        """获取业务类型所需的必填槽位。"""
        return SLOT_SCHEMAS.get(business_type, [])

    def check_completeness(self, business_type: str, slots: dict[str, Any]) -> list[str]:
        """检查槽位完整性，返回缺失列表。"""
        required = self.get_required_slots(business_type)
        return [s for s in required if s not in slots or slots[s] is None]
