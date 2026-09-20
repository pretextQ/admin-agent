# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""全局测试 fixtures。"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest


def pytest_configure(config) -> None:
    """注册自定义标记。"""
    markers = {
        "slow": "耗时较长的用例",
        "integration": "需要 PostgreSQL / Redis 等真实依赖的集成测试",
        "e2e": "跨模块端到端用例",
        "llm": "调用真实 LLM 的用例",
    }
    for name, description in markers.items():
        config.addinivalue_line("markers", f"{name}: {description}")


@pytest.fixture(autouse=True)
def stub_audit_db(monkeypatch):
    """审计中间件写库默认打桩，避免单元测试触碰真实 PostgreSQL。

    返回 mock session，供审计相关用例断言写入内容；用例内部如需
    自定义工厂可再叠加 patch（内层 patch 优先生效）。
    """
    session = MagicMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=session)
    ctx.__aexit__ = AsyncMock(return_value=False)
    # 两层调用链：get_session_factory() -> sessionmaker；sessionmaker() -> 异步上下文
    session_factory_mock = MagicMock(return_value=ctx)
    get_session_factory_mock = MagicMock(return_value=session_factory_mock)
    monkeypatch.setattr(
        "app.admin_ai.db.database.get_session_factory", get_session_factory_mock
    )
    yield session


@pytest.fixture
def mock_llm() -> AsyncMock:
    """LLM 网关桩。

    网关接口为 `await gateway.chat(messages, purpose=..., session_key=...) -> str`，
    故这里按最后一条消息返回预置 JSON 文本（不再是供应商的 completion 对象）。
    """

    async def _chat(messages: list[dict[str, Any]], **_kwargs: Any) -> str:
        prompt = (messages or [{}])[-1].get("content", "")
        if "请假" in prompt or ("请" in prompt and "假" in prompt):
            return '{"intent": "leave_request", "business_type": "leave", "confidence": 0.95}'
        return '{"intent": "policy_query", "confidence": 0.9}'

    mock = AsyncMock()
    mock.chat.side_effect = _chat
    return mock