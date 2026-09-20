# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""工具基类。"""

from __future__ import annotations

import ast
import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

# 受理编号在下游响应里的字段名（对接真实服务时先确认；不一致则任务 external_id 为空）
EXTERNAL_ID_FIELD = "external_id"


def parse_downstream_payload(text: str) -> dict[str, Any]:
    """把下游响应文本解析成响应体。

    工具以文本回传下游响应（开发桩是 `str(dict)` 的 Python repr，真实服务是 JSON），
    两种形态都容忍；解析不出时返回空字典，由调用方走降级（此处不告警，避免每次调用刷日志）。
    """
    if not text:
        return {}
    for parser in (json.loads, ast.literal_eval):
        try:
            payload = parser(text)
        except (ValueError, SyntaxError):
            continue
        if isinstance(payload, dict):
            return payload
    return {}


def extract_external_id(text: str) -> Optional[str]:
    """从下游响应里取受理编号。

    用户会被回复告知「受理编号 MOCK-xxxx」，必须把它落到任务的 `external_id` 上，
    否则用户拿着这个编号查不到自己的单据。取不到就返回 None，不编造编号。
    """
    payload = parse_downstream_payload(text)
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    value = data.get(EXTERNAL_ID_FIELD)
    return str(value) if isinstance(value, (str, int)) and str(value) else None


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

    @property
    def text_content(self) -> str:
        """文本内容（各工具目前都把下游响应原样转成文本回传）。

        注意不能叫 `text`：那会覆盖上面的 `ToolResult.text()` 构造器，
        12 个工具都在用它。
        """
        for part in self.content or []:
            if isinstance(part, dict) and part.get("type") == "text":
                return str(part.get("text") or "")
        return ""

    @property
    def external_id(self) -> Optional[str]:
        """下游受理编号；失败结果不携带编号。"""
        if self.is_error:
            return None
        return extract_external_id(self.text_content)


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