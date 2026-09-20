# Copyright 2026  Admin AI Team, All rights reserved.
"""审批路由算法测试（评审 B-2；设计 §4 与 §9 的 T-1~T-5、T-7）。

算法为纯函数：输入规则 + 组织快照，输出审批链或 RoutingError，不触碰数据库。
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from app.admin_ai.core.approval.router import (
    DelegationInfo,
    DepartmentInfo,
    OrgSnapshot,
    RoutingError,
    RuleInfo,
    UserInfo,
    match_rules,
    resolve_chain,
)
from app.admin_ai.db.models import ApprovalMode, ApproverType, utc_now

# ---------------------------------------------------------------- 构造工具

def _dept(
    dept_id: str,
    name: str,
    parent_id: str | None = None,
    manager_id: str | None = None,
    path: str | None = None,
    level: int = 1,
) -> DepartmentInfo:
    return DepartmentInfo(
        id=dept_id,
        name=name,
        parent_id=parent_id,
        path=path or f"/{name}",
        level=level,
        manager_id=manager_id,
    )


def _user(
    user_id: str,
    department_id: str | None = None,
    role: str = "employee",
    is_active: bool = True,
) -> UserInfo:
    return UserInfo(
        id=user_id,
        name=user_id,
        role=role,
        is_active=is_active,
        is_deleted=False,
        department_id=department_id,
    )


def _rule(
    rule_id: str,
    business_type: str = "expense",
    approver_type: str = ApproverType.SELF_DEPT_MANAGER.value,
    step_order: int = 1,
    amount_min: Decimal | None = None,
    amount_max: Decimal | None = None,
    approver_param: str | None = None,
    approval_mode: str = ApprovalMode.ANY_ONE.value,
    required: bool = True,
    enabled: bool = True,
) -> RuleInfo:
    return RuleInfo(
        id=rule_id,
        business_type=business_type,
        amount_min=amount_min,
        amount_max=amount_max,
        step_order=step_order,
        approver_type=approver_type,
        approver_param=approver_param,
        approval_mode=approval_mode,
        required=required,
        enabled=enabled,
    )


EXPENSE_RULES = [
    _rule("r1", amount_min=Decimal("0"), amount_max=Decimal("2000")),
    _rule(
        "r2",
        approver_type=ApproverType.PARENT_DEPT_MANAGER.value,
        amount_min=Decimal("2000"),
    ),
    _rule("r3", step_order=2, amount_min=Decimal("2000")),
]


def _org(*, dept_manager: str | None = "mgr", tech_manager_active: bool = True) -> OrgSnapshot:
    """公司 → 技术部 → 后端组；公司主管 ceo，技术部主管 mgr。"""
    departments = [
        _dept("c", "公司", level=1, manager_id="ceo", path="/公司"),
        _dept("t", "技术部", parent_id="c", level=2, manager_id=dept_manager, path="/公司/技术部"),
        _dept("b", "后端组", parent_id="t", level=3, manager_id=None, path="/公司/技术部/后端组"),
    ]
    users = [
        _user("ceo", department_id="c", role="gm"),
        _user("mgr", department_id="t", role="manager", is_active=tech_manager_active),
        _user("emp", department_id="t"),
        _user("intern", department_id="b"),
    ]
    return OrgSnapshot(
        departments={d.id: d for d in departments},
        users={u.id: u for u in users},
    )


# ---------------------------------------------------------------- 规则匹配

def test_match_rules_by_amount_range() -> None:
    """金额区间为「含 min、不含 max」；未配置区间的规则不参与金额匹配。"""
    matched = match_rules(EXPENSE_RULES, "expense", Decimal("1500"))
    assert [r.id for r in matched] == ["r1"]

    matched = match_rules(EXPENSE_RULES, "expense", Decimal("3000"))
    assert [r.id for r in matched] == ["r2", "r3"]


def test_match_rules_boundary_is_inclusive_min_exclusive_max() -> None:
    """2000 元整应命中 >2000 区间，而非 ≤2000 区间。"""
    matched = match_rules(EXPENSE_RULES, "expense", Decimal("2000"))
    assert [r.id for r in matched] == ["r2", "r3"]


def test_match_rules_without_amount_only_matches_null_range() -> None:
    """金额为空（如用印）时只匹配区间为 NULL 的规则。"""
    rules = EXPENSE_RULES + [_rule("seal", business_type="seal", approver_type=ApproverType.SELF_DEPT_MANAGER.value)]
    assert [r.id for r in match_rules(rules, "seal", None)] == ["seal"]
    # 带金额区间的规则不能用于无金额业务
    assert match_rules(EXPENSE_RULES, "expense", None) == []


def test_match_rules_skips_disabled_and_other_business() -> None:
    """停用规则与其他业务类型的规则都不参与匹配。"""
    rules = EXPENSE_RULES + [_rule("off", enabled=False, approver_type=ApproverType.TOP_DEPT_MANAGER.value)]
    assert "off" not in [r.id for r in match_rules(rules, "expense", Decimal("100"))]


# ---------------------------------------------------------------- T-1 / T-2

def test_t1_small_expense_routes_to_dept_manager() -> None:
    """T-1 报销 1500 元（≤2000）→ 审批链 = [主管]。"""
    outcome = resolve_chain(
        rules=EXPENSE_RULES,
        snapshot=_org(),
        applicant_id="emp",
        business_type="expense",
        amount=Decimal("1500"),
    )
    assert [(s.step, s.approver_id) for s in outcome.steps] == [(1, "mgr")]
    assert outcome.steps[0].source == ApproverType.SELF_DEPT_MANAGER.value


def test_t2_large_expense_routes_two_levels_in_order() -> None:
    """T-2 报销 3000 元（>2000）→ 审批链 = [总监, 主管]，顺序正确。"""
    outcome = resolve_chain(
        rules=EXPENSE_RULES,
        snapshot=_org(),
        applicant_id="emp",
        business_type="expense",
        amount=Decimal("3000"),
    )
    assert [(s.step, s.approver_id) for s in outcome.steps] == [(1, "ceo"), (2, "mgr")]
    assert outcome.steps[0].source == ApproverType.PARENT_DEPT_MANAGER.value
    assert outcome.steps[1].source == ApproverType.SELF_DEPT_MANAGER.value


def test_same_approver_in_two_steps_is_deduplicated() -> None:
    """设计 §4.2 3c：同一链中审批人不得重复，去重保留靠前的一步。"""
    org = _org(dept_manager="ceo")  # 技术部主管与公司主管为同一人
    outcome = resolve_chain(
        rules=EXPENSE_RULES,
        snapshot=org,
        applicant_id="emp",
        business_type="expense",
        amount=Decimal("3000"),
    )
    assert [(s.step, s.approver_id) for s in outcome.steps] == [(1, "ceo")]


# ---------------------------------------------------------------- T-3 / T-4

def test_t3_self_approval_ascends_to_parent_manager() -> None:
    """T-3 申请人是本部门主管 → 自动上溯到上级，不出现自审。"""
    outcome = resolve_chain(
        rules=EXPENSE_RULES,
        snapshot=_org(),
        applicant_id="mgr",
        business_type="expense",
        amount=Decimal("1500"),
    )
    assert [(s.step, s.approver_id) for s in outcome.steps] == [(1, "ceo")]


def test_t3_self_approval_at_root_fails() -> None:
    """T-3 上溯到根仍冲突 → RoutingError，不猜测审批人。"""
    with pytest.raises(RoutingError) as exc:
        resolve_chain(
            rules=EXPENSE_RULES,
            snapshot=_org(),
            applicant_id="ceo",
            business_type="expense",
            amount=Decimal("1500"),
        )
    assert exc.value.reason == "self_approval"


def test_t4_department_without_manager_fails() -> None:
    """T-4 部门无主管 → RoutingError（宁可转人工，不猜审批人）。"""
    with pytest.raises(RoutingError) as exc:
        resolve_chain(
            rules=EXPENSE_RULES,
            snapshot=_org(dept_manager=None),
            applicant_id="emp",
            business_type="expense",
            amount=Decimal("1500"),
        )
    assert exc.value.reason == "no_manager"


def test_applicant_without_department_fails() -> None:
    """申请人无部门（组织数据缺失）→ RoutingError。"""
    org = _org()
    org.users["nodep"] = _user("nodep")
    with pytest.raises(RoutingError) as exc:
        resolve_chain(
            rules=EXPENSE_RULES,
            snapshot=org,
            applicant_id="nodep",
            business_type="expense",
            amount=Decimal("1500"),
        )
    assert exc.value.reason == "no_department"


def test_inactive_manager_ascends_to_parent() -> None:
    """设计 §4.2 3b：审批人已停用 → 上溯一级。"""
    outcome = resolve_chain(
        rules=EXPENSE_RULES,
        snapshot=_org(tech_manager_active=False),
        applicant_id="emp",
        business_type="expense",
        amount=Decimal("1500"),
    )
    assert [s.approver_id for s in outcome.steps] == ["ceo"]


# ---------------------------------------------------------------- T-7

def test_t7_business_type_without_rules_fails() -> None:
    """T-7 未配置审批规则的新业务类型 → RoutingError（调用方转人工指派）。"""
    with pytest.raises(RoutingError) as exc:
        resolve_chain(
            rules=EXPENSE_RULES,
            snapshot=_org(),
            applicant_id="emp",
            business_type="seal",
            amount=None,
        )
    assert exc.value.reason == "no_rule"


def test_optional_step_is_skipped_when_unresolvable() -> None:
    """required=False 的步骤解析不出来时跳过，不影响必要步骤。"""
    rules = [
        _rule("r1", amount_min=Decimal("0"), amount_max=Decimal("2000")),
        _rule(
            "r2",
            approver_type=ApproverType.ROLE.value,
            approver_param="finance",
            required=False,
        ),
    ]
    outcome = resolve_chain(
        rules=rules,
        snapshot=_org(),
        applicant_id="emp",
        business_type="expense",
        amount=Decimal("100"),
    )
    assert [s.approver_id for s in outcome.steps] == ["mgr"]


def test_required_step_unresolvable_fails() -> None:
    """required=True 的步骤解析失败 → RoutingError。"""
    rules = [
        _rule("r1", amount_min=Decimal("0"), amount_max=Decimal("2000")),
        _rule("r2", approver_type=ApproverType.ROLE.value, approver_param="finance"),
    ]
    with pytest.raises(RoutingError) as exc:
        resolve_chain(
            rules=rules,
            snapshot=_org(),
            applicant_id="emp",
            business_type="expense",
            amount=Decimal("100"),
        )
    assert exc.value.reason == "no_role_member"


# ---------------------------------------------------------------- 角色类审批人

def test_role_approver_collects_all_members_in_one_step() -> None:
    """D-2 任一人通过：角色对应多人时全部加入同一相邻步骤。"""
    org = _org()
    org.users["f1"] = _user("f1", department_id="c", role="finance")
    org.users["f2"] = _user("f2", department_id="c", role="finance")
    rules = [
        _rule(
            "r1",
            approver_type=ApproverType.ROLE.value,
            approver_param="finance",
            amount_min=Decimal("0"),
            amount_max=Decimal("2000"),
        ),
        _rule(
            "r2",
            step_order=2,
            approver_type=ApproverType.SELF_DEPT_MANAGER.value,
            amount_min=Decimal("0"),
            amount_max=Decimal("2000"),
        ),
    ]
    outcome = resolve_chain(
        rules=rules,
        snapshot=org,
        applicant_id="emp",
        business_type="expense",
        amount=Decimal("100"),
    )
    assert [(s.step, s.approver_id) for s in outcome.steps] == [(1, "f1"), (1, "f2"), (2, "mgr")]
    assert {s.mode for s in outcome.steps if s.step == 1} == {ApprovalMode.ANY_ONE.value}


def test_role_approver_excludes_applicant() -> None:
    """角色成员包含申请人时剔除申请人，不出现自审。"""
    org = _org()
    org.users["mgr"] = _user("mgr", department_id="t", role="finance")
    rules = [
        _rule(
            "r1",
            approver_type=ApproverType.ROLE.value,
            approver_param="finance",
            amount_min=Decimal("0"),
            amount_max=Decimal("2000"),
        )
    ]
    with pytest.raises(RoutingError) as exc:
        resolve_chain(
            rules=rules,
            snapshot=org,
            applicant_id="mgr",
            business_type="expense",
            amount=Decimal("100"),
        )
    assert exc.value.reason == "no_role_member"


def test_co_sign_mode_is_carried_on_steps() -> None:
    """会签（D-2 可选项）：步骤上带 all_must 标记，交由审批流转层解释。"""
    rules = [
        _rule(
            "r1",
            approver_type=ApproverType.ROLE.value,
            approver_param="finance",
            amount_min=Decimal("0"),
            amount_max=Decimal("2000"),
            approval_mode=ApprovalMode.ALL_MUST.value,
        )
    ]
    org = _org()
    org.users["f1"] = _user("f1", department_id="c", role="finance")
    outcome = resolve_chain(
        rules=rules,
        snapshot=org,
        applicant_id="emp",
        business_type="expense",
        amount=Decimal("100"),
    )
    assert all(s.mode == ApprovalMode.ALL_MUST.value for s in outcome.steps)


def test_user_approver_type_uses_param_as_user_id() -> None:
    """user:<uuid> 兜底类型直接指定审批人。"""
    rules = [
        _rule(
            "r1",
            approver_type=ApproverType.USER.value,
            approver_param="ceo",
            amount_min=Decimal("0"),
            amount_max=Decimal("2000"),
        )
    ]
    outcome = resolve_chain(
        rules=rules,
        snapshot=_org(),
        applicant_id="emp",
        business_type="expense",
        amount=Decimal("100"),
    )
    assert [s.approver_id for s in outcome.steps] == ["ceo"]


def test_top_dept_manager_resolves_root_manager() -> None:
    """top_dept_manager 沿 path 上溯到顶层部门主管。"""
    rules = [
        _rule(
            "r1",
            approver_type=ApproverType.TOP_DEPT_MANAGER.value,
            amount_min=Decimal("0"),
            amount_max=Decimal("2000"),
        )
    ]
    outcome = resolve_chain(
        rules=rules,
        snapshot=_org(),
        applicant_id="intern",
        business_type="expense",
        amount=Decimal("100"),
    )
    assert [s.approver_id for s in outcome.steps] == ["ceo"]


# ---------------------------------------------------------------- T-5 代理审批

def test_t5_active_delegation_replaces_approver() -> None:
    """T-5 审批人休假且有生效委派 → 替换为被委托人并记录 delegated_from。"""
    org = _org()
    org.users["deputy"] = _user("deputy", department_id="t", role="manager")
    now = utc_now()
    delegation = DelegationInfo(
        delegator_id="mgr",
        delegate_id="deputy",
        business_types=None,
        start_at=now - timedelta(days=1),
        end_at=now + timedelta(days=1),
        is_active=True,
    )
    outcome = resolve_chain(
        rules=EXPENSE_RULES,
        snapshot=org,
        applicant_id="emp",
        business_type="expense",
        amount=Decimal("1500"),
        delegations=[delegation],
        occurred_at=now,
    )
    assert [(s.approver_id, s.delegated_from) for s in outcome.steps] == [("deputy", "mgr")]


def test_expired_delegation_is_ignored() -> None:
    """过期委派不生效。"""
    org = _org()
    org.users["deputy"] = _user("deputy", department_id="t", role="manager")
    now = utc_now()
    delegation = DelegationInfo(
        delegator_id="mgr",
        delegate_id="deputy",
        business_types=None,
        start_at=now - timedelta(days=5),
        end_at=now - timedelta(days=1),
        is_active=True,
    )
    outcome = resolve_chain(
        rules=EXPENSE_RULES,
        snapshot=org,
        applicant_id="emp",
        business_type="expense",
        amount=Decimal("1500"),
        delegations=[delegation],
        occurred_at=now,
    )
    assert [s.approver_id for s in outcome.steps] == ["mgr"]


def test_delegation_scoped_to_business_type() -> None:
    """委派限定业务类型时，其他业务不受影响。"""
    org = _org()
    org.users["deputy"] = _user("deputy", department_id="t", role="manager")
    now = utc_now()
    delegation = DelegationInfo(
        delegator_id="mgr",
        delegate_id="deputy",
        business_types=["seal"],
        start_at=now - timedelta(days=1),
        end_at=now + timedelta(days=1),
        is_active=True,
    )
    outcome = resolve_chain(
        rules=EXPENSE_RULES,
        snapshot=org,
        applicant_id="emp",
        business_type="expense",
        amount=Decimal("1500"),
        delegations=[delegation],
        occurred_at=now,
    )
    assert [s.approver_id for s in outcome.steps] == ["mgr"]


def test_delegation_to_applicant_fails_instead_of_self_approval() -> None:
    """被委托人恰为申请人时不静默放行，转人工。"""
    org = _org()
    now = utc_now()
    delegation = DelegationInfo(
        delegator_id="mgr",
        delegate_id="emp",
        business_types=None,
        start_at=now - timedelta(days=1),
        end_at=now + timedelta(days=1),
        is_active=True,
    )
    with pytest.raises(RoutingError) as exc:
        resolve_chain(
            rules=EXPENSE_RULES,
            snapshot=org,
            applicant_id="emp",
            business_type="expense",
            amount=Decimal("1500"),
            delegations=[delegation],
            occurred_at=now,
        )
    assert exc.value.reason == "delegation_self"
