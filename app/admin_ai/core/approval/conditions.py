# Copyright 2026  Admin AI Team, All rights reserved.
"""审批规则的条件求值与派生上下文。

解决「规则只能按业务类型 + 金额匹配」的局限（组织架构与审批路由设计 §12 偏离项 4）：
场景文档里的审批要求常常按**槽位**分支——用印的印章类型、请假的连续天数、差旅的出差天数、
资产的单项价值。这里提供一个受控的条件求值器：

- `build_rule_context()`：从槽位构造求值上下文，并补上**派生字段**（`days` 由起止日期算出）；
- `evaluate_conditions()`：对规则上的条件列表做隐式 AND 求值，算子受限、不做表达式解析（无 eval）。

设计取舍：**槽位缺失一律视为「条件不成立」**，绝不猜测。因此需要「无论如何都要审批」的业务
应配置一条兜底规则（金额区间与条件均为空），否则未匹配即视为无需审批——见 `router.match_rules`。
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

# 支持的算子（受限集合，避免引入表达式解析与注入面）
SUPPORTED_OPS = frozenset({"eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in"})

# 派生字段名
DERIVED_DAYS = "days"

_DATE_PATTERNS = (
    re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})$"),
    re.compile(r"^(\d{4})/(\d{1,2})/(\d{1,2})$"),
    re.compile(r"^(\d{4})年(\d{1,2})月(\d{1,2})日$"),
)


class ConditionError(ValueError):
    """条件配置本身非法（算子不支持、结构不对）。"""


def parse_date(value: Any) -> date | None:
    """宽容解析日期；解析不出来返回 None（调用方按「条件不成立」处理）。"""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        pass
    for pattern in _DATE_PATTERNS:
        match = pattern.match(text)
        if match:
            year, month, day = (int(part) for part in match.groups())
            try:
                return date(year, month, day)
            except ValueError:
                return None
    return None


def build_rule_context(
    business_type: str, slots: Mapping[str, Any] | None
) -> dict[str, Any]:
    """构造规则求值上下文：槽位原值 + 派生字段。

    `days`：请假/差旅的连续天数，按「含首含尾」计算（9/25~9/26 = 2 天）。
    起止日期缺失或倒置时**不写入**该字段——条件随之不成立，不会猜测天数。
    """
    context: dict[str, Any] = dict(slots or {})
    context["business_type"] = business_type

    start = parse_date(context.get("start_date"))
    end = parse_date(context.get("end_date"))
    if start and end and end >= start:
        context[DERIVED_DAYS] = (end - start).days + 1
    return context


def evaluate_conditions(
    conditions: Any, context: Mapping[str, Any]
) -> bool:
    """对条件列表做隐式 AND 求值；`conditions` 为空表示无条件（恒成立）。"""
    if conditions in (None, "", [], {}):
        return True
    if isinstance(conditions, Mapping):
        conditions = [conditions]
    if not isinstance(conditions, Sequence) or isinstance(conditions, (str, bytes)):
        raise ConditionError(f"条件结构非法：{type(conditions).__name__}，应为对象或对象数组")
    for condition in conditions:
        if not isinstance(condition, Mapping):
            raise ConditionError("条件项必须是对象，如 {\"slot\": \"days\", \"op\": \"gt\", \"value\": 2}")
        if not _evaluate_one(condition, context):
            return False
    return True


def validate_conditions(conditions: Any) -> None:
    """校验条件配置（供管理端/脚本写入前检查），非法时抛 ConditionError。"""
    if conditions in (None, "", [], {}):
        return
    if isinstance(conditions, Mapping):
        items: Iterable[Any] = [conditions]
    elif isinstance(conditions, (str, bytes)) or not isinstance(conditions, Sequence):
        raise ConditionError("条件应为对象或对象数组")
    else:
        items = conditions
    for condition in items:
        if not isinstance(condition, Mapping):
            raise ConditionError("条件项必须是对象")
        slot = condition.get("slot")
        op = condition.get("op")
        if not slot or not isinstance(slot, str):
            raise ConditionError("条件缺少 slot")
        if op not in SUPPORTED_OPS:
            raise ConditionError(f"不支持的算子 {op!r}，可用：{sorted(SUPPORTED_OPS)}")
        if "value" not in condition:
            raise ConditionError("条件缺少 value")
        if op in {"in", "not_in"} and not isinstance(condition["value"], (list, tuple)):
            raise ConditionError(f"算子 {op} 的 value 应为数组")


def _evaluate_one(condition: Mapping[str, Any], context: Mapping[str, Any]) -> bool:
    """单条件求值；槽位缺失返回 False（不猜测）。"""
    slot = condition.get("slot")
    op = condition.get("op")
    expected = condition.get("value")

    if slot not in context:
        return False
    actual = context.get(slot)
    if actual is None:
        return False

    if op in {"in", "not_in"}:
        if not isinstance(expected, (list, tuple)):
            raise ConditionError(f"算子 {op} 的 value 应为数组")
        hit = any(_values_equal(actual, item) for item in expected)
        return hit if op == "in" else not hit

    if op == "eq":
        return _values_equal(actual, expected)
    if op == "ne":
        return not _values_equal(actual, expected)

    left, right = _as_numbers(actual, expected)
    if left is None or right is None:
        return False
    if op == "gt":
        return left > right
    if op == "gte":
        return left >= right
    if op == "lt":
        return left < right
    if op == "lte":
        return left <= right
    raise ConditionError(f"不支持的算子 {op!r}")


def _values_equal(actual: Any, expected: Any) -> bool:
    """相等比较：数值型按 Decimal 比较（避免 2 与 "2" 判不等），其余按字符串比较。"""
    left, right = _as_numbers(actual, expected)
    if left is not None and right is not None:
        return left == right
    return str(actual).strip() == str(expected).strip()


def _as_numbers(actual: Any, expected: Any) -> tuple[Decimal | None, Decimal | None]:
    """可转数值则返回 Decimal 对，否则返回 (None, None)。"""
    try:
        return Decimal(str(actual).strip()), Decimal(str(expected).strip())
    except (InvalidOperation, ValueError, TypeError):
        return None, None
