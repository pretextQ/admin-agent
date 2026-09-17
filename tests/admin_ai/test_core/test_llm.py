# -*- coding: utf-8 -*-
"""LLM 客户端工厂测试。"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any
from unittest.mock import patch

from app.admin_ai.config import Settings
from app.admin_ai.core.llm import build_llm_client


def _config(**overrides: Any) -> Settings:
    """构造不读取 .env / 环境变量的配置。"""
    return Settings(_env_file=None, **overrides)


def test_returns_none_without_api_key() -> None:
    """未配置 API Key 时降级为规则回退。"""
    assert build_llm_client(_config(OPENAI_API_KEY="")) is None


def test_builds_client_with_key() -> None:
    """配置了 Key 且依赖可用时返回客户端实例。"""
    created: dict[str, Any] = {}

    class _StubAsyncOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            created.update(kwargs)

    stub = ModuleType("openai")
    stub.AsyncOpenAI = _StubAsyncOpenAI  # type: ignore[attr-defined]

    config = _config(
        OPENAI_API_KEY="sk-test",
        OPENAI_BASE_URL="https://example.test/v1",
    )
    with patch.dict(sys.modules, {"openai": stub}):
        client = build_llm_client(config)

    assert isinstance(client, _StubAsyncOpenAI)
    assert created["api_key"] == "sk-test"
    assert created["base_url"] == "https://example.test/v1"


def test_returns_none_when_dependency_missing() -> None:
    """openai 依赖缺失时优雅降级，不抛异常。"""
    config = _config(OPENAI_API_KEY="sk-test")
    with patch.dict(sys.modules, {"openai": None}):
        assert build_llm_client(config) is None

