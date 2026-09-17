# -*- coding: utf-8 -*-
"""会话状态存储测试。"""

from __future__ import annotations

import json
import sys
from typing import Any
from unittest.mock import AsyncMock, patch

from app.admin_ai.core.agent.state_store import (
    ConversationState,
    InMemoryConversationStateStore,
    RedisConversationStateStore,
    build_state_store,
    get_default_state_store,
)


def _state() -> ConversationState:
    return ConversationState(
        intent="leave_request",
        business_type="leave",
        slots={"leave_type": "年假"},
        awaiting_slots=True,
        pending_confirmation=False,
    )


async def test_memory_save_and_get_roundtrip() -> None:
    store = InMemoryConversationStateStore()
    await store.save("c1", _state())
    assert await store.get("c1") == _state()


async def test_memory_get_unknown_returns_none() -> None:
    store = InMemoryConversationStateStore()
    assert await store.get("missing") is None


async def test_memory_clear_removes_state() -> None:
    store = InMemoryConversationStateStore()
    await store.save("c1", _state())
    await store.clear("c1")
    assert await store.get("c1") is None


def test_state_roundtrips_through_json() -> None:
    payload = _state().to_dict()
    json.dumps(payload)
    assert ConversationState.from_dict(payload) == _state()


class _FakeRedis:
    def __init__(self) -> None:
        self.data: dict[str, str] = {}

    async def get(self, key: str) -> Any:
        return self.data.get(key)

    async def set(self, key: str, value: str, ex: Any = None) -> None:
        self.data[key] = value

    async def delete(self, key: str) -> None:
        self.data.pop(key, None)


async def test_redis_store_roundtrip() -> None:
    store = RedisConversationStateStore(_FakeRedis())
    await store.save("c1", _state())
    assert await store.get("c1") == _state()
    await store.clear("c1")
    assert await store.get("c1") is None


async def test_redis_store_uses_prefix_and_ttl() -> None:
    client = AsyncMock()
    store = RedisConversationStateStore(client, ttl=120, prefix="conv:")
    await store.save("c1", _state())
    key, value = client.set.call_args.args
    assert key == "conv:c1"
    assert client.set.call_args.kwargs["ex"] == 120
    assert json.loads(value)["business_type"] == "leave"


def test_build_state_store_falls_back_without_redis() -> None:
    with patch.dict(sys.modules, {"redis": None, "redis.asyncio": None}):
        store = build_state_store("redis://localhost:6379/0")
    assert isinstance(store, InMemoryConversationStateStore)


def test_default_state_store_is_singleton() -> None:
    assert get_default_state_store() is get_default_state_store()
