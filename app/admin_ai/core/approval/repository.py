# Copyright 2026  Admin AI Team, All rights reserved.
"""审批路由的数据装载与落库（DB ↔ 纯算法之间的适配层）。

装载走「一次性读全量组织快照」而不是逐步懒加载：200 人企业的部门与用户总量很小
（部门数十、用户数百），一次装载比多次往返更省事，也让 `router.resolve_chain` 保持纯函数。
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.core.approval.router import (
    DelegationInfo,
    DepartmentInfo,
    OrgSnapshot,
    RoutingOutcome,
    RuleInfo,
    UserInfo,
    resolve_chain,
)
from app.admin_ai.db.models import (
    ApprovalDelegationModel,
    ApprovalModel,
    ApprovalRuleModel,
    ApprovalStatus,
    DepartmentModel,
    TaskModel,
    UserModel,
)

# 金额槽位候选键（不同业务的槽位命名不同）
AMOUNT_SLOT_KEYS = ("amount", "total_amount", "expense_amount")


def extract_amount(slots: Mapping[str, Any] | None) -> Decimal | None:
    """从槽位中取出金额（报销/差旅等），取不到返回 None。"""
    if not slots:
        return None
    for key in AMOUNT_SLOT_KEYS:
        value = slots.get(key)
        if value is None or value == "":
            continue
        try:
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            continue
    return None


# ---------------------------------------------------------------- 模型 → 快照

def rule_info(model: ApprovalRuleModel) -> RuleInfo:
    """规则模型 → 快照。"""
    approver_type = model.approver_type
    mode = model.approval_mode
    return RuleInfo(
        id=model.id,
        business_type=model.business_type,
        amount_min=model.amount_min,
        amount_max=model.amount_max,
        step_order=model.step_order or 1,
        approver_type=approver_type.value if hasattr(approver_type, "value") else str(approver_type),
        approver_param=model.approver_param,
        approval_mode=mode.value if hasattr(mode, "value") else str(mode),
        required=bool(model.required),
        enabled=bool(model.enabled),
    )


def department_info(model: DepartmentModel) -> DepartmentInfo:
    """部门模型 → 快照。"""
    return DepartmentInfo(
        id=model.id,
        name=model.name,
        parent_id=model.parent_id,
        path=model.path,
        level=model.level or 1,
        manager_id=model.manager_id,
    )


def user_info(model: UserModel) -> UserInfo:
    """用户模型 → 快照。"""
    return UserInfo(
        id=model.id,
        name=model.name,
        role=model.role,
        is_active=bool(model.is_active),
        is_deleted=bool(model.is_deleted),
        department_id=model.department_id,
    )


def delegation_info(model: ApprovalDelegationModel) -> DelegationInfo:
    """委派模型 → 快照。"""
    return DelegationInfo(
        delegator_id=model.delegator_id,
        delegate_id=model.delegate_id,
        business_types=model.business_types,
        start_at=model.start_at,
        end_at=model.end_at,
        is_active=bool(model.is_active),
    )


# ---------------------------------------------------------------- 装载

async def load_rules(db: AsyncSession, business_type: str) -> list[RuleInfo]:
    """按业务类型装载生效规则。"""
    rows = (
        await db.execute(
            select(ApprovalRuleModel).where(
                ApprovalRuleModel.business_type == business_type,
                ApprovalRuleModel.enabled == True,  # noqa: E712
            )
        )
    ).scalars().all()
    return [rule_info(row) for row in rows]


async def load_org_snapshot(db: AsyncSession) -> OrgSnapshot:
    """装载组织快照。

    **包含已停用/离职用户**：路由需要识别「审批人已停用」并上溯，
    若在 SQL 层过滤掉就无从判断，会退化成「无主管」。
    """
    department_rows = (
        await db.execute(select(DepartmentModel).where(DepartmentModel.is_active == True))  # noqa: E712
    ).scalars().all()
    user_rows = (
        await db.execute(select(UserModel).where(UserModel.is_deleted == False))  # noqa: E712
    ).scalars().all()
    return OrgSnapshot(
        departments={row.id: department_info(row) for row in department_rows},
        users={row.id: user_info(row) for row in user_rows},
    )


async def load_delegations(db: AsyncSession) -> list[DelegationInfo]:
    """装载生效委派，新的优先（同一委托人存在多条时取最近创建的一条）。"""
    rows = (
        await db.execute(
            select(ApprovalDelegationModel)
            .where(ApprovalDelegationModel.is_active == True)  # noqa: E712
            .order_by(ApprovalDelegationModel.created_at.desc())
        )
    ).scalars().all()
    return [delegation_info(row) for row in rows]


# ---------------------------------------------------------------- 路由入口

async def route_approval(
    db: AsyncSession,
    *,
    business_type: str,
    applicant_id: str,
    amount: Decimal | None = None,
    slots: Mapping[str, Any] | None = None,
    occurred_at: datetime | None = None,
) -> RoutingOutcome:
    """装载组织数据并计算审批链；无法解析时抛 `RoutingError`。

    `amount` 未显式传入时从 `slots` 推断。
    """
    resolved_amount = amount if amount is not None else extract_amount(slots)
    return resolve_chain(
        rules=await load_rules(db, business_type),
        snapshot=await load_org_snapshot(db),
        applicant_id=applicant_id,
        business_type=business_type,
        amount=resolved_amount,
        delegations=await load_delegations(db),
        occurred_at=occurred_at,
    )


def build_approval_rows(task_id: str, outcome: RoutingOutcome) -> list[ApprovalModel]:
    """审批链 → 待落库的审批记录（同一步骤多人时为多行）。"""
    return [
        ApprovalModel(
            task_id=task_id,
            approver_id=step.approver_id,
            step=step.step,
            status=ApprovalStatus.PENDING.value,
            approver_source=step.source,
            mode=step.mode,
            delegated_from=step.delegated_from,
        )
        for step in outcome.steps
    ]


def first_step_approver(outcome: RoutingOutcome) -> str | None:
    """审批链第一步的审批人（写入 `tasks.approver_id` 便于列表展示）。"""
    return outcome.steps[0].approver_id if outcome.steps else None


def set_routing_note(task: TaskModel, *, reason: str, message: str) -> None:
    """把「无法解析审批人」的原因记在任务数据里，供管理端排查与人工指派。

    只记原因码与说明，不写入任何身份信息或金额。
    """
    data: dict[str, Any] = dict(task.data or {})
    data["_routing"] = {"status": "manual_assign_required", "reason": reason, "message": message}
    task.data = data


def clear_routing_note(task: TaskModel) -> None:
    """审批链解析成功时清除历史的人工指派标记。"""
    if not task.data or "_routing" not in task.data:
        return
    data: dict[str, Any] = dict(task.data)
    data.pop("_routing", None)
    task.data = data
