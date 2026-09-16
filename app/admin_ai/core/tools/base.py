# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""工具基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolResult:
    """工具执行结果。"""
    content: list[dict] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    is_error: bool = False

    @classmethod
    def text(cls, text: str, details: Optional[dict] = None) -> "ToolResult":
        """构造文本结果。"""
        return cls(content=[{"type": "text", "text": text}], details=details or {})

    @classmethod
    def error(cls, message: str, details: Optional[dict] = None) -> "ToolResult":
        """构造错误结果。"""
        return cls(
            content=[{"type": "text", "text": message}],
            details=details or {},
            is_error=True,
        )


class BaseTool(ABC):
    """工具基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称。"""

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述。"""

    @abstractmethod
    async def execute(self, params: dict[str, Any], user_id: str) -> ToolResult:
        """执行工具。"""