# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""固定资产工具。"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.admin_ai.core.tools.base import BaseTool, ToolResult

logger = structlog.get_logger(__name__)


class AssetTool(BaseTool):
    """固定资产领用/归还工具。"""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    @property
    def name(self) -> str:
        return "asset"

    @property
    def description(self) -> str:
        return "固定资产领用/归还"

    async def execute(self, params: dict[str, Any], user_id: str) -> ToolResult:
        """执行资产操作。"""
        action = params.get("action", "query")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self._base_url}/api/asset/{action}",
                    json=params,
                    headers={"X-User-Id": user_id},
                )
                response.raise_for_status()
                return ToolResult.text(str(response.json()))
        except httpx.HTTPError as exc:
            logger.error("资产工具调用失败", error=str(exc))
            return ToolResult.error(f"资产系统调用失败: {exc}")
