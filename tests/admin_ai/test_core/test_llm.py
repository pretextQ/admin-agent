# -*- coding: utf-8 -*-
"""LLM 网关工厂测试。"""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.admin_ai.config import Settings
from app.admin_ai.core.llm import build_llm_client
from app.admin_ai.core.llm_gateway import LLMGateway


def _config(**overrides: Any) -> Settings:
    """构造不读取 .env / 环境变量的配置。"""
    return Settings(_env_file=None, **overrides)


def _production_config(**overrides: Any) -> Settings:
    """构造满足生产必填项的最小配置（用于校验 fail-fast 规则）。"""
    base: dict[str, Any] = {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "x" * 40,
        "OPENAI_API_KEY": "sk-test",
        "FEISHU_APP_ID": "app",
        "FEISHU_APP_SECRET": "secret",
        "FEISHU_REDIRECT_URI": "https://example.test/cb",
        "CORS_ORIGINS": ["https://example.test"],
    }
    base.update(overrides)
    return _config(**base)


def _stub_openai_module() -> tuple[ModuleType, dict[str, Any]]:
    """构造 openai 桩模块，返回 (模块, 捕获的构造参数)。"""
    created: dict[str, Any] = {}

    class _StubAsyncOpenAI:
        def __init__(self, **kwargs: Any) -> None:
            created.update(kwargs)

    stub = ModuleType("openai")
    stub.AsyncOpenAI = _StubAsyncOpenAI  # type: ignore[attr-defined]
    return stub, created


def test_returns_none_without_api_key() -> None:
    """未配置 API Key 时降级为规则回退。"""
    assert build_llm_client(_config(OPENAI_API_KEY="")) is None


def test_builds_gateway_with_key() -> None:
    """配置了 Key 且依赖可用时返回 LLMGateway（内含脱敏与 L4 拦截）。"""
    stub, created = _stub_openai_module()
    config = _config(
        OPENAI_API_KEY="sk-test",
        OPENAI_BASE_URL="https://example.test/v1",
    )
    with patch.dict(sys.modules, {"openai": stub}):
        gateway = build_llm_client(config)

    assert isinstance(gateway, LLMGateway)
    assert created["api_key"] == "sk-test"
    assert created["base_url"] == "https://example.test/v1"


def test_gateway_bypassed_when_redaction_off_in_dev() -> None:
    """开发环境可显式关闭脱敏（生产由下方 fail-fast 拦截）。"""
    stub, _ = _stub_openai_module()
    config = _config(OPENAI_API_KEY="sk-test", LLM_REDACTION_ENABLED=False)
    with patch.dict(sys.modules, {"openai": stub}):
        gateway = build_llm_client(config)

    assert isinstance(gateway, LLMGateway)
    assert gateway.is_enabled is False


def test_production_forbids_disabling_redaction() -> None:
    """生产环境禁止关闭 LLM 脱敏：避免 L3 数据未经脱敏发往外部模型。"""
    with pytest.raises(ValidationError):
        _production_config(LLM_REDACTION_ENABLED=False)


def test_production_forbids_debug_mode() -> None:
    """生产环境禁止 DEBUG=true。

    DEBUG 会打开 SQLAlchemy echo，把含业务数据的 SQL（含用户对话原文、
    报销金额等 L3 明文）打印进日志，绕过脱敏层的保护范围。
    """
    with pytest.raises(ValidationError):
        _production_config(DEBUG=True)


def test_returns_none_when_dependency_missing() -> None:
    """openai 依赖缺失时优雅降级，不抛异常。"""
    config = _config(OPENAI_API_KEY="sk-test")
    with patch.dict(sys.modules, {"openai": None}):
        assert build_llm_client(config) is None
