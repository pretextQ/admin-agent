# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""会话状态存储。

按 conversation_id 保存多轮对话所需的最小状态：意图、业务类型、
已收集槽位、是否正在续填槽位、是否存在待确认的高风险操作。

默认使用进程内实现，配置了 Redis 时使用 Redis（惰性导入）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Optional, Protocol

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ConversationState:
    """一次会话的可持久化状态。"""

    intent: Optional[str] = None
    business_type: Optional[str] = None
    slots: dict[str, Any] = field(default_factory=dict)
    awaiting_slots: bool = False
    pending_confirmation: bool = False

    def to_dict(self) -> dict[str, Any]:
        """转为可 JSON 序列化的字典。"""
        return {
            "intent": self.intent,
            "business_type": self.business_type,
            "slots": self.slots,
            "awaiting_slots": self.awaiting_slots,
            "pending_confirmation": self.pending_confirmation,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ConversationState":
        """从字典还原状态。"""
        return cls(
            intent=data.get("intent"),
            business_type=data.get("business_type"),
            slots=dict(data.get("slots") or {}),
            awaiting_slots=bool(data.get("awaiting_slots", False)),
            pending_confirmation=bool(data.get("pending_confirmation", False)),
        )


class ConversationStateStore(Protocol):
    """会话状态存储接口。"""

    async def get(self, conversation_id: str) -> Optional[ConversationState]:
        """读取状态，不存在返回 None。"""

    async def save(self, conversation_id: str, state: ConversationState) -> None:
        """写入状态。"""

    async def clear(self, conversation_id: str) -> None:
        """删除状态。"""


class InMemoryConversationStateStore:
    """进程内实现，用于开发与测试。"""

    def __init__(self) -> None:
        self._states: dict[str, str] = {}

    async def get(self, conversation_id: str) -> Optional[ConversationState]:
        raw = self._states.get(conversation_id)
        if raw is None:
            return None
        try:
            return ConversationState.from_dict(json.loads(raw))
        except (TypeError, ValueError):
            logger.warning("会话状态解析失败，忽略", conversation_id=conversation_id)
            return None

    async def save(self, conversation_id: str, state: ConversationState) -> None:
        self._states[conversation_id] = json.dumps(state.to_dict(), ensure_ascii=False)

    async def clear(self, conversation_id: str) -> None:
        self._states.pop(conversation_id, None)


class RedisConversationStateStore:
    """Redis 实现，带 TTL。"""

    def __init__(
        self,
        client: Any,
        ttl: int = 86400,
        prefix: str = "conversation_state:",
    ) -> None:
        self._client = client
        self._ttl = ttl
        self._prefix = prefix

    def _key(self, conversation_id: str) -> str:
        return f"{self._prefix}{conversation_id}"

    async def get(self, conversation_id: str) -> Optional[ConversationState]:
        raw = await self._client.get(self._key(conversation_id))
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            return ConversationState.from_dict(json.loads(raw))
        except (TypeError, ValueError):
            logger.warning("会话状态解析失败，忽略", conversation_id=conversation_id)
            return None

    async def save(self, conversation_id: str, state: ConversationState) -> None:
        payload = json.dumps(state.to_dict(), ensure_ascii=False)
        await self._client.set(self._key(conversation_id), payload, ex=self._ttl)

    async def clear(self, conversation_id: str) -> None:
        await self._client.delete(self._key(conversation_id))


def build_state_store(redis_url: str, ttl: int = 86400) -> ConversationStateStore:
    """按配置构建状态存储；Redis 不可用时回退进程内实现。"""
    try:
        import redis.asyncio as aioredis
    except ImportError:
        logger.warning("redis 依赖未安装，会话状态使用进程内存储")
        return InMemoryConversationStateStore()

    client = aioredis.from_url(redis_url, decode_responses=True)
    return RedisConversationStateStore(client, ttl=ttl)


_default_store: Optional[ConversationStateStore] = None


def get_default_state_store() -> ConversationStateStore:
    """获取默认状态存储单例（进程内）。"""
    global _default_store
    if _default_store is None:
        _default_store = InMemoryConversationStateStore()
    return _default_store
