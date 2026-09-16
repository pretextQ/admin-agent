# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""任务/待办接口。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.api.response import ApiResponse, BusinessError
from app.admin_ai.api.schemas import ApprovalRequest
from app.admin_ai.core.auth.deps import get_current_user
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import ApprovalAction, ApprovalModel, TaskModel, TaskStatus

router = APIRouter(prefix="/tasks", tags=["任务"])


@router.get("/my", response_model=ApiResponse[dict])
async def get_my_tasks(
    status: Optional[str] = None,
    type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """获取我的任务列表。"""
    query = select(TaskModel).where(TaskModel.user_id == current_user["user_id"])
    if status:
        query = query.where(TaskModel.status == status)
    if type:
        query = query.where(TaskModel.type == type)

    # 统计总数
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(TaskModel.created_at.desc())
    result = await db.execute(query)
    tasks = result.scalars().all()

    # 统计待处理和审批中数量
    pending_count = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
    approving_count = sum(1 for t in tasks if t.status == TaskStatus.APPROVING)

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
        "pending_count": pending_count,
        "approving_count": approving_count,
    })


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
    """获取任务详情。"""
    result = await db.execute(select(TaskModel).where(TaskModel.id == task_id))
    task = result.scalar_one_or_none()
    if not task:
        raise BusinessError(code=40004, message="任务不存在")
    if task.user_id != current_user["user_id"]:
        raise BusinessError(code=40003, message="无权访问该任务")

    # 获取审批链
    approvals_result = await db.execute(
        select(ApprovalModel)
        .where(ApprovalModel.task_id == task_id)
        .order_by(ApprovalModel.step)
    )
    approvals = approvals_result.scalars().all()

    return ApiResponse(data={
        "id": task.id,
        "type": task.type.value if task.type else None,
        "status": task.status.value if task.status else None,
        "title": task.title,
        "data": task.data,
        "risk_level": task.risk_level,
        "external_id": task.external_id,
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
        # 加签：插入新的 pending ApprovalModel
        if not payload.add_sign_user_id:
            raise BusinessError(code=40001, message="加签必须指定 add_sign_user_id")
        new_approval = ApprovalModel(
            task_id=task_id,
            approver_id=payload.add_sign_user_id,
            step=approval.step + 1,
            status="pending",
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
    approval.decided_at = datetime.now(timezone.utc)

    if payload.action == "reject":
        task.status = TaskStatus.FAILED
    elif payload.action == "approve":
        # 检查是否还有其他 pending 的审批记录
        next_pending = await db.execute(
            select(ApprovalModel).where(
                ApprovalModel.task_id == task_id,
                ApprovalModel.status == "pending",
                ApprovalModel.id != approval.id,
            )
        )
        if next_pending.scalar_one_or_none():
            # 还有下一步审批，保持 APPROVING
            pass
        else:
            # 所有审批完成
            task.status = TaskStatus.COMPLETED
            task.completed_at = datetime.now(timezone.utc)

    await db.commit()
    return ApiResponse(data={
        "id": task_id,
        "action": payload.action,
        "status": task.status.value,
    })


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