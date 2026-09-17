# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""LLM 客户端工厂。

按配置构建 OpenAI 兼容客户端。未配置密钥或缺少依赖时返回 None，
调用方据此降级为规则回退（关键词 / 正则），保证服务可用性。
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from app.admin_ai.config import Settings

logger = structlog.get_logger(__name__)


def build_llm_client(config: Settings) -> Optional[Any]:
    """构建 LLM 客户端。

    Args:
        config: 应用配置。

    Returns:
        AsyncOpenAI 实例；未配置密钥或依赖缺失时返回 None。
    """
    if not config.OPENAI_API_KEY:
        logger.warning("未配置 OPENAI_API_KEY，LLM 能力降级为规则回退")
        return None

    try:
        # 惰性导入：openai 为可选运行依赖，缺失时不应阻断应用启动
        from openai import AsyncOpenAI
    except ImportError:
        logger.warning("openai 依赖未安装，LLM 能力降级为规则回退")
        return None

    return AsyncOpenAI(
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_BASE_URL,
    )
