# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""入离职工具。"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.admin_ai.core.tools.base import BaseTool, ToolResult

logger = structlog.get_logger(__name__)


class OnboardingTool(BaseTool):
    """入离职办理工具。"""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    @property
    def name(self) -> str:
        return "onboarding"

    @property
    def description(self) -> str:
        return "入离职办理"

    async def execute(self, params: dict[str, Any], user_id: str) -> ToolResult:
        """执行入离职操作。"""
        action = params.get("action", "create")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self._base_url}/api/onboarding/{action}",
                    json=params,
                    headers={"X-User-Id": user_id},
                )
                response.raise_for_status()
                return ToolResult.text(str(response.json()))
        except httpx.HTTPError as exc:
            logger.error("入离职工具调用失败", error=str(exc))
            return ToolResult.error(f"入离职系统调用失败: {exc}")
