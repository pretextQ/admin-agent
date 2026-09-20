# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""LLM 脱敏层。

把送往外部大模型的数据按「送出白名单」处理：
**先拦截（L4 命中即中止）→ 再脱敏（身份类字段替换为占位符）→ 回复回填**。

设计见 `docs/architecture/LLM数据脱敏与合规设计.md` §3（白名单）、§4（脱敏与占位符）、§7（拦截）。
本模块不做任何 IO，也不查库——已知姓名由调用方查出后注入，便于单测与复用。

安全约定：
1. 脱敏失败**不得降级为直发原文**（调用方须捕获异常并回退规则路径）；
2. 占位符映射只存在于会话期内存（多实例部署时应注入 Redis 实现），不入库、不落日志；
3. 金额默认保留（可配 `redact_amount=True` 一并占位化）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)

# 类别 → 占位符前缀（占位符形如 [员工1]、[手机2]）
CATEGORY_LABELS: dict[str, str] = {
    "person": "员工",
    "phone": "手机",
    "email": "邮箱",
    "employee_id": "工号",
    "amount": "金额",
    "id_card": "证件",
    "bank_card": "卡号",
}

# L4 特征：命中即中止调用（绝不送出，不做「脱敏后送出」）
# 设计 §3 的白名单优先于 §4.2 的规则表——身份证/银行卡属 L4，一律拦截。
DEFAULT_BLOCKED_PATTERNS: list[tuple[str, str]] = [
    ("id_card", r"\d{17}[\dXx]"),
    ("bank_card", r"\d{16,19}"),
]

# 脱敏规则（身份类字段，替换为占位符后送出）
DEFAULT_RULES: list[tuple[str, str]] = [
    ("phone", r"1[3-9]\d{9}"),
    ("email", r"[\w.+-]+@[\w-]+\.[\w.]+"),
]

# 金额：仅在 redact_amount=True 时启用
AMOUNT_PATTERN = r"(\d+(?:\.\d+)?)\s*元"

_PLACEHOLDER_RE = re.compile(r"\[([^\[\]]+?)(\d+)\]")


@dataclass
class RedactionResult:
    """脱敏结果。"""

    text: str
    categories: list[str] = field(default_factory=list)


class LLMCallBlockedError(Exception):
    """外部 LLM 调用被拦截的基类：调用方应回退规则/模板路径，不得直发原文。"""


class RedactionBlockedError(LLMCallBlockedError):
    """内容命中 L4 特征，已中止本次外部 LLM 调用。"""

    def __init__(self, category: str) -> None:
        self.category = category
        super().__init__(f"内容命中 L4 特征（{category}），已中止外部 LLM 调用")


class PlaceholderRegistry:
    """会话级占位符映射。

    同一会话内，同一实体的每次出现都映射到同一占位符——否则 LLM 会把
    「张三」的两次提及当成两个人，多轮对话语义会错乱。

    进程内实现，用于单实例部署与测试；多实例部署应替换为 Redis 实现
    （与会话状态同生命周期，参见设计 §4.3）。
    """

    def __init__(self) -> None:
        # session_key -> {"forward": {category: {value: placeholder}},
        #                 "backward": {placeholder: value},
        #                 "counter": {category: int}}
        self._sessions: dict[str, dict[str, Any]] = {}

    def _session(self, session_key: str) -> dict[str, Any]:
        return self._sessions.setdefault(
            session_key, {"forward": {}, "backward": {}, "counter": {}}
        )

    def to_placeholder(self, session_key: str, category: str, value: str) -> str:
        """取得（或分配）该实体在本会话内的占位符。"""
        session = self._session(session_key)
        per_category = session["forward"].setdefault(category, {})
        if value in per_category:
            return per_category[value]

        index = session["counter"].get(category, 0) + 1
        session["counter"][category] = index
        label = CATEGORY_LABELS.get(category, category)
        placeholder = f"[{label}{index}]"
        per_category[value] = placeholder
        session["backward"][placeholder] = value
        return placeholder

    def to_value(self, session_key: str, placeholder: str) -> Optional[str]:
        """按占位符取回真值；未登记返回 None（不猜测）。"""
        session = self._sessions.get(session_key)
        if not session:
            return None
        return session["backward"].get(placeholder)

    def clear(self, session_key: str) -> None:
        """会话结束时清除映射（不保留跨会话的真值关联）。"""
        self._sessions.pop(session_key, None)


class Redactor:
    """脱敏器：拦截 L4、替换身份类字段、回填占位符。"""

    def __init__(
        self,
        rules: Optional[list[tuple[str, str]]] = None,
        known_names: Optional[set[str]] = None,
        redact_amount: bool = False,
        blocked_patterns: Optional[list[tuple[str, str]]] = None,
        employee_id_pattern: Optional[str] = None,
        registry: Optional[PlaceholderRegistry] = None,
    ) -> None:
        self._rules = rules if rules is not None else list(DEFAULT_RULES)
        self._blocked = (
            blocked_patterns if blocked_patterns is not None else list(DEFAULT_BLOCKED_PATTERNS)
        )
        # 长名字优先替换，避免「张三」吃掉「张三丰」
        self._known_names = sorted(known_names or set(), key=len, reverse=True)
        self._redact_amount = redact_amount
        self._employee_id_pattern = employee_id_pattern
        self._registry = registry or PlaceholderRegistry()

    # ------------------------------------------------------------ 拦截

    def contains_blocked(self, text: str) -> Optional[str]:
        """检测 L4 特征；命中返回类别名，未命中返回 None。"""
        if not text:
            return None
        for category, pattern in self._blocked:
            if re.search(pattern, text):
                return category
        return None

    # ------------------------------------------------------------ 脱敏

    def redact(self, text: str, session_key: str) -> RedactionResult:
        """脱敏文本。

        Raises:
            RedactionBlockedError: 命中 L4 特征（调用方应回退规则路径，不得直发原文）。
        """
        if not text:
            return RedactionResult(text=text, categories=[])

        blocked = self.contains_blocked(text)
        if blocked:
            raise RedactionBlockedError(blocked)

        categories: list[str] = []
        result = text

        for category, pattern in self._rules:
            result, hit = self._substitute(result, pattern, category, session_key)
            if hit:
                categories.append(category)

        if self._employee_id_pattern:
            result, hit = self._substitute(
                result, self._employee_id_pattern, "employee_id", session_key
            )
            if hit:
                categories.append("employee_id")

        if self._redact_amount:
            result, hit = self._substitute(result, AMOUNT_PATTERN, "amount", session_key)
            if hit:
                categories.append("amount")

        for name in self._known_names:
            if name and name in result:
                placeholder = self._registry.to_placeholder(session_key, "person", name)
                result = result.replace(name, placeholder)
                if "person" not in categories:
                    categories.append("person")

        return RedactionResult(text=result, categories=categories)

    def _substitute(
        self, text: str, pattern: str, category: str, session_key: str
    ) -> tuple[str, bool]:
        """把匹配到的实体逐个替换为占位符，返回 (新文本, 是否有命中)。"""
        hits = list(re.finditer(pattern, text))
        if not hits:
            return text, False
        # 从后往前替换，避免偏移量失效
        for match in reversed(hits):
            placeholder = self._registry.to_placeholder(session_key, category, match.group(0))
            text = text[: match.start()] + placeholder + text[match.end():]
        return text, True

    # ------------------------------------------------------------ 回填

    def restore(self, text: str, session_key: str) -> str:
        """把回复中的占位符回填为真实值；未登记的占位符原样保留（不猜测）。"""
        if not text:
            return text

        def _replace(match: re.Match[str]) -> str:
            value = self._registry.to_value(session_key, match.group(0))
            return value if value is not None else match.group(0)

        return _PLACEHOLDER_RE.sub(_replace, text)

    # ------------------------------------------------------- 运行时维护

    def update_known_names(self, names: set[str]) -> None:
        """更新已知姓名集合（启动时从 users 表加载，人员变动后可按需刷新）。"""
        self._known_names = sorted({n for n in names if n}, key=len, reverse=True)
