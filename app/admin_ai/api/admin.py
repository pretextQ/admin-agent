# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""管理后台接口。"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.api.response import ApiResponse
from app.admin_ai.core.auth.deps import get_admin_user
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import AuditLogModel, ConversationModel, ConversationStatus, TaskModel, TaskStatus, utc_now

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
