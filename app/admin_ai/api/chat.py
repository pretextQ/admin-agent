# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""对话接口。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from app.admin_ai.api.response import ApiResponse
from app.admin_ai.api.schemas import ChatRequest, ChatResponse, ConfirmRequest, TransferRequest
from app.admin_ai.core.agent.orchestrator import AgentContext
from app.admin_ai.core.agent.state_store import (
    ConversationState,
    ConversationStateStore,
    get_default_state_store,
)
from app.admin_ai.core.auth.deps import get_current_user

router = APIRouter(prefix="/chat", tags=["对话"])


def _get_state_store(request: Request) -> ConversationStateStore:
    """获取会话状态存储；未在 lifespan 中初始化时回退到默认内存实现。"""
    store = getattr(request.app.state, "state_store", None)
    if store is None:
        store = get_default_state_store()
    return store


async def _persist_state(
    store: ConversationStateStore,
    conversation_id: str,
    context: AgentContext,
    result: dict,
) -> None:
    """把本轮上下文写回会话状态。"""
    card = result.get("card_data") or {}
    state = ConversationState(
        intent=context.intent,
        business_type=context.business_type,
        slots=context.slots,
        awaiting_slots=context.awaiting_slots,
        pending_confirmation=bool(
            result.get("requires_action") and card.get("type") == "confirmation"
        ),
    )
    await store.save(conversation_id, state)


@router.post("/send", response_model=ApiResponse[ChatResponse])
async def send_message(
    payload: ChatRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse[ChatResponse]:
    """发送消息，创建或继续会话。"""
    orchestrator = request.app.state.orchestrator
    store = _get_state_store(request)
    conversation_id = payload.conversation_id or str(uuid.uuid4())

    # 恢复该会话已收集的意图/业务类型/槽位，实现多轮补全
    state = await store.get(conversation_id) or ConversationState()
    context = AgentContext(
        user_id=current_user["user_id"],
        conversation_id=conversation_id,
        intent=state.intent,
        business_type=state.business_type,
        slots=dict(state.slots),
        awaiting_slots=state.awaiting_slots,
    )
    result = await orchestrator.process(payload.message, context, payload.attachments)
    await _persist_state(store, conversation_id, context, result)

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
) -> ApiResponse[dict]:
    """获取会话历史。"""
    return ApiResponse(data={"conversation_id": conversation_id, "messages": [], "total": 0})


@router.post("/confirm/{conversation_id}", response_model=ApiResponse[ChatResponse])
async def confirm_action(
    conversation_id: str,
    payload: ConfirmRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse[ChatResponse]:
    """确认或取消高风险操作。

    从会话状态中恢复待确认操作的业务类型与槽位，确认后携带 `confirmed=True`
    恢复执行；取消则清除待确认状态且不调用工具。
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

    if not payload.confirmed:
        await store.clear(conversation_id)
        return ApiResponse(data=ChatResponse(
            conversation_id=conversation_id,
            message_id=str(uuid.uuid4()),
            content="已取消操作。",
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
    """转人工。"""
    return ApiResponse(data=ChatResponse(
        conversation_id=conversation_id,
        message_id=str(uuid.uuid4()),
        content="已为您转接人工客服，请稍候。",
    ))