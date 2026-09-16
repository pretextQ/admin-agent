# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""多轮对话管理。"""

from __future__ import annotations

import json
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class DialogManager:
    """对话管理器。"""

    def __init__(self, redis_client: Any = None) -> None:
        self._redis = redis_client

    async def get_history(self, conversation_id: str) -> list[dict[str, Any]]:
        """获取对话历史。"""
        if self._redis is None:
            return []
        try:
            data = await self._redis.get(f"conversation:{conversation_id}")
            if data:
                return json.loads(data)
        except Exception as e:
            logger.warning("获取对话历史失败", error=str(e))
        return []

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> None:
        """保存消息到历史。"""
        if self._redis is None:
            return
        try:
            history = await self.get_history(conversation_id)
            history.append({"role": role, "content": content})
            await self._redis.set(
                f"conversation:{conversation_id}",
                json.dumps(history, ensure_ascii=False),
                ex=86400,
            )
        except Exception as e:
            logger.warning("保存消息失败", error=str(e))

    async def clear(self, conversation_id: str) -> None:
        """清空对话历史。"""
        if self._redis is None:
            return
        try:
            await self._redis.delete(f"conversation:{conversation_id}")
        except Exception as e:
            logger.warning("清空对话失败", error=str(e))