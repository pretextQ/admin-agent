# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""状态查询（场景 REQ-03）单元测试。

覆盖纯逻辑部分：查询类型归一、时间范围解析、回复格式化。
涉及 SQL 的归属过滤由 `test_status_query_integration.py` 在真实 PG 上验证。
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest

from app.admin_ai.core.status_query import (
    QUERY_TYPE_EXPENSE_STATUS,
    QUERY_TYPE_LEAVE_BALANCE,
    QUERY_TYPE_TASK_PROGRESS,
    LeaveBalanceEntry,
    TaskView,
    TimeRange,
    approval_status_label,
    extract_task_ref,
    format_leave_balance,
    format_task_detail,
    format_task_list,
    infer_business_type,
    normalize_query_type,
    resolve_time_range,
)

NOW = datetime(2026, 9, 20, 10, 0, 0)


# ---------------------------------------------------------------- 查询类型归一


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("我的报销到哪一步了", QUERY_TYPE_EXPENSE_STATUS),
        ("我上个月的报销到哪一步了", QUERY_TYPE_EXPENSE_STATUS),
        ("这个月报销状态怎么样", QUERY_TYPE_EXPENSE_STATUS),
        ("我还剩几天年假", QUERY_TYPE_LEAVE_BALANCE),
        ("我的年假余额还有多少", QUERY_TYPE_LEAVE_BALANCE),
        ("我的请假批了吗", QUERY_TYPE_LEAVE_BALANCE),
        ("这个月还剩几天调休", QUERY_TYPE_LEAVE_BALANCE),
        ("我的采购任务进度如何", QUERY_TYPE_TASK_PROGRESS),
        ("我提交的申请到哪一步了", QUERY_TYPE_TASK_PROGRESS),
        ("我的流程走到哪了", QUERY_TYPE_TASK_PROGRESS),
        # 未指定查询类型：必须追问（场景 03 TC008）
        ("查询状态", None),
        ("帮我查一下", None),
        ("今天天气怎么样", None),
        ("你好", None),
    ],
)
def test_normalize_query_type_from_message(message: str, expected: str | None) -> None:
    """按场景 03 §3.3 的意图规则归一查询类型；无法判定返回 None。"""
    assert normalize_query_type(message) == expected


@pytest.mark.parametrize(
    ("hint", "expected"),
    [
        ("假期余额", QUERY_TYPE_LEAVE_BALANCE),
        ("leave_balance", QUERY_TYPE_LEAVE_BALANCE),
        ("报销状态", QUERY_TYPE_EXPENSE_STATUS),
        ("expense_status", QUERY_TYPE_EXPENSE_STATUS),
        ("任务进度", QUERY_TYPE_TASK_PROGRESS),
        ("task_progress", QUERY_TYPE_TASK_PROGRESS),
    ],
)
def test_normalize_query_type_from_llm_hint(hint: str, expected: str) -> None:
    """LLM 给出的规范值或英文别名可直接采用。"""
    assert normalize_query_type(hint) == expected


def test_normalize_query_type_prefers_hint_over_message() -> None:
    """LLM 明确给出查询类型时优先于关键词推断。"""
    assert (
        normalize_query_type("任务进度", "我的报销到哪一步了")
        == QUERY_TYPE_TASK_PROGRESS
    )


def test_normalize_query_type_ignores_blank() -> None:
    """空值与 None 不应被识别为某类查询。"""
    assert normalize_query_type(None, "", "   ") is None


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("查询任务 MOCK-2046C424 的状态", "MOCK-2046C424"),
        # 受理号由开发桩生成，是十六进制串，可能以字母开头
        ("MOCK-F9D673BA 到哪一步了", "MOCK-F9D673BA"),
        ("查询任务 TK20240315001 的状态", "TK20240315001"),
        ("我的报销到哪一步了", None),
        ("2026-09-20 提交的报销", None),
        ("我还剩几天年假", None),
    ],
)
def test_extract_task_ref(message: str, expected: str | None) -> None:
    """单据号识别：受理号/UUID 命中，日期与普通表述不误判为单据号。"""
    assert extract_task_ref(message) == expected


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("我的请假批了吗", "leave"),
        ("我的年假申请到哪了", "leave"),
        ("那笔报销走到哪了", "expense"),
        ("我的差旅申请进度", "travel"),
        ("用印申请到哪一步了", "seal"),
        ("物资领用的进度", "material"),
        ("我提交的任务到哪一步了", None),
        ("查询状态", None),
    ],
)
def test_infer_business_type(message: str, expected: str | None) -> None:
    """从消息里识别用户关心的具体业务，用于把任务进度查询收窄到该业务。"""
    assert infer_business_type(message) == expected


# ---------------------------------------------------------------- 时间范围


def test_time_range_defaults_to_recent_30_days() -> None:
    """未提及时默认最近 30 天（场景 03 §5.2）。"""
    span = resolve_time_range("我的任务进度", now=NOW)
    assert span.label == "最近30天"
    assert span.end == NOW
    assert (span.end - span.start).days == 30


def test_time_range_parses_recent_days() -> None:
    span = resolve_time_range("最近7天的报销", now=NOW)
    assert span.label == "最近7天"
    assert (span.end - span.start).days == 7


def test_time_range_parses_last_month() -> None:
    span = resolve_time_range("我上个月的报销到哪一步了", now=NOW)
    assert span.label == "上个月"
    assert span.start == datetime(2026, 8, 1)
    assert span.end == datetime(2026, 8, 31, 23, 59, 59)


def test_time_range_parses_this_week() -> None:
    span = resolve_time_range("本周的任务进度", now=NOW)
    assert span.label == "本周"
    assert span.start == datetime(2026, 9, 14)  # 2026-09-20 是周日
    assert span.end == NOW


def test_time_range_parses_explicit_month() -> None:
    span = resolve_time_range("2026年1月的报销记录", now=NOW)
    assert span.start == datetime(2026, 1, 1)
    assert span.end == datetime(2026, 1, 31, 23, 59, 59)


def test_time_range_clamps_to_one_year() -> None:
    """时间范围上限：最早不超过 1 年（场景 03 §5.2）。"""
    span = resolve_time_range("最近400天的任务", now=NOW)
    assert (span.end - span.start).days <= 365


def test_time_range_never_starts_in_future() -> None:
    """解析结果必须落在 now 之前，避免因时区/口径产生空窗口。"""
    for message in ("上个月", "本周", "今年", "2026年8月", "最近30天"):
        span = resolve_time_range(message, now=NOW)
        assert span.start < span.end <= NOW


# ---------------------------------------------------------------- 列表格式化


def _task(
    title: str = "请假（年假）",
    task_type: str = "leave",
    status: str = "审批中",
    created_at: datetime = datetime(2026, 9, 15, 9, 0),
    amount: Decimal | None = None,
    approvers: tuple[str, ...] = (),
) -> TaskView:
    return TaskView(
        title=title,
        task_type=task_type,
        status=status,
        created_at=created_at,
        amount=amount,
        pending_approvers=approvers,
    )


def _range(days: int = 30) -> TimeRange:
    from datetime import timedelta

    return TimeRange(start=NOW - timedelta(days=days), end=NOW, label=f"最近{days}天")


def test_format_task_list_shows_status_and_approver() -> None:
    """列表包含状态、时间与当前待审人——用户问的是"到哪一步了"。"""
    text = format_task_list(
        [_task(status="审批中", approvers=("主管-张三",), created_at=datetime(2026, 9, 15, 9, 0))],
        time_range=_range(),
        total=1,
    )
    assert "请假（年假）" in text
    assert "审批中" in text
    assert "主管-张三" in text
    assert "2026-09-15" in text


def test_format_task_list_orders_as_given_and_notes_total() -> None:
    """按传入顺序（时间倒序）展示，超出展示条数时提示总数。"""
    views = [_task(title=f"单据{i}") for i in range(1, 8)]
    text = format_task_list(views, time_range=_range(), total=12)
    assert text.index("单据1") < text.index("单据2")
    assert "12" in text


def test_format_task_list_reports_empty() -> None:
    """无结果时给出场景 03 §8.1 的友好提示。"""
    text = format_task_list([], time_range=_range(), total=0)
    assert "未找到" in text


def test_format_task_list_names_the_subject() -> None:
    """按业务收窄时要说清查的是哪一类，否则用户以为查的是全部单据。"""
    text = format_task_list(
        [_task(title="请假（年假）")], time_range=_range(), total=1, subject="请假"
    )
    assert "1 条请假记录" in text

    empty = format_task_list([], time_range=_range(), total=0, subject="请假")
    assert "请假记录" in empty


def test_format_task_list_does_not_leak_other_business_amount() -> None:
    """金额只在该业务确有金额时展示，避免把空金额渲染成 0。"""
    text = format_task_list([_task(amount=None)], time_range=_range(), total=1)
    assert "￥" not in text


def test_format_task_detail_includes_approval_chain() -> None:
    """按单据查询时返回详情与审批链。"""
    text = format_task_detail(
        _task(title="报销（酒店）", amount=Decimal("500.00")),
        external_id="MOCK-2046C424",
        approvals=[(1, "主管-张三", "待审"), (2, "总监-李四", "未开始")],
    )
    assert "MOCK-2046C424" in text
    assert "500.00" in text
    assert "主管-张三" in text
    assert "总监-李四" in text


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("pending", "待审"),
        ("approve", "已通过"),
        ("reject", "已驳回"),
        ("done", "已处理"),
        ("skipped", "已跳过"),
        (None, "未知"),
        ("weird", "weird"),
    ],
)
def test_approval_status_label(status: str | None, expected: str) -> None:
    """审批状态用审批自己的词表。

    `approvals.status` 与 `tasks.status` 是两套取值：复用任务标签会把审批的
    pending 显示成「待处理」、approve 直接漏出英文原值。
    """
    assert approval_status_label(status) == expected


# ---------------------------------------------------------------- 假期余额


def test_format_leave_balance_lists_entries() -> None:
    """余额回复含额度、已用与剩余（场景 03 §5.5）。"""
    text = format_leave_balance(
        [
            LeaveBalanceEntry(leave_type="年假", quota=10, used=2),
            LeaveBalanceEntry(leave_type="调休", quota=5, used=0),
        ],
        pending=[],
        as_of=NOW,
        source="HR 系统",
    )
    assert "年假" in text and "10" in text and "2" in text and "8" in text
    assert "调休" in text
    assert "HR 系统" in text
    assert "2026-09-20" in text


def test_format_leave_balance_marks_unlimited() -> None:
    """无限制假期不渲染成具体天数。"""
    text = format_leave_balance(
        [LeaveBalanceEntry(leave_type="事假", quota=999, used=0)],
        pending=[],
        as_of=NOW,
        source="本地默认额度",
    )
    assert "不限" in text
    assert "999" not in text


def test_format_leave_balance_mentions_pending_requests() -> None:
    """在途请假单要让用户看到进度，否则"批了吗"得不到回答。"""
    text = format_leave_balance(
        [LeaveBalanceEntry(leave_type="年假", quota=10, used=0)],
        pending=[_task(title="请假（年假）", status="审批中", approvers=("主管-张三",))],
        as_of=NOW,
        source="HR 系统",
    )
    assert "审批中" in text
    assert "主管-张三" in text


def test_format_leave_balance_degrades_honestly() -> None:
    """HR 不可用时要如实说明数据来源，不能把默认额度当权威数据。"""
    text = format_leave_balance(
        [LeaveBalanceEntry(leave_type="年假", quota=10, used=0)],
        pending=[],
        as_of=NOW,
        source="本地默认额度（HR 系统暂时不可用，数据可能不是最新）",
    )
    assert "HR 系统暂时不可用" in text
