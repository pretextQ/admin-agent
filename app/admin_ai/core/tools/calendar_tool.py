# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""会议室/车辆预定工具。"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.admin_ai.core.tools.base import BaseTool, ToolResult

logger = structlog.get_logger(__name__)


class CalendarTool(BaseTool):
    """会议室/车辆预定工具，按 business_type 内部分派。"""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    @property
    def name(self) -> str:
        return "calendar"

    @property
    def description(self) -> str:
        return "会议室/车辆预定"

    async def execute(self, params: dict[str, Any], user_id: str) -> ToolResult:
        """执行预定操作。"""
        action = params.get("action", "query_available")
        business_type = params.get("business_type", "meeting_room")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self._base_url}/api/calendar/{business_type}/{action}",
                    json=params,
                    headers={"X-User-Id": user_id},
                )
                response.raise_for_status()
                return ToolResult.text(str(response.json()))
        except httpx.HTTPError as exc:
            logger.error("日程工具调用失败", error=str(exc))
            return ToolResult.error(f"日程系统调用失败: {exc}")
