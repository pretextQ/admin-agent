# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""槽位抽取测试。"""

from __future__ import annotations

import pytest

from app.admin_ai.core.agent.slot import SlotExtractor


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