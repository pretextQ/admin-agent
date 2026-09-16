# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""工具注册中心。"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from app.admin_ai.core.tools.base import BaseTool

logger = structlog.get_logger(__name__)


class ToolRegistry:
    """工具注册中心。"""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册工具。"""
        self._tools[tool.name] = tool
        logger.info("工具已注册", tool_name=tool.name)

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """获取工具。"""
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, str]]:
        """列出所有工具。"""
        return [{"name": t.name, "description": t.description} for t in self._tools.values()]