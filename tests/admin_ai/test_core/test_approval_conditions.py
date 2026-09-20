# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""审批规则条件求值测试（组织架构与审批路由设计 §12 偏离项 4 的补齐）。

要点：日期解析宽容、派生天数含首含尾、槽位缺失一律视为条件不成立（不猜测）、
算子受限不可注入、非法配置在校验阶段就报错。
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from app.admin_ai.core.approval.conditions import (
    ConditionError,
    build_rule_context,
    evaluate_conditions,
    parse_date,
    validate_conditions,
)

# ---------------------------------------------------------------- 日期解析

def test_parse_date_accepts_common_formats() -> None:
    """ISO 日期、ISO 时间、斜杠与中文格式都要认。"""
    assert parse_date("2026-09-25") == date(2026, 9, 25)
    assert parse_date("2026-09-25T09:30:00") == date(2026, 9, 25)
    assert parse_date("2026/9/5") == date(2026, 9, 5)
    assert parse_date("2026年9月5日") == date(2026, 9, 5)
    assert parse_date(date(2026, 9, 25)) == date(2026, 9, 25)
    assert parse_date(datetime(2026, 9, 25, 9, 0)) == date(2026, 9, 25)


def test_parse_date_returns_none_for_garbage() -> None:
    """解析不出来返回 None，绝不猜测日期。"""
    assert parse_date("下周") is None
    assert parse_date("") is None
    assert parse_date(None) is None
    assert parse_date("2026-02-30") is None  # 不存在的日期


# ---------------------------------------------------------------- 派生上下文

def test_build_rule_context_derives_inclusive_days() -> None:
    """请假 9/25~9/26 记 2 天（含首含尾）。"""
    context = build_rule_context("leave", {"start_date": "2026-09-25", "end_date": "2026-09-26"})
    assert context["days"] == 2
    assert context["business_type"] == "leave"


def test_build_rule_context_single_day_is_one() -> None:
    """同一天起止记 1 天。"""
    context = build_rule_context("leave", {"start_date": "2026-09-25", "end_date": "2026-09-25"})
    assert context["days"] == 1


def test_build_rule_context_skips_days_when_dates_missing_or_inverted() -> None:
    """日期缺失或倒置时不写入 days——条件随之不成立，不猜天数。"""
    assert "days" not in build_rule_context("leave", {"start_date": "2026-09-25"})
    assert "days" not in build_rule_context("leave", {"start_date": "下周"})
    assert "days" not in build_rule_context(
        "travel", {"start_date": "2026-09-26", "end_date": "2026-09-25"}
    )
    assert "days" not in build_rule_context("leave", None)


# ---------------------------------------------------------------- 条件求值

def test_empty_conditions_always_hold() -> None:
    """无条件是兜底规则，恒成立。"""
    for empty in (None, "", [], {}):
        assert evaluate_conditions(empty, {"days": 2}) is True


def test_numeric_comparison_tolerates_str_and_number() -> None:
    """数值比较对 "2" 与 2 一视同仁（槽位值来自 LLM/正则，类型不稳定）。"""
    context = {"days": "3", "amount": 6000}
    assert evaluate_conditions({"slot": "days", "op": "gt", "value": 2}, context) is True
    assert evaluate_conditions({"slot": "amount", "op": "gte", "value": 5000}, context) is True
    assert evaluate_conditions({"slot": "days", "op": "lte", "value": "2"}, context) is False
    assert evaluate_conditions({"slot": "days", "op": "lt", "value": 3.0}, context) is False


def test_equality_on_enum_slot() -> None:
    """枚举型槽位（印章类型）按字符串比较。"""
    context = {"seal_type": "合同章"}
    assert evaluate_conditions({"slot": "seal_type", "op": "eq", "value": "合同章"}, context) is True
    assert evaluate_conditions({"slot": "seal_type", "op": "ne", "value": "公章"}, context) is True


def test_missing_slot_never_matches() -> None:
    """槽位缺失/为 None → 条件不成立（宁可转人工，不猜测）。"""
    assert evaluate_conditions({"slot": "days", "op": "gt", "value": 2}, {}) is False
    assert evaluate_conditions({"slot": "days", "op": "gt", "value": 2}, {"days": None}) is False


def test_in_and_not_in_operators() -> None:
    """in / not_in 支持枚举集合。"""
    context = {"seal_type": "法人章"}
    assert evaluate_conditions({"slot": "seal_type", "op": "in", "value": ["合同章", "法人章"]}, context) is True
    assert evaluate_conditions({"slot": "seal_type", "op": "not_in", "value": ["公章"]}, context) is True


def test_multiple_conditions_are_anded() -> None:
    """条件列表隐式 AND。"""
    context = {"leave_type": "病假", "days": 4}
    conditions = [
        {"slot": "leave_type", "op": "eq", "value": "病假"},
        {"slot": "days", "op": "gte", "value": 3},
    ]
    assert evaluate_conditions(conditions, context) is True
    assert evaluate_conditions(conditions, {"leave_type": "年假", "days": 4}) is False


def test_unsupported_operator_raises() -> None:
    """算子受限（不做表达式解析）：未支持的算子直接报错而不是静默放行。"""
    with pytest.raises(ConditionError):
        evaluate_conditions({"slot": "days", "op": "contains", "value": 2}, {"days": 2})


def test_malformed_condition_structure_raises() -> None:
    """结构非法（字符串、数字、列表元素非对象）报错。"""
    with pytest.raises(ConditionError):
        evaluate_conditions("days > 2", {})
    with pytest.raises(ConditionError):
        evaluate_conditions([1, 2], {})
    with pytest.raises(ConditionError):
        evaluate_conditions({"slot": "days", "op": "in", "value": 2}, {"days": 2})


# ---------------------------------------------------------------- 配置校验

def test_validate_conditions_accepts_valid() -> None:
    """合法配置不抛异常（供管理端/脚本写入前调用）。"""
    validate_conditions(None)
    validate_conditions({"slot": "days", "op": "gt", "value": 2})
    validate_conditions([{"slot": "seal_type", "op": "eq", "value": "合同章"}])
    validate_conditions([{"slot": "seal_type", "op": "in", "value": ["合同章"]}])


@pytest.mark.parametrize(
    "bad",
    [
        {"op": "gt", "value": 2},
        {"slot": "days", "value": 2},
        {"slot": "days", "op": "gt"},
        {"slot": "days", "op": "between", "value": 2},
        {"slot": "days", "op": "in", "value": 2},
        "days>2",
    ],
)
def test_validate_conditions_rejects_bad(bad) -> None:
    """非法配置在校验阶段暴露，不等到线上路由时才发现。"""
    with pytest.raises(ConditionError):
        validate_conditions(bad)
