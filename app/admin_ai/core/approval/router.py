# Copyright 2026  Admin AI Team, All rights reserved.
"""审批路由算法（评审 B-2，设计见 docs/architecture/组织架构与审批路由设计.md §4）。

本模块是**纯函数**：输入审批规则与组织快照，输出有序审批链或 `RoutingError`，
不触碰数据库（装载见 `repository.py`）。这样算法可以脱离 PG 独立测试，
也便于将来替换组织数据来源（HR 同步 / CSV 导入）。

核心原则：**宁可转人工，也不猜测审批人**——错误路由会让审批失去公司内部授权效力。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from app.admin_ai.db.models import ApprovalMode, ApproverType, utc_now


class RoutingError(Exception):
    """无法解析出审批链。

    `reason` 为机器可读原因（用于告警分类与「待人工指派」标记），`message` 为中文说明。
    """

    def __init__(self, reason: str, message: str = "") -> None:
        super().__init__(message or reason)
        self.reason = reason
        self.message = message or reason

    def __repr__(self) -> str:
        return f"<RoutingError reason={self.reason} message={self.message}>"


@dataclass(frozen=True)
class DepartmentInfo:
    """部门快照。"""
    id: str
    name: str
    parent_id: str | None
    path: str
    level: int
    manager_id: str | None


@dataclass(frozen=True)
class UserInfo:
    """用户快照（仅路由所需字段，不含 L3 身份信息）。"""
    id: str
    name: str
    role: str
    is_active: bool
    is_deleted: bool
    department_id: str | None

    @property
    def usable(self) -> bool:
        """在职且未删除，可作为审批人。"""
        return self.is_active and not self.is_deleted


@dataclass(frozen=True)
class RuleInfo:
    """审批规则快照。"""
    id: str
    business_type: str
    amount_min: Decimal | None
    amount_max: Decimal | None
    step_order: int
    approver_type: str
    approver_param: str | None
    approval_mode: str = ApprovalMode.ANY_ONE.value
    required: bool = True
    enabled: bool = True


@dataclass(frozen=True)
class DelegationInfo:
    """代理审批委派快照。`business_types=None` 表示全部业务类型。"""
    delegator_id: str
    delegate_id: str
    start_at: datetime
    end_at: datetime
    business_types: Sequence[str] | None = None
    is_active: bool = True


@dataclass(frozen=True)
class OrgSnapshot:
    """组织快照：路由所需的全部组织数据。"""
    departments: Mapping[str, DepartmentInfo]
    users: Mapping[str, UserInfo]

    def department_chain(self, department_id: str | None) -> list[DepartmentInfo]:
        """自身 → 上级 → … → 根（缺失节点安全截断，环形保护）。"""
        chain: list[DepartmentInfo] = []
        seen: set[str] = set()
        current_id = department_id
        while current_id and current_id not in seen:
            department = self.departments.get(current_id)
            if department is None:
                break
            chain.append(department)
            seen.add(current_id)
            current_id = department.parent_id
        return chain


@dataclass(frozen=True)
class ApprovalStep:
    """审批链中的一环。同一 `step` 的多条记录属于同一步骤（多人并行）。"""
    step: int
    approver_id: str
    source: str
    mode: str = ApprovalMode.ANY_ONE.value
    delegated_from: str | None = None


@dataclass(frozen=True)
class RoutingOutcome:
    """路由结果：有序审批链。"""
    steps: tuple[ApprovalStep, ...]


def match_rules(
    rules: Iterable[RuleInfo], business_type: str, amount: Decimal | None
) -> list[RuleInfo]:
    """按业务类型与金额匹配生效规则，按 step_order 升序返回。

    金额区间为「含 amount_min、不含 amount_max」；`amount` 为空时只匹配区间为 NULL 的规则
    （如用印无金额）。停用（enabled=False）规则不参与匹配。
    """
    if amount is not None and not isinstance(amount, Decimal):
        amount = Decimal(str(amount))

    matched: list[RuleInfo] = []
    for rule in rules:
        if not rule.enabled or rule.business_type != business_type:
            continue
        if amount is None:
            if rule.amount_min is None and rule.amount_max is None:
                matched.append(rule)
            continue
        if rule.amount_min is not None and amount < rule.amount_min:
            continue
        if rule.amount_max is not None and amount >= rule.amount_max:
            continue
        matched.append(rule)
    return sorted(matched, key=lambda r: r.step_order)


def resolve_chain(
    *,
    rules: Iterable[RuleInfo],
    snapshot: OrgSnapshot,
    applicant_id: str,
    business_type: str,
    amount: Decimal | None = None,
    delegations: Sequence[DelegationInfo] = (),
    occurred_at: datetime | None = None,
) -> RoutingOutcome:
    """计算审批链（设计 §4.2）。

    逐级解析审批人 → 自审拦截与上溯 → 停用上溯 → 链内去重 → 委派替换。
    任一步无法解析出审批人则抛 `RoutingError`，调用方应转人工指派而非放行。
    """
    matched = match_rules(rules, business_type, amount)
    if not matched:
        raise RoutingError(
            "no_rule",
            f"业务类型 {business_type}（金额 {amount}）未匹配到审批规则，需人工指派",
        )

    applicant = snapshot.users.get(applicant_id)
    if applicant is None:
        raise RoutingError("no_applicant", f"申请人 {applicant_id} 不存在")

    grouped: dict[int, list[RuleInfo]] = {}
    for rule in matched:
        grouped.setdefault(rule.step_order, []).append(rule)

    steps: list[ApprovalStep] = []
    seen_approvers: set[str] = set()
    required_groups = 0
    required_surviving = 0
    out_step = 0

    for step_order in sorted(grouped):
        step_rules = grouped[step_order]
        is_required = any(rule.required for rule in step_rules)
        if is_required:
            required_groups += 1

        # 步骤内成员：一条规则可能解析出多人（role 类型），多条规则共享同一 step_order 时取并集
        resolved: list[tuple[str, str]] = []
        failures: list[tuple[RuleInfo, RoutingError]] = []
        for rule in step_rules:
            try:
                for approver_id in _resolve_rule(rule, snapshot, applicant):
                    resolved.append((approver_id, rule.approver_type))
            except RoutingError as exc:
                failures.append((rule, exc))

        # 必需规则解析失败 → 整链失败（不因同一步骤其他可选规则成功而放行）
        for rule, exc in failures:
            if rule.required:
                raise exc
        if not resolved:
            continue  # 整步均为可选规则且都解析失败 → 跳过该步

        mode = step_rules[0].approval_mode
        new_members = [(aid, source) for aid, source in resolved if aid not in seen_approvers]
        if not new_members:
            continue  # 整步审批人都在更靠前的步骤里出现过（去重）
        out_step += 1
        if is_required:
            required_surviving += 1
        for approver_id, source in new_members:
            seen_approvers.add(approver_id)
            final_id, delegated_from = _apply_delegation(
                approver_id=approver_id,
                business_type=business_type,
                snapshot=snapshot,
                delegations=delegations,
                applicant_id=applicant_id,
                occurred_at=occurred_at,
            )
            steps.append(
                ApprovalStep(
                    step=out_step,
                    approver_id=final_id,
                    source=source,
                    mode=mode,
                    delegated_from=delegated_from,
                )
            )

    if not steps:
        raise RoutingError("no_approver", "未解析出任何审批人")
    if required_groups and not required_surviving:
        # 设计 §4.2 3c：去重导致必需步骤全部消失，属规则配置冲突
        raise RoutingError(
            "dedupe_removed_required", "链内去重后必需审批步骤消失，疑审批规则配置冲突"
        )
    return RoutingOutcome(steps=tuple(steps))


# ---------------------------------------------------------------- 内部解析

def _resolve_rule(rule: RuleInfo, snapshot: OrgSnapshot, applicant: UserInfo) -> list[str]:
    """解析单条规则对应的审批人（可能多人）。"""
    approver_type = rule.approver_type

    if approver_type in (
        ApproverType.SELF_DEPT_MANAGER.value,
        ApproverType.PARENT_DEPT_MANAGER.value,
        ApproverType.TOP_DEPT_MANAGER.value,
    ):
        start = _start_department(approver_type, snapshot, applicant)
        return [_resolve_department_manager(start, snapshot, applicant)]

    if approver_type == ApproverType.ROLE.value:
        role = rule.approver_param
        if not role:
            raise RoutingError("bad_rule", "role 类型规则缺少 approver_param")
        members = sorted(
            user.id
            for user in snapshot.users.values()
            if user.role == role and user.usable and user.id != applicant.id
        )
        if not members:
            raise RoutingError("no_role_member", f"角色 {role} 无可用成员")
        return members

    if approver_type == ApproverType.USER.value:
        user_id = rule.approver_param
        if not user_id:
            raise RoutingError("bad_rule", "user 类型规则缺少 approver_param")
        user = snapshot.users.get(user_id)
        if user is None or not user.usable:
            raise RoutingError("no_user", f"指定审批人 {user_id} 不存在或已停用")
        if user.id == applicant.id:
            raise RoutingError("self_approval", "指定审批人为申请人本人")
        return [user.id]

    raise RoutingError("bad_rule", f"未知的 approver_type: {approver_type}")


def _start_department(
    approver_type: str, snapshot: OrgSnapshot, applicant: UserInfo
) -> DepartmentInfo:
    """按审批人类型确定起始部门。"""
    chain = snapshot.department_chain(applicant.department_id)
    if not chain:
        raise RoutingError("no_department", "申请人未归属任何部门，无法按组织路由")

    if approver_type == ApproverType.SELF_DEPT_MANAGER.value:
        return chain[0]
    if approver_type == ApproverType.PARENT_DEPT_MANAGER.value:
        if len(chain) < 2:
            raise RoutingError("no_manager", f"部门「{chain[0].name}」无上级部门")
        return chain[1]
    # top_dept_manager：沿路径上溯到层级最小的部门（level=1 为根）
    return min(chain, key=lambda d: d.level)


def _resolve_department_manager(
    start: DepartmentInfo, snapshot: OrgSnapshot, applicant: UserInfo
) -> str:
    """解析部门主管；自审或已停用时逐级上溯（设计 §4.2 3a/3b）。"""
    seen: set[str] = set()
    last_reason = "no_manager"
    for department in snapshot.department_chain(start.id):
        if department.id in seen:
            break
        seen.add(department.id)
        if not department.manager_id:
            raise RoutingError("no_manager", f"部门「{department.name}」未设置主管")
        manager = snapshot.users.get(department.manager_id)
        if manager is None:
            raise RoutingError("no_manager", f"部门「{department.name}」主管不存在")
        if manager.id == applicant.id:
            last_reason = "self_approval"
            continue  # 自审 → 上溯一级
        if not manager.usable:
            last_reason = "no_manager"
            continue  # 已停用/离职 → 上溯一级
        return manager.id
    if last_reason == "self_approval":
        raise RoutingError("self_approval", "上溯至顶层仍为申请人本人，禁止自审")
    raise RoutingError("no_manager", "上溯至顶层仍无可用主管")


def _apply_delegation(
    *,
    approver_id: str,
    business_type: str,
    snapshot: OrgSnapshot,
    delegations: Sequence[DelegationInfo],
    applicant_id: str,
    occurred_at: datetime | None,
) -> tuple[str, str | None]:
    """生效中的委派 → 替换为被委托人，返回 (最终审批人, 原审批人)。"""
    if not delegations:
        return approver_id, None

    now = _to_naive_utc(occurred_at) if occurred_at else utc_now()
    for delegation in delegations:
        if delegation.delegator_id != approver_id or not delegation.is_active:
            continue
        if not (_to_naive_utc(delegation.start_at) <= now <= _to_naive_utc(delegation.end_at)):
            continue
        if delegation.business_types and business_type not in delegation.business_types:
            continue

        delegate = snapshot.users.get(delegation.delegate_id)
        if delegate is None or not delegate.usable:
            raise RoutingError(
                "delegation_invalid", f"委派对象 {delegation.delegate_id} 不存在或已停用"
            )
        if delegate.id == applicant_id:
            raise RoutingError("delegation_self", "委派对象为申请人本人，禁止自审")
        return delegate.id, approver_id
    return approver_id, None


def _to_naive_utc(value: datetime) -> datetime:
    """统一为无时区 UTC，兼容上游传入带时区时间的情况。"""
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)
