# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""审批流工具。"""

from __future__ import annotations

from typing import Any

import httpx
import structlog

from app.admin_ai.core.tools.base import BaseTool, ToolResult

logger = structlog.get_logger(__name__)


class ApprovalTool(BaseTool):
    """审批流工具，转发到外部审批引擎。"""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url

    @property
    def name(self) -> str:
        return "approval"

    @property
    def description(self) -> str:
        return "审批流发起/查询"

    async def execute(self, params: dict[str, Any], user_id: str) -> ToolResult:
        """执行审批操作。"""
        action = params.get("action", "create")
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(
                    f"{self._base_url}/api/approval/{action}",
                    json=params,
                    headers={"X-User-Id": user_id},
                )
                response.raise_for_status()
                return ToolResult.text(str(response.json()))
        except httpx.HTTPError as exc:
            logger.error("审批工具调用失败", error=str(exc))
            return ToolResult.error(f"审批系统调用失败: {exc}")
