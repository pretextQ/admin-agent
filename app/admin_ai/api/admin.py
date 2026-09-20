# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""管理后台接口。"""

from __future__ import annotations

from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.api.response import ApiResponse, BusinessError
from app.admin_ai.api.schemas import (
    ApprovalDelegationRequest,
    ApprovalRuleRequest,
    OrgSyncRequest,
)
from app.admin_ai.config import get_config
from app.admin_ai.core.approval.conditions import ConditionError, validate_conditions
from app.admin_ai.core.approval.sync import sync_org
from app.admin_ai.core.auth.deps import get_admin_user
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import (
    ApprovalDelegationModel,
    ApprovalMode,
    ApprovalRuleModel,
    ApproverType,
    AuditLogModel,
    ConversationModel,
    ConversationStatus,
    DepartmentModel,
    TaskModel,
    TaskStatus,
    UserModel,
    generate_uuid,
    utc_now,
)

# 全部使用无时区 UTC 时间（与列默认值 utc_now 一致）
router = APIRouter(prefix="/admin", tags=["管理后台"], dependencies=[Depends(get_admin_user)])


@router.get("/dashboard", response_model=ApiResponse[dict])
async def get_dashboard(
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """仪表盘数据。"""
    day_start = utc_now().replace(hour=0, minute=0, second=0, microsecond=0)

    today_conversations = await db.scalar(
        select(func.count()).select_from(ConversationModel)
        .where(ConversationModel.created_at >= day_start)
    ) or 0
    today_tasks = await db.scalar(
        select(func.count()).select_from(TaskModel).where(TaskModel.created_at >= day_start)
    ) or 0
    total_conversations = await db.scalar(
        select(func.count()).select_from(ConversationModel)
    ) or 0
    transferred = await db.scalar(
        select(func.count()).select_from(ConversationModel)
        .where(ConversationModel.status == ConversationStatus.TRANSFERRED)
    ) or 0

    top_intent_rows = (
        await db.execute(
            select(ConversationModel.intent, func.count())
            .where(ConversationModel.intent.isnot(None))
            .group_by(ConversationModel.intent)
            .order_by(func.count().desc())
            .limit(5)
        )
    ).all()

    return ApiResponse(data={
        "today_conversations": today_conversations,
        "today_tasks": today_tasks,
        "transfer_rate": round(transferred / total_conversations, 4) if total_conversations else 0.0,
        "top_intents": [{"intent": intent, "count": count} for intent, count in top_intent_rows],
    })


@router.get("/audit-logs", response_model=ApiResponse[dict])
async def get_audit_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """审计日志查询。"""
    page = max(page, 1)
    page_size = min(max(page_size, 1), 100)

    query = select(AuditLogModel)
    if user_id:
        query = query.where(AuditLogModel.user_id == user_id)
    if action:
        query = query.where(AuditLogModel.action.ilike(f"%{action}%"))

    total = await db.scalar(
        select(func.count()).select_from(query.subquery())
    ) or 0
    logs = (
        await db.execute(
            query.order_by(AuditLogModel.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    ).scalars().all()

    return ApiResponse(data={
        "logs": [
            {
                "id": log.id,
                "user_id": log.user_id,
                "conversation_id": log.conversation_id,
                "action": log.action,
                "resource_type": log.resource_type,
                "resource_id": log.resource_id,
                "input_data": log.input_data,
                "decision": log.decision,
                "ip_address": log.ip_address,
                "created_at": log.created_at.isoformat() if log.created_at else None,
            }
            for log in logs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.get("/tools", response_model=ApiResponse[dict])
async def list_tools(request: Request) -> ApiResponse[dict]:
    """工具列表。"""
    registry = getattr(request.app.state, "tool_registry", None)
    tools = registry.list_tools() if registry else []
    return ApiResponse(data={"tools": tools})


@router.put("/tools/{tool_id}/config", response_model=ApiResponse[dict])
async def update_tool_config(
    tool_id: str,
    config: dict,
) -> ApiResponse[dict]:
    """更新工具配置。TODO: 工具配置尚无持久化存储，当前仅回显。"""
    return ApiResponse(data={"tool_id": tool_id, "config": config, "status": "accepted"})


@router.get("/metrics", response_model=ApiResponse[dict])
async def get_metrics(
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """系统指标。TODO: llm_calls/token_cost/avg_response_time 需要 LLM 调用埋点支持。"""
    total_tasks = await db.scalar(select(func.count()).select_from(TaskModel)) or 0
    completed_tasks = await db.scalar(
        select(func.count()).select_from(TaskModel).where(TaskModel.status == TaskStatus.COMPLETED)
    ) or 0
    total_conversations = await db.scalar(
        select(func.count()).select_from(ConversationModel)
    ) or 0
    transferred = await db.scalar(
        select(func.count()).select_from(ConversationModel)
        .where(ConversationModel.status == ConversationStatus.TRANSFERRED)
    ) or 0

    return ApiResponse(data={
        "llm_calls": 0,
        "token_cost": 0.0,
        "avg_response_time": 0.0,
        "completion_rate": round(completed_tasks / total_tasks, 4) if total_tasks else 0.0,
        "transfer_rate": round(transferred / total_conversations, 4) if total_conversations else 0.0,
    })


# ---------------------------------------------------------------- 组织架构与审批路由（评审 B-2）
# 首期维护入口为「脚本 + API」（决策 D-5）：前端管理页与评审 I-3 的管理后台归属一并排期。


@router.get("/departments", response_model=ApiResponse[dict])
async def list_departments(
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """部门树（排障与人工核对组织数据用）。"""
    departments = (
        await db.execute(select(DepartmentModel).order_by(DepartmentModel.path))
    ).scalars().all()
    manager_ids = {d.manager_id for d in departments if d.manager_id}
    managers = {}
    if manager_ids:
        rows = (
            await db.execute(
                select(UserModel.id, UserModel.employee_id, UserModel.name).where(
                    UserModel.id.in_(manager_ids)
                )
            )
        ).all()
        managers = {row[0]: {"employee_id": row[1], "name": row[2]} for row in rows}
    return ApiResponse(data={
        "items": [
            {
                "id": d.id,
                "name": d.name,
                "parent_id": d.parent_id,
                "path": d.path,
                "level": d.level,
                "external_id": d.external_id,
                "is_active": d.is_active,
                "manager": managers.get(d.manager_id),
            }
            for d in departments
        ],
        "total": len(departments),
    })


@router.get("/approval-rules", response_model=ApiResponse[dict])
async def list_approval_rules(
    business_type: Optional[str] = None,
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """审批路由规则列表。"""
    query = select(ApprovalRuleModel).order_by(
        ApprovalRuleModel.business_type, ApprovalRuleModel.step_order
    )
    if business_type:
        query = query.where(ApprovalRuleModel.business_type == business_type)
    rules = (await db.execute(query)).scalars().all()
    return ApiResponse(data={"items": [_rule_to_dict(r) for r in rules], "total": len(rules)})


@router.post("/approval-rules", response_model=ApiResponse[dict])
async def upsert_approval_rule(
    payload: ApprovalRuleRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """新增或更新审批规则（带 id 为更新）。

    审批规则决定「按金额与部门路由到谁」，配置错误会导致审批链解析失败并转人工，
    因此这里对取值做显式校验。
    """
    try:
        approver_type = ApproverType(payload.approver_type)
    except ValueError as exc:
        raise BusinessError(code=40001, message=f"非法 approver_type: {payload.approver_type}") from exc
    try:
        approval_mode = ApprovalMode(payload.approval_mode)
    except ValueError as exc:
        raise BusinessError(code=40001, message=f"非法 approval_mode: {payload.approval_mode}") from exc
    if approver_type == ApproverType.ROLE and not payload.approver_param:
        raise BusinessError(code=40001, message="approver_type=role 必须提供 approver_param")
    if approver_type == ApproverType.USER and not payload.approver_param:
        raise BusinessError(code=40001, message="approver_type=user 必须提供 approver_param")
    if (
        payload.amount_min is not None
        and payload.amount_max is not None
        and payload.amount_min >= payload.amount_max
    ):
        raise BusinessError(code=40001, message="amount_min 必须小于 amount_max")
    if payload.step_order < 1:
        raise BusinessError(code=40001, message="step_order 从 1 开始")
    try:
        validate_conditions(payload.condition)
    except ConditionError as exc:
        raise BusinessError(code=40001, message=f"审批条件非法：{exc}") from exc

    rule = None
    if payload.id:
        rule = (
            await db.execute(select(ApprovalRuleModel).where(ApprovalRuleModel.id == payload.id))
        ).scalar_one_or_none()
        if rule is None:
            raise BusinessError(code=40004, message="审批规则不存在")
    if rule is None:
        rule = ApprovalRuleModel(id=generate_uuid(), business_type=payload.business_type)
        db.add(rule)

    rule.business_type = payload.business_type
    rule.amount_min = _to_decimal(payload.amount_min)
    rule.amount_max = _to_decimal(payload.amount_max)
    rule.step_order = payload.step_order
    rule.approver_type = approver_type
    rule.approver_param = payload.approver_param
    rule.approval_mode = approval_mode
    rule.required = payload.required
    rule.enabled = payload.enabled
    rule.condition = payload.condition or None
    rule.remark = payload.remark
    rule.updated_at = utc_now()
    await db.commit()
    return ApiResponse(data=_rule_to_dict(rule))


@router.delete("/approval-rules/{rule_id}", response_model=ApiResponse[dict])
async def delete_approval_rule(
    rule_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """删除审批规则（在途审批不受影响：步骤模式在生成审批链时已快照）。"""
    rule = (
        await db.execute(select(ApprovalRuleModel).where(ApprovalRuleModel.id == rule_id))
    ).scalar_one_or_none()
    if rule is None:
        raise BusinessError(code=40004, message="审批规则不存在")
    await db.delete(rule)
    await db.commit()
    return ApiResponse(data={"id": rule_id, "deleted": True})


@router.get("/approval-delegations", response_model=ApiResponse[dict])
async def list_approval_delegations(
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """代理审批委派列表。"""
    delegations = (
        await db.execute(
            select(ApprovalDelegationModel).order_by(ApprovalDelegationModel.start_at.desc())
        )
    ).scalars().all()
    return ApiResponse(data={
        "items": [
            {
                "id": d.id,
                "delegator_id": d.delegator_id,
                "delegate_id": d.delegate_id,
                "start_at": d.start_at.isoformat() if d.start_at else None,
                "end_at": d.end_at.isoformat() if d.end_at else None,
                "business_types": d.business_types,
                "is_active": d.is_active,
            }
            for d in delegations
        ],
        "total": len(delegations),
    })


@router.post("/approval-delegations", response_model=ApiResponse[dict])
async def create_approval_delegation(
    payload: ApprovalDelegationRequest,
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """新增代理审批委派（主管休假时把审批权临时交给他人）。"""
    if payload.delegator_id == payload.delegate_id:
        raise BusinessError(code=40001, message="不能把审批权委派给自己")
    if payload.end_at <= payload.start_at:
        raise BusinessError(code=40001, message="end_at 必须晚于 start_at")

    delegation = ApprovalDelegationModel(
        id=generate_uuid(),
        delegator_id=payload.delegator_id,
        delegate_id=payload.delegate_id,
        start_at=payload.start_at,
        end_at=payload.end_at,
        business_types=payload.business_types,
    )
    db.add(delegation)
    await db.commit()
    return ApiResponse(data={
        "id": delegation.id,
        "delegator_id": delegation.delegator_id,
        "delegate_id": delegation.delegate_id,
    })


@router.post("/org/sync", response_model=ApiResponse[dict])
async def trigger_org_sync(
    payload: Optional[OrgSyncRequest] = None,
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """手动触发组织架构同步（日常由定时任务调用 `scripts/sync_org.py`）。

    失败时不会修改组织数据，返回 ok=false 与原因，供运维排查上游接口。
    """
    config = get_config()
    payload = payload or OrgSyncRequest()
    summary = await sync_org(
        db,
        provider=payload.provider or config.ORG_SYNC_PROVIDER,
        csv_dir=payload.csv_dir or config.ORG_SYNC_CSV_DIR,
        base_url=config.HR_ORG_BASE_URL,
        token=config.HR_ORG_TOKEN,
        timeout=config.ORG_SYNC_TIMEOUT_SECONDS,
    )
    return ApiResponse(data=summary.as_dict())


def _to_decimal(value: Optional[float]) -> Optional[Decimal]:
    """金额转 Decimal（金额区间为「含 min、不含 max」）。"""
    return None if value is None else Decimal(str(value))


def _rule_to_dict(rule: ApprovalRuleModel) -> dict:
    """审批规则序列化。"""
    return {
        "id": rule.id,
        "business_type": rule.business_type,
        "amount_min": float(rule.amount_min) if rule.amount_min is not None else None,
        "amount_max": float(rule.amount_max) if rule.amount_max is not None else None,
        "step_order": rule.step_order,
        "approver_type": (
            rule.approver_type.value if hasattr(rule.approver_type, "value") else rule.approver_type
        ),
        "approver_param": rule.approver_param,
        "approval_mode": (
            rule.approval_mode.value
            if hasattr(rule.approval_mode, "value")
            else rule.approval_mode
        ),
        "condition": rule.condition or None,
        "required": rule.required,
        "enabled": rule.enabled,
        "remark": rule.remark,
    }
