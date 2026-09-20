# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""LLM 客户端工厂。

按配置构建 **LLMGateway**（外部 LLM 的统一出入口，内含脱敏与 L4 拦截）。
未配置密钥或缺少依赖时返回 None，调用方据此降级为规则回退（关键词 / 正则），
保证服务可用性。

所有对大模型的调用都应经此网关，不要直接持有供应商客户端——
否则会绕过脱敏与拦截，形成合规缺口（见 docs/architecture/LLM数据脱敏与合规设计.md）。
"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from app.admin_ai.config import Settings
from app.admin_ai.core.llm_gateway import LLMGateway
from app.admin_ai.core.llm_redaction import Redactor

logger = structlog.get_logger(__name__)


def build_llm_client(config: Settings) -> Optional[LLMGateway]:
    """构建 LLM 网关。

    Args:
        config: 应用配置。

    Returns:
        LLMGateway 实例；未配置密钥或依赖缺失时返回 None（全局规则回退）。
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

    client = AsyncOpenAI(
        api_key=config.OPENAI_API_KEY,
        base_url=config.OPENAI_BASE_URL,
    )

    redactor = Redactor(
        redact_amount=config.REDACT_AMOUNT,
        employee_id_pattern=config.LLM_EMPLOYEE_ID_PATTERN or None,
    )
    if not config.LLM_REDACTION_ENABLED:
        logger.warning(
            "LLM 脱敏已关闭，数据将未经脱敏发往外部模型",
            note="仅允许开发环境；生产环境会拒绝启动",
        )

    return LLMGateway(
        client=client,
        redactor=redactor,
        model=config.LLM_MODEL,
        enabled=config.LLM_REDACTION_ENABLED,
        excluded_business_types=tuple(config.LLM_EXCLUDED_BUSINESS_TYPES),
        audit_enabled=config.LLM_AUDIT_ENABLED,
    )
