# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""对话接口。"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request

from app.admin_ai.api.response import ApiResponse
from app.admin_ai.api.schemas import ChatRequest, ChatResponse, ConfirmRequest, TransferRequest
from app.admin_ai.core.agent.orchestrator import AgentContext
from app.admin_ai.core.auth.deps import get_current_user

router = APIRouter(prefix="/chat", tags=["对话"])


@router.post("/send", response_model=ApiResponse[ChatResponse])
async def send_message(
    payload: ChatRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse[ChatResponse]:
    """发送消息，创建或继续会话。"""
    orchestrator = request.app.state.orchestrator
    conversation_id = payload.conversation_id or str(uuid.uuid4())
    context = AgentContext(
        user_id=current_user["user_id"],
        conversation_id=conversation_id,
    )
    result = await orchestrator.process(payload.message, context, payload.attachments)
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


@router.post("/confirm/{task_id}", response_model=ApiResponse[ChatResponse])
async def confirm_action(
    task_id: str,
    payload: ConfirmRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
) -> ApiResponse[ChatResponse]:
    """确认或取消高风险操作。"""
    orchestrator = request.app.state.orchestrator
    context = AgentContext(
        user_id=current_user["user_id"],
        conversation_id=task_id,
        confirmed=payload.confirmed,
    )
    result = await orchestrator.process(
        "确认操作" if payload.confirmed else "取消操作",
        context,
    )
    return ApiResponse(data=ChatResponse(
        conversation_id=task_id,
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