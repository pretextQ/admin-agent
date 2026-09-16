# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""槽位抽取模块。"""

from __future__ import annotations

import re
from typing import Any, Optional

import structlog

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


class SlotExtractor:
    """槽位抽取器。"""

    def __init__(self, llm_client: Any = None) -> None:
        self._llm = llm_client

    async def extract(
        self,
        message: str,
        intent: str,
        business_type: Optional[str] = None,
        existing_slots: Optional[dict[str, Any]] = None,
        attachments: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """从消息中抽取槽位。"""
        existing = existing_slots or {}
        if self._llm is None:
            return self._fallback_extract(message, business_type, existing)
        return existing

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
        return slots

    def get_required_slots(self, business_type: str) -> list[str]:
        """获取业务类型所需的必填槽位。"""
        return SLOT_SCHEMAS.get(business_type, [])

    def check_completeness(self, business_type: str, slots: dict[str, Any]) -> list[str]:
        """检查槽位完整性，返回缺失列表。"""
        required = self.get_required_slots(business_type)
        return [s for s in required if s not in slots or slots[s] is None]