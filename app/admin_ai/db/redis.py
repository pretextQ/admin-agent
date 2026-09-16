# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""Redis 连接管理。"""

from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis

from app.admin_ai.config import get_config

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """获取 Redis 客户端单例。"""
    global _redis_client
    if _redis_client is None:
        config = get_config()
        _redis_client = aioredis.from_url(config.REDIS_URL, decode_responses=True)
    return _redis_client


async def close_redis() -> None:
    """关闭 Redis 连接。"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None