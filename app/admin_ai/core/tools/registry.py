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

    def register(self, name: str, tool: BaseTool) -> None:
        """注册工具。"""
        self._tools[name] = tool
        logger.info("工具已注册", tool_name=name)

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """获取工具。"""
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, str]]:
        """列出所有工具。"""
        return [{"name": t.name, "description": t.description} for t in self._tools.values()]


def init_tools(config: Any) -> ToolRegistry:
    """初始化并注册所有工具。

    Args:
        config: 应用配置对象。

    Returns:
        工具注册中心实例。
    """
    registry = ToolRegistry()

    # 延迟导入，避免循环依赖
    from app.admin_ai.core.tools.oa_tool import OATool
    from app.admin_ai.core.tools.approval_tool import ApprovalTool
    from app.admin_ai.core.tools.material_tool import MaterialTool
    from app.admin_ai.core.tools.calendar_tool import CalendarTool
    from app.admin_ai.core.tools.hr_tool import HRTool
    from app.admin_ai.core.tools.expense_tool import ExpenseTool
    from app.admin_ai.core.tools.travel_tool import TravelTool
    from app.admin_ai.core.tools.asset_tool import AssetTool
    from app.admin_ai.core.tools.seal_tool import SealTool
    from app.admin_ai.core.tools.certificate_tool import CertificateTool
    from app.admin_ai.core.tools.onboarding_tool import OnboardingTool

    # 注册工具，键名与 TaskType 对应
    registry.register("oa", OATool(config.OA_SERVICE_URL))
    registry.register("approval", ApprovalTool(config.OA_SERVICE_URL))
    registry.register("material", MaterialTool(config.MATERIAL_SERVICE_URL))
    registry.register("meeting_room", CalendarTool(config.OA_SERVICE_URL))
    registry.register("vehicle", CalendarTool(config.OA_SERVICE_URL))
    registry.register("leave", HRTool(config.OA_SERVICE_URL))
    registry.register("expense", ExpenseTool(config.FINANCE_SERVICE_URL))
    registry.register("travel", TravelTool(config.OA_SERVICE_URL))
    registry.register("asset", AssetTool(config.MATERIAL_SERVICE_URL))
    registry.register("seal", SealTool(config.OA_SERVICE_URL))
    registry.register("certificate", CertificateTool(config.OA_SERVICE_URL))
    registry.register("onboarding", OnboardingTool(config.OA_SERVICE_URL))

    return registry