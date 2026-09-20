# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""审批规则条件匹配与「无需审批」语义测试（补齐设计 §12 偏离项 4）。

覆盖：按槽位条件分支（印章类型/天数/价值）、条件规则优先于兜底规则、
规则存在但本次未匹配 → 无需审批（而不是报错或猜测）。

组织快照沿用 `_org()`：公司（主管 ceo）→ 技术部（主管 mgr），emp 属技术部。
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.admin_ai.core.approval.conditions import build_rule_context
from app.admin_ai.core.approval.router import RoutingError, match_rules, resolve_chain
from app.admin_ai.db.models import ApproverType
from tests.admin_ai.test_core.test_approval_router import _org, _rule


def _resolve(rules, *, business_type: str, slots: dict, applicant_id: str = "emp"):
    """用槽位构造上下文后求解审批链。"""
    return resolve_chain(
        rules=rules,
        snapshot=_org(),
        applicant_id=applicant_id,
        business_type=business_type,
        amount=None,
        context=build_rule_context(business_type, slots),
    )


# ---------------------------------------------------------------- 条件匹配基础

def test_condition_rule_wins_over_catch_all() -> None:
    """同一步骤内条件规则优先于兜底规则（不合并成多人）。"""
    rules = [
        _rule("r1", business_type="travel", condition={"slot": "days", "op": "gt", "value": 5},
              approver_type=ApproverType.PARENT_DEPT_MANAGER.value),
        _rule("r2", business_type="travel", approver_type=ApproverType.SELF_DEPT_MANAGER.value),
    ]
    outcome = _resolve(rules, business_type="travel", slots={"start_date": "2026-09-01", "end_date": "2026-09-08"})
    assert [s.approver_id for s in outcome.steps] == ["ceo"]  # 8 天 > 5 → 上级部门主管

    outcome = _resolve(rules, business_type="travel", slots={"start_date": "2026-09-01", "end_date": "2026-09-03"})
    assert [s.approver_id for s in outcome.steps] == ["mgr"]  # 3 天 → 兜底：本部门主管


def test_condition_on_enum_slot_branches_by_seal_type() -> None:
    """按印章类型分支：合同章 → 法务，其余 → 部门主管。"""
    org_rules = [
        _rule("legal", business_type="seal", approver_type=ApproverType.ROLE.value,
              approver_param="legal", condition={"slot": "seal_type", "op": "eq", "value": "合同章"}),
        _rule("mgr", business_type="seal", approver_type=ApproverType.SELF_DEPT_MANAGER.value),
    ]
    outcome = resolve_chain(
        rules=org_rules,
        snapshot=_org(extra_roles={"legal": ["lawyer"]}),
        applicant_id="emp",
        business_type="seal",
        context=build_rule_context("seal", {"seal_type": "合同章"}),
    )
    assert [s.approver_id for s in outcome.steps] == ["lawyer"]

    outcome = resolve_chain(
        rules=org_rules,
        snapshot=_org(extra_roles={"legal": ["lawyer"]}),
        applicant_id="emp",
        business_type="seal",
        context=build_rule_context("seal", {"seal_type": "公章"}),
    )
    assert [s.approver_id for s in outcome.steps] == ["mgr"]


# ---------------------------------------------------------------- 业务分支

LEAVE_RULES = [
    _rule("short", business_type="leave", condition={"slot": "days", "op": "lte", "value": 2},
          approver_type=ApproverType.SELF_DEPT_MANAGER.value),
    _rule("long1", business_type="leave", condition={"slot": "days", "op": "gt", "value": 2},
          approver_type=ApproverType.SELF_DEPT_MANAGER.value, step_order=1),
    _rule("long2", business_type="leave", condition={"slot": "days", "op": "gt", "value": 2},
          approver_type=ApproverType.ROLE.value, approver_param="hr", step_order=2),
    _rule("fallback", business_type="leave", approver_type=ApproverType.SELF_DEPT_MANAGER.value),
]


def test_leave_two_days_single_level() -> None:
    """请假 2 天（≤2）→ 主管单级（场景 05）。"""
    outcome = _resolve(LEAVE_RULES, business_type="leave",
                       slots={"leave_type": "年假", "start_date": "2026-09-25", "end_date": "2026-09-26"})
    assert [(s.step, s.approver_id) for s in outcome.steps] == [(1, "mgr")]


def test_leave_more_than_two_days_adds_hr_step() -> None:
    """请假 3 天（>2）→ 主管 + HR 复核两级（场景 05）。"""
    outcome = resolve_chain(
        rules=LEAVE_RULES,
        snapshot=_org(extra_roles={"hr": ["hr01"]}),
        applicant_id="emp",
        business_type="leave",
        context=build_rule_context("leave", {"start_date": "2026-09-21", "end_date": "2026-09-23"}),
    )
    assert [(s.step, s.approver_id) for s in outcome.steps] == [(1, "mgr"), (2, "hr01")]


def test_leave_falls_back_when_days_unknown() -> None:
    """日期缺失算不出天数 → 兜底规则（主管审批），不静默放行。"""
    outcome = _resolve(LEAVE_RULES, business_type="leave", slots={"leave_type": "年假"})
    assert [(s.step, s.approver_id) for s in outcome.steps] == [(1, "mgr")]


ASSET_RULES = [
    _rule("big", business_type="asset", amount_min=Decimal("5000"),
          approver_type=ApproverType.PARENT_DEPT_MANAGER.value),
    _rule("any", business_type="asset", approver_type=ApproverType.SELF_DEPT_MANAGER.value),
]


def test_asset_by_value_threshold() -> None:
    """资产按单项价值分级：>5000 → 总监；≤5000 或价值未知 → 主管（场景 09）。"""
    outcome = resolve_chain(
        rules=ASSET_RULES, snapshot=_org(), applicant_id="emp", business_type="asset",
        amount=Decimal("6000"), context=build_rule_context("asset", {"asset_name": "笔记本"}),
    )
    assert [s.approver_id for s in outcome.steps] == ["ceo"]

    outcome = resolve_chain(
        rules=ASSET_RULES, snapshot=_org(), applicant_id="emp", business_type="asset",
        amount=Decimal("3000"), context=build_rule_context("asset", {"asset_name": "显示器"}),
    )
    assert [s.approver_id for s in outcome.steps] == ["mgr"]

    outcome = resolve_chain(
        rules=ASSET_RULES, snapshot=_org(), applicant_id="emp", business_type="asset",
        amount=None, context=build_rule_context("asset", {"asset_name": "显示器"}),
    )
    assert [s.approver_id for s in outcome.steps] == ["mgr"]


# ---------------------------------------------------------------- 无需审批语义

def test_rules_exist_but_nothing_matches_means_no_approval() -> None:
    """规则存在但本次不匹配 → 无需审批（场景 04：单价 ≤100 的物资不走审批）。"""
    rules = [_rule("premium", business_type="material", amount_min=Decimal("100"),
                   approver_type=ApproverType.SELF_DEPT_MANAGER.value)]
    outcome = resolve_chain(
        rules=rules, snapshot=_org(), applicant_id="emp", business_type="material",
        amount=Decimal("30"), context=build_rule_context("material", {"item_name": "A4纸"}),
    )
    assert outcome.requires_approval is False
    assert outcome.steps == ()


def test_no_rules_at_all_is_config_error() -> None:
    """该业务完全没有启用规则 → 配置缺失，仍按 RoutingError 转人工（不静默放行）。"""
    with pytest.raises(RoutingError) as exc:
        resolve_chain(
            rules=[], snapshot=_org(), applicant_id="emp", business_type="seal", amount=None,
            context=build_rule_context("seal", {"seal_type": "公章"}),
        )
    assert exc.value.reason == "no_rule"


def test_match_rules_requires_condition_to_hold() -> None:
    """match_rules 同时校验金额区间与条件。"""
    rules = [
        _rule("r1", business_type="seal", condition={"slot": "seal_type", "op": "eq", "value": "合同章"}),
        _rule("r2", business_type="seal"),
    ]
    matched = match_rules(rules, "seal", None, build_rule_context("seal", {"seal_type": "合同章"}))
    assert [r.id for r in matched] == ["r1"]  # 条件成立 → 只保留条件规则

    matched = match_rules(rules, "seal", None, build_rule_context("seal", {"seal_type": "公章"}))
    assert [r.id for r in matched] == ["r2"]  # 条件不成立 → 兜底规则
