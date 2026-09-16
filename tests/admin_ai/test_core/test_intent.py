# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""意图识别测试。"""

from __future__ import annotations

import pytest

from app.admin_ai.core.agent.intent import IntentRecognizer


class TestIntentRecognizer:
    """意图识别测试。"""

    @pytest.fixture
    def recognizer(self, mock_llm) -> IntentRecognizer:
        return IntentRecognizer(llm_client=mock_llm)

    async def test_recognize_leave_request(self, recognizer: IntentRecognizer) -> None:
        result = await recognizer.recognize("我想请两天年假")
        assert result["intent"] == "leave_request"
        assert result["confidence"] >= 0.8

    async def test_recognize_policy_query(self, recognizer: IntentRecognizer) -> None:
        result = await recognizer.recognize("年假有几天")
        assert result["intent"] == "policy_query"

    async def test_recognize_fallback_greeting(self) -> None:
        recognizer = IntentRecognizer(llm_client=None)
        result = await recognizer.recognize("你好")
        assert result["intent"] == "greeting"

    async def test_recognize_fallback_leave(self) -> None:
        recognizer = IntentRecognizer(llm_client=None)
        result = await recognizer.recognize("我想请假")
        assert result["intent"] == "leave_request"

    async def test_recognize_fallback_unknown(self) -> None:
        recognizer = IntentRecognizer(llm_client=None)
        result = await recognizer.recognize("今天天气怎么样")
        assert result["intent"] == "other"