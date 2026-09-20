# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""任务/待办接口。"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.api.response import ApiResponse, BusinessError
from app.admin_ai.api.schemas import ApprovalRequest
from app.admin_ai.core.approval.ownership import OwnershipPlan, build_ownership_plan
from app.admin_ai.core.auth.deps import get_current_user
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import (
    ApprovalAction,
    ApprovalMode,
    ApprovalModel,
    ApprovalStatus,
    AuditLogModel,
    TaskModel,
    TaskStatus,
    utc_now,
)

router = APIRouter(prefix="/tasks", tags=["任务"])


@router.get("/my", response_model=ApiResponse[dict])
async def get_my_tasks(
    status: Optional[str] = None,
    type: Optional[str] = None,
    scope: str = "my",
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """获取任务列表。

    `scope` 决定数据归属范围（SECURITY §4.3）：
    `my` 本人（默认）/ `dept` 本部门及子部门（部门主管）/ `all` 全量（admin/finance/hr，受审计）。
    归属条件下推到 SQL，不做「先查全量再过滤」。
    """
    plan = await build_ownership_plan(
        db,
        user_id=current_user["user_id"],
        role=current_user.get("role", "employee"),
        scope=scope,
    )

    query = select(TaskModel)
    if plan.condition is not None:
        query = query.where(plan.condition)
    if status:
        query = query.where(TaskModel.status == status)
    if type:
        query = query.where(TaskModel.type == type)

    # 统计基于过滤后的全量集合，而非当前页
    total = await db.scalar(select(func.count()).select_from(query.subquery())) or 0
    pending_count = await db.scalar(
        select(func.count()).select_from(
            query.where(TaskModel.status == TaskStatus.PENDING).subquery()
        )
    ) or 0
    approving_count = await db.scalar(
        select(func.count()).select_from(
            query.where(TaskModel.status == TaskStatus.APPROVING).subquery()
        )
    ) or 0

    if plan.audited:
        await _record_scope_access(db, user_id=current_user["user_id"], plan=plan)

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(TaskModel.created_at.desc())
    result = await db.execute(query)
    tasks = result.scalars().all()

    return ApiResponse(data={
        "items": [
            {
                "id": t.id,
                "type": t.type.value if t.type else None,
                "status": t.status.value if t.status else None,
                "title": t.title,
                "risk_level": t.risk_level,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "scope": plan.scope,
        "pending_count": pending_count,
        "approving_count": approving_count,
    })


async def _record_scope_access(db: AsyncSession, *, user_id: str, plan: OwnershipPlan) -> None:
    """记录越范围查询（dept/all）的审计：谁在何时看了哪个范围（不记具体单据内容）。"""
    db.add(
        AuditLogModel(
            user_id=user_id,
            action="task_scope_query",
            resource_type="tasks",
            resource_id=",".join(plan.department_ids) or None,
            decision=f"scope={plan.scope}",
        )
    )
    await db.commit()


@router.get("/pending-approval", response_model=ApiResponse[dict])
async def get_pending_approval_tasks(
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """获取待我审批的任务。"""
    query = (
        select(TaskModel)
        .join(ApprovalModel, ApprovalModel.task_id == TaskModel.id)
        .where(
            ApprovalModel.approver_id == current_user["user_id"],
            ApprovalModel.status == "pending",
        )
    )

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    tasks = result.scalars().all()

    return ApiResponse(data={
        "items": [
            {
                "id": t.id,
                "type": t.type.value if t.type else None,
                "status": t.status.value if t.status else None,
                "title": t.title,
                "risk_level": t.risk_level,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in tasks
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/{task_id}", response_model=ApiResponse[dict])
async def get_task_detail(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """获取任务详情。任务属主与当前审批人可见。"""
    result = await db.execute(select(TaskModel).where(TaskModel.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise BusinessError(code=40004, message="任务不存在")

    # 获取审批链
    approvals_result = await db.execute(
        select(ApprovalModel)
        .where(ApprovalModel.task_id == task_id)
        .order_by(ApprovalModel.step)
    )
    approvals = approvals_result.scalars().all()

    is_owner = task.user_id == current_user["user_id"]
    can_approve = (
        task.status == TaskStatus.APPROVING
        and any(
            a.approver_id == current_user["user_id"] and a.status == "pending"
            for a in approvals
        )
    )
    if not is_owner and not can_approve:
        raise BusinessError(code=40003, message="无权访问该任务")

    return ApiResponse(data={
        "id": task.id,
        "type": task.type.value if task.type else None,
        "status": task.status.value if task.status else None,
        "title": task.title,
        "data": task.data,
        "risk_level": task.risk_level,
        "external_id": task.external_id,
        "can_approve": can_approve,
        "is_owner": is_owner,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "completed_at": task.completed_at.isoformat() if task.completed_at else None,
        "approvals": [
            {
                "id": a.id,
                "step": a.step,
                "approver_id": a.approver_id,
                "action": a.action.value if a.action else None,
                "status": a.status,
                "comment": a.comment,
                "add_sign_user_id": a.add_sign_user_id,
                "created_at": a.created_at.isoformat() if a.created_at else None,
                "decided_at": a.decided_at.isoformat() if a.decided_at else None,
            }
            for a in approvals
        ],
    })


@router.post("/{task_id}/approve", response_model=ApiResponse[dict])
async def approve_task(
    task_id: str,
    payload: ApprovalRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """审批任务，仅当前审批人可操作。"""
    # 校验 action
    valid_actions = {"approve", "reject", "add_sign"}
    if payload.action not in valid_actions:
        raise BusinessError(code=40001, message=f"非法操作: {payload.action}，仅支持 {valid_actions}")

    result = await db.execute(select(TaskModel).where(TaskModel.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise BusinessError(code=40004, message="任务不存在")

    # 校验任务状态
    if task.status != TaskStatus.APPROVING:
        raise BusinessError(code=40001, message=f"任务状态为 {task.status.value}，无法审批")

    # 查找当前审批人待审批记录
    approval_result = await db.execute(
        select(ApprovalModel).where(
            ApprovalModel.task_id == task_id,
            ApprovalModel.approver_id == current_user["user_id"],
            ApprovalModel.status == "pending",
        )
    )
    approval = approval_result.scalar_one_or_none()
    if not approval:
        raise BusinessError(code=40003, message="您不是当前审批人")

    if payload.action == "add_sign":
        # 加签：关闭原审批记录，插入被加签人的 pending 记录
        if not payload.add_sign_user_id:
            raise BusinessError(code=40001, message="加签必须指定 add_sign_user_id")
        if payload.add_sign_user_id == current_user["user_id"]:
            raise BusinessError(code=40001, message="不能加签给自己")

        approval.action = ApprovalAction.ADD_SIGN
        approval.status = ApprovalStatus.DONE.value
        approval.add_sign_user_id = payload.add_sign_user_id
        approval.decided_at = utc_now()

        new_approval = ApprovalModel(
            task_id=task_id,
            approver_id=payload.add_sign_user_id,
            step=approval.step,
            status=ApprovalStatus.PENDING.value,
            mode=_step_mode(approval),
            approver_source="add_sign",
        )
        db.add(new_approval)
        await db.commit()
        return ApiResponse(data={
            "id": task_id,
            "action": "add_sign",
            "status": task.status.value,
            "new_approver_id": payload.add_sign_user_id,
        })

    # 更新审批状态
    approval.action = ApprovalAction(payload.action)
    approval.status = payload.action
    approval.comment = payload.comment
    approval.decided_at = utc_now()

    # 同任务其他待审记录：用于「任一人通过则同步骤其他待办自动关闭」与「是否已全部审完」判断
    other_pending = (
        await db.execute(
            select(ApprovalModel).where(
                ApprovalModel.task_id == task_id,
                ApprovalModel.status == "pending",
                ApprovalModel.id != approval.id,
            )
        )
    ).scalars().all()

    if payload.action == "reject":
        task.status = TaskStatus.FAILED
        _close_pending(other_pending)
        await db.commit()
        return ApiResponse(data={
            "id": task_id,
            "action": payload.action,
            "status": task.status.value,
        })

    # 通过：按该步骤的模式决定后续
    if _step_mode(approval) == ApprovalMode.ANY_ONE.value:
        # 任一人通过即该步完成，同步骤其他待办自动关闭（设计 §4.3）
        _close_pending([a for a in other_pending if a.step == approval.step])

    # 汇总仍待审的记录（任何步骤）；全部审完则任务完成
    remaining = [a for a in other_pending if a.status == "pending"]
    if remaining:
        pass  # 还有待审（其他步骤或会签未齐），保持 APPROVING
    else:
        task.status = TaskStatus.COMPLETED
        task.completed_at = utc_now()

    await db.commit()
    return ApiResponse(data={
        "id": task_id,
        "action": payload.action,
        "status": task.status.value,
    })


def _step_mode(approval: ApprovalModel) -> str:
    """该审批步骤的多人判定方式；历史数据无该字段时按任一人通过处理。"""
    return getattr(approval, "mode", None) or ApprovalMode.ANY_ONE.value


def _close_pending(approvals: list[ApprovalModel]) -> None:
    """关闭待审记录（标记 skipped，保留记录以便审计追溯）。

    已出结论的记录（approve/reject/done）一律不改写，历史审批意见必须可追溯。
    """
    for item in approvals:
        if item.status != ApprovalStatus.PENDING.value:
            continue
        item.status = ApprovalStatus.SKIPPED.value
        item.decided_at = utc_now()


@router.post("/{task_id}/cancel", response_model=ApiResponse[dict])
async def cancel_task(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """取消任务。"""
    result = await db.execute(select(TaskModel).where(TaskModel.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise BusinessError(code=40004, message="任务不存在")
    if task.user_id != current_user["user_id"]:
        raise BusinessError(code=40003, message="无权取消该任务")

    cancellable = {TaskStatus.PENDING, TaskStatus.PROCESSING, TaskStatus.APPROVING}
    if task.status not in cancellable:
        raise BusinessError(
            code=40001, message=f"任务当前状态为 {task.status.value}，不可取消"
        )

    task.status = TaskStatus.CANCELLED
    await db.commit()

    return ApiResponse(data={"id": task_id, "status": "cancelled"})


@router.get("/{task_id}/timeline", response_model=ApiResponse[dict])
async def get_task_timeline(
    task_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """获取任务状态时间线。"""
    result = await db.execute(select(TaskModel).where(TaskModel.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise BusinessError(code=40004, message="任务不存在")
    if task.user_id != current_user["user_id"]:
        raise BusinessError(code=40003, message="无权访问该任务")

    approvals_result = await db.execute(
        select(ApprovalModel)
        .where(ApprovalModel.task_id == task_id)
        .order_by(ApprovalModel.created_at)
    )
    approvals = approvals_result.scalars().all()

    timeline = [
        {
            "event": "created",
            "timestamp": task.created_at.isoformat() if task.created_at else None,
            "description": "任务创建",
        }
    ]

    for a in approvals:
        timeline.append({
            "event": f"approval_{a.status}",
            "timestamp": a.decided_at.isoformat() if a.decided_at else a.created_at.isoformat(),
            "description": f"审批人{a.approver_id}{a.status}",
            "comment": a.comment,
        })

    if task.completed_at:
        timeline.append({
            "event": "completed",
            "timestamp": task.completed_at.isoformat(),
            "description": "任务完成",
        })

    return ApiResponse(data={"task_id": task_id, "timeline": timeline})