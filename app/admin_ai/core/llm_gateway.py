# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""外部 LLM 统一出入口。

所有对大模型的调用都必须经过 `LLMGateway.chat()`，由它统一完成：

    白名单/涉密业务校验 → L4 命中拦截 → 脱敏改写 → 调用供应商 → 占位符回填 → 调用审计

设计见 `docs/architecture/LLM数据脱敏与合规设计.md` §4.1。

安全约定（违反即视为合规缺口）：
1. **fail-closed**：脱敏组件异常时拒绝调用，绝不降级为直发原文；
2. **审计不含值**：审计只记录脱敏类别与用量，不记录提示词/回复原文；
3. **旁路仅供开发**：`enabled=False` 会同时跳过脱敏与拦截，生产环境由配置 fail-fast 禁止。
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any, Optional

import structlog

from app.admin_ai.core.llm_redaction import (
    LLMCallBlockedError,
    RedactionBlockedError,
    Redactor,
)

logger = structlog.get_logger(__name__)

# 无会话上下文时使用的固定 key（保证同进程内占位符一致）
DEFAULT_SESSION_KEY = "__default__"

AuditSink = Callable[[dict[str, Any]], Awaitable[None]]

# 默认不走外部 LLM 的业务类型（涉密：证明开具、用印/合同）
DEFAULT_EXCLUDED_BUSINESS_TYPES = ("certificate", "seal")


class BusinessTypeExcludedError(LLMCallBlockedError):
    """业务类型被配置为不走外部 LLM（如证明开具、用印）。"""

    def __init__(self, business_type: str) -> None:
        self.business_type = business_type
        super().__init__(f"业务类型 {business_type} 被配置为不走外部 LLM")


async def _default_audit_sink(record: dict[str, Any]) -> None:
    """默认审计出口：结构化日志（接入 DB 审计表时注入自定义 sink）。"""
    logger.info("LLM 调用", **record)


class LLMGateway:
    """外部 LLM 调用网关。

    Args:
        client: 供应商客户端（OpenAI 兼容，需提供 `chat.completions.create`）。
        redactor: 脱敏器；为 None 时按「未启用脱敏」处理（仅测试用）。
        model: 模型名。
        enabled: 是否启用脱敏与拦截。关闭会旁路整条安全链路，**仅允许开发环境**。
        excluded_business_types: 不走外部 LLM 的业务类型。
        audit_sink: 审计出口；默认写结构化日志。
        audit_enabled: 是否记录调用审计。
    """

    def __init__(
        self,
        client: Any,
        redactor: Optional[Redactor] = None,
        model: str = "gpt-4o-mini",
        enabled: bool = True,
        excluded_business_types: Optional[tuple[str, ...]] = None,
        audit_sink: Optional[AuditSink] = None,
        audit_enabled: bool = True,
    ) -> None:
        self._client = client
        self._redactor = redactor
        self._model = model
        self._enabled = enabled and redactor is not None
        self._excluded = set(
            excluded_business_types
            if excluded_business_types is not None
            else DEFAULT_EXCLUDED_BUSINESS_TYPES
        )
        self._audit_sink = audit_sink or _default_audit_sink
        self._audit_enabled = audit_enabled

    # --------------------------------------------------------------- 对外接口

    @property
    def is_enabled(self) -> bool:
        """脱敏与拦截是否生效（生产环境恒为 True，见 config.py 的 fail-fast）。"""
        return self._enabled

    def update_known_names(self, names: set[str]) -> None:
        """更新脱敏用的已知姓名集合（启动时从 users 表加载）。"""
        if self._redactor is not None:
            self._redactor.update_known_names(names)

    async def chat(
        self,
        messages: list[dict[str, Any]],
        purpose: str = "chat",
        session_key: Optional[str] = None,
        business_type: Optional[str] = None,
        **kwargs: Any,
    ) -> str:
        """调用大模型，返回**已回填占位符**的回复文本。

        Raises:
            BusinessTypeExcludedError: 业务类型被配置为不走外部 LLM。
            RedactionBlockedError: 内容命中 L4 特征。
            Exception: 脱敏组件内部错误（fail-closed，不会发出请求）。
        """
        started = time.perf_counter()
        session = session_key or DEFAULT_SESSION_KEY

        if business_type and business_type in self._excluded:
            await self._audit(purpose, [], blocked=True, reason="business_excluded")
            raise BusinessTypeExcludedError(business_type)

        categories: list[str] = []
        if self._enabled:
            try:
                messages, categories = self._redact_messages(messages, session)
            except RedactionBlockedError as exc:
                await self._audit(purpose, [], blocked=True, reason=exc.category)
                raise
            except Exception as exc:  # noqa: BLE001 - 脱敏失败必须拒绝调用
                logger.error("脱敏失败，拒绝调用外部 LLM", error=str(exc))
                await self._audit(purpose, [], blocked=True, reason="redactor_error")
                raise

        response = await self._client.chat.completions.create(
            model=self._model, messages=messages, **kwargs
        )
        content = response.choices[0].message.content or ""
        reply = self._redactor.restore(content, session) if self._enabled else content

        await self._audit(
            purpose,
            categories,
            blocked=False,
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
            usage=getattr(response, "usage", None),
        )
        return reply

    # --------------------------------------------------------------- 内部实现

    def _redact_messages(
        self, messages: list[dict[str, Any]], session: str
    ) -> tuple[list[dict[str, Any]], list[str]]:
        """逐条脱敏消息，返回新消息列表与命中的类别（去重、稳定顺序）。"""
        assert self._redactor is not None  # self._enabled 保证
        prepared: list[dict[str, Any]] = []
        categories: list[str] = []
        for message in messages:
            content = message.get("content", "")
            if isinstance(content, str) and content:
                result = self._redactor.redact(content, session)
                for category in result.categories:
                    if category not in categories:
                        categories.append(category)
                prepared.append({**message, "content": result.text})
            else:
                prepared.append(message)
        return prepared, categories

    async def _audit(
        self,
        purpose: str,
        categories: list[str],
        blocked: bool,
        reason: Optional[str] = None,
        latency_ms: Optional[float] = None,
        usage: Any = None,
    ) -> None:
        """写调用审计：只记类别与用量，**不记任何真值**；失败不阻断业务。"""
        if not self._audit_enabled:
            return
        record: dict[str, Any] = {
            "purpose": purpose,
            "model": self._model,
            "redacted_categories": categories,
            "blocked": blocked,
            "trace_id": structlog.contextvars.get_contextvars().get("trace_id"),
        }
        if reason:
            record["reason"] = reason
        if latency_ms is not None:
            record["latency_ms"] = latency_ms
        if usage is not None:
            record["prompt_tokens"] = getattr(usage, "prompt_tokens", None)
            record["completion_tokens"] = getattr(usage, "completion_tokens", None)
        try:
            await self._audit_sink(record)
        except Exception as exc:  # noqa: BLE001 - 审计失败不影响业务
            logger.warning("LLM 审计写入失败", error=str(exc))
