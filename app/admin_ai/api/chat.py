# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""对话接口。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.api.response import ApiResponse, BusinessError
from app.admin_ai.api.schemas import ChatRequest, ChatResponse, ConfirmRequest, TransferRequest
from app.admin_ai.core.agent.orchestrator import AgentContext
from app.admin_ai.core.agent.state_store import (
    ConversationState,
    ConversationStateStore,
    get_default_state_store,
)
from app.admin_ai.core.auth.deps import get_current_user
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import (
    ConversationModel,
    ConversationStatus,
    MessageModel,
    MessageRole,
    TaskModel,
    TaskType,
)

router = APIRouter(prefix="/chat", tags=["对话"])

# 业务类型 -> 任务标题用词（与 TaskType 取值对应）
TASK_LABELS = {
    "leave": "请假",
    "expense": "报销",
    "travel": "差旅",
    "meeting_room": "会议室预定",
    "vehicle": "车辆预定",
    "material": "物资领用",
    "asset": "资产领用/归还",
    "seal": "用印",
    "certificate": "证明开具",
    "onboarding": "入离职办理",
}
# 与编排器 HIGH_RISK_TYPES 对应的高风险业务
HIGH_RISK_BUSINESS = {"expense", "seal"}


def _build_task_title(business_type: str, slots: dict[str, Any]) -> str:
    """根据业务类型与槽位生成任务标题。"""
    label = TASK_LABELS.get(business_type, business_type)
    hint = slots.get("leave_type") or slots.get("expense_type") or slots.get("item_name") \
        or slots.get("certificate_type") or slots.get("asset_name")
    return f"{label}（{hint}）" if hint else label


def _get_state_store(request: Request) -> ConversationStateStore:
    """获取会话状态存储；未在 lifespan 中初始化时回退到默认内存实现。"""
    store = getattr(request.app.state, "state_store", None)
    if store is None:
        store = get_default_state_store()
    return store


def _build_conversation_state(context: AgentContext, result: dict, user_id: str) -> ConversationState:
    """把本轮上下文与结果转为可持久化状态。"""
    card = result.get("card_data") or {}
    return ConversationState(
        intent=context.intent,
        business_type=context.business_type,
        slots=context.slots,
        awaiting_slots=context.awaiting_slots,
        pending_confirmation=bool(
            result.get("requires_action") and card.get("type") == "confirmation"
        ),
        user_id=user_id,
    )


async def _save_chat_turn(
    db: AsyncSession,
    conversation_id: str,
    user_id: str,
    context: AgentContext,
    user_message: str,
    result: dict,
) -> None:
    """会话与一轮对话消息落库。

    会话行按 conversation_id 幂等创建；助手消息把卡片/工具调用等
    放入 meta，供 `/chat/history` 还原前端消息结构。
    """
    conversation = (
        await db.execute(select(ConversationModel).where(ConversationModel.id == conversation_id))
    ).scalar_one_or_none()
    if conversation is None:
        conversation = ConversationModel(id=conversation_id, user_id=user_id)
        db.add(conversation)
    conversation.intent = context.intent
    conversation.business_type = context.business_type
    conversation.context = {"awaiting_slots": context.awaiting_slots}
    if result.get("transfer_to_human"):
        conversation.status = ConversationStatus.TRANSFERRED

    db.add(MessageModel(
        conversation_id=conversation_id,
        role=MessageRole.USER,
        content=user_message,
    ))

    meta: dict[str, Any] = {}
    if result.get("card_data"):
        meta["card_data"] = result["card_data"]
    if result.get("requires_action"):
        meta["requires_action"] = True
    if result.get("tool_calls"):
        meta["tool_calls"] = result["tool_calls"]
    db.add(MessageModel(
        conversation_id=conversation_id,
        role=MessageRole.ASSISTANT,
        content=result.get("content", ""),
        meta=meta or None,
    ))

    # 工具执行成功时创建任务记录，供任务列表/详情/时间线展示
    business_type = result.get("task_type")
    if business_type:
        try:
            task_type = TaskType(business_type)
        except ValueError:
            task_type = None
        if task_type:
            slots = result.get("slots") or {}
            db.add(TaskModel(
                user_id=user_id,
                conversation_id=conversation_id,
                type=task_type,
                title=_build_task_title(business_type, slots),
                data=slots,
                risk_level="high" if business_type in HIGH_RISK_BUSINESS else "low",
                requires_confirmation=business_type in HIGH_RISK_BUSINESS,
            ))


@router.post("/send", response_model=ApiResponse[ChatResponse])
async def send_message(
    payload: ChatRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ChatResponse]:
    """发送消息，创建或继续会话。"""
    orchestrator = request.app.state.orchestrator
    store = _get_state_store(request)
    conversation_id = payload.conversation_id or str(uuid.uuid4())

    # 恢复该会话已收集的意图/业务类型/槽位，实现多轮补全
    state = await store.get(conversation_id) or ConversationState()
    if state.user_id and state.user_id != current_user["user_id"]:
        raise BusinessError(code=40003, message="无权访问该会话")
    context = AgentContext(
        user_id=current_user["user_id"],
        conversation_id=conversation_id,
        intent=state.intent,
        business_type=state.business_type,
        slots=dict(state.slots),
        awaiting_slots=state.awaiting_slots,
    )
    result = await orchestrator.process(payload.message, context, payload.attachments)
    await store.save(conversation_id, _build_conversation_state(context, result, current_user["user_id"]))
    await _save_chat_turn(db, conversation_id, current_user["user_id"], context, payload.message, result)

    return ApiResponse(data=ChatResponse(
        conversation_id=conversation_id,
        message_id=str(uuid.uuid4()),
        content=result.get("content", ""),
        card_data=result.get("card_data"),
        requires_action=result.get("requires_action", False),
        tool_calls=result.get("tool_calls"),
    ))


@router.get("/history/{conversation_id}", response_model=ApiResponse[dict])
async def get_conversation_history(
    conversation_id: str,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """获取会话历史（仅会话属主可见）。"""
    conversation = (
        await db.execute(select(ConversationModel).where(ConversationModel.id == conversation_id))
    ).scalar_one_or_none()
    if conversation is None:
        raise BusinessError(code=40004, message="会话不存在")
    if conversation.user_id != current_user["user_id"]:
        raise BusinessError(code=40003, message="无权访问该会话")

    messages = (
        await db.execute(
            select(MessageModel)
            .where(MessageModel.conversation_id == conversation_id)
            .order_by(MessageModel.created_at)
        )
    ).scalars().all()

    items = []
    for m in messages:
        meta = m.meta or {}
        items.append({
            "id": m.id,
            "role": m.role.value if isinstance(m.role, MessageRole) else str(m.role),
            "content": m.content,
            "card_data": meta.get("card_data"),
            "requires_action": bool(meta.get("requires_action")),
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })
    return ApiResponse(data={
        "conversation_id": conversation_id,
        "messages": items,
        "total": len(items),
    })


@router.post("/confirm/{conversation_id}", response_model=ApiResponse[ChatResponse])
async def confirm_action(
    conversation_id: str,
    payload: ConfirmRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[ChatResponse]:
    """确认或取消高风险操作。

    从会话状态中恢复待确认操作的业务类型与槽位，确认后携带 `confirmed=True`
    恢复执行；取消则清除待确认状态且不调用工具。仅会话属主可操作。
    """
    orchestrator = request.app.state.orchestrator
    store = _get_state_store(request)
    state = await store.get(conversation_id)

    if state is None or not state.pending_confirmation:
        return ApiResponse(data=ChatResponse(
            conversation_id=conversation_id,
            message_id=str(uuid.uuid4()),
            content="当前没有待确认的操作。",
        ))

    if state.user_id != current_user["user_id"]:
        raise BusinessError(code=40003, message="无权操作该会话")

    user_message = "确认操作" if payload.confirmed else "取消操作"
    if not payload.confirmed:
        await store.clear(conversation_id)
        content = "已取消操作。"
        await _save_chat_turn(
            db, conversation_id, current_user["user_id"],
            AgentContext(user_id=current_user["user_id"], conversation_id=conversation_id),
            user_message, {"content": content},
        )
        return ApiResponse(data=ChatResponse(
            conversation_id=conversation_id,
            message_id=str(uuid.uuid4()),
            content=content,
        ))

    context = AgentContext(
        user_id=current_user["user_id"],
        conversation_id=conversation_id,
        intent=state.intent,
        business_type=state.business_type,
        slots=dict(state.slots),
        confirmed=True,
    )
    result = await orchestrator.process("确认操作", context)
    await store.clear(conversation_id)
    await _save_chat_turn(
        db, conversation_id, current_user["user_id"], context, user_message, result
    )
    return ApiResponse(data=ChatResponse(
        conversation_id=conversation_id,
        message_id=str(uuid.uuid4()),
        content=result.get("content", ""),
        card_data=result.get("card_data"),
        requires_action=result.get("requires_action", False),
    ))


@router.post("/transfer/{conversation_id}", response_model=ApiResponse[ChatResponse])
async def transfer_to_human(
    conversation_id: str,
    payload: TransferRequest,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse[ChatResponse]:
    """转人工。TODO: 对接人工客服队列，当前仅返回固定话术。"""
    return ApiResponse(data=ChatResponse(
        conversation_id=conversation_id,
        message_id=str(uuid.uuid4()),
        content="已为您转接人工客服，请稍候。",
    ))
