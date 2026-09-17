# -*- coding: utf-8 -*-
"""槽位抽取测试。"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.admin_ai.core.agent.slot import SlotExtractor


def _llm_returning(payload: dict[str, Any]) -> MagicMock:
    """构造返回固定 JSON 的 LLM 桩。"""
    message = type("Message", (), {"content": json.dumps(payload, ensure_ascii=False)})()
    choice = type("Choice", (), {"message": message})()
    completion = type("Completion", (), {"choices": [choice]})()
    llm = MagicMock()
    llm.chat.completions.create = AsyncMock(return_value=completion)
    return llm


class TestSlotExtractor:
    """槽位抽取测试。"""

    @pytest.fixture
    def extractor(self) -> SlotExtractor:
        return SlotExtractor(llm_client=None)

    async def test_extract_dates(self, extractor: SlotExtractor) -> None:
        result = await extractor.extract("2026-09-20 到 2026-09-21", "leave", "leave")
        assert result.get("start_date") == "2026-09-20"
        assert result.get("end_date") == "2026-09-21"

    async def test_extract_days(self, extractor: SlotExtractor) -> None:
        result = await extractor.extract("请2天假", "leave", "leave")
        assert result.get("days") == 2

    async def test_get_required_slots(self, extractor: SlotExtractor) -> None:
        slots = extractor.get_required_slots("leave")
        assert "leave_type" in slots
        assert "start_date" in slots
        assert "end_date" in slots

    async def test_check_completeness_missing(self, extractor: SlotExtractor) -> None:
        missing = extractor.check_completeness("leave", {"leave_type": "年假"})
        assert "start_date" in missing
        assert "end_date" in missing

    async def test_check_completeness_complete(self, extractor: SlotExtractor) -> None:
        missing = extractor.check_completeness("leave", {
            "leave_type": "年假", "start_date": "2026-09-20", "end_date": "2026-09-21"
        })
        assert len(missing) == 0


class TestFallbackExtraction:
    """无 LLM 时的规则回退抽取。"""

    async def test_extracts_leave_type(self) -> None:
        extractor = SlotExtractor(llm_client=None)
        result = await extractor.extract("我想请年假", "leave_request", "leave")
        assert result.get("leave_type") == "年假"

    async def test_extracts_quantity_and_amount(self) -> None:
        extractor = SlotExtractor(llm_client=None)
        result = await extractor.extract("领用3个笔记本，金额 500 元", "material_request", "material")
        assert result.get("quantity") == 3


class TestLLMExtraction:
    """有 LLM 时的抽取行为。"""

    async def test_merges_llm_slots_with_existing(self) -> None:
        llm = _llm_returning({"slots": {"leave_type": "年假"}, "missing": ["start_date"]})
        extractor = SlotExtractor(llm_client=llm)
        result = await extractor.extract(
            "请年假", "leave_request", "leave", {"start_date": "2026-09-20"}
        )
        assert result.get("leave_type") == "年假"
        assert result.get("start_date") == "2026-09-20"

    async def test_llm_failure_falls_back(self) -> None:
        llm = MagicMock()
        llm.chat.completions.create = AsyncMock(side_effect=RuntimeError("boom"))
        extractor = SlotExtractor(llm_client=llm)
        result = await extractor.extract("2026-09-20 到 2026-09-21", "leave_request", "leave")
        assert result.get("start_date") == "2026-09-20"
        assert result.get("end_date") == "2026-09-21"
