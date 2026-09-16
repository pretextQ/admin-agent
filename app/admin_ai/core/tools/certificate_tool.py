# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""证明开具工具。"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.admin_ai.core.tools.base import BaseTool, ToolResult

logger = structlog.get_logger(__name__)


class CertificateTool(BaseTool):
    """证明开具工具。"""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    @property
    def name(self) -> str:
        return "certificate"

    @property
    def description(self) -> str:
        return "证明开具"

    async def execute(self, params: dict[str, Any], user_id: str) -> ToolResult:
        """执行证明开具操作。"""
        action = params.get("action", "create")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self._base_url}/api/certificate/{action}",
                    json=params,
                    headers={"X-User-Id": user_id},
                )
                response.raise_for_status()
                return ToolResult.text(str(response.json()))
        except httpx.HTTPError as exc:
            logger.error("证明工具调用失败", error=str(exc))
            return ToolResult.error(f"证明系统调用失败: {exc}")
