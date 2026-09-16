# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""对话接口。"""

from __future__ import annotations

from fastapi import APIRouter

from app.admin_ai.api.response import ApiResponse
from app.admin_ai.api.schemas import ChatRequest, ChatResponse, ConfirmRequest, TransferRequest

router = APIRouter(prefix="/chat", tags=["对话"])


@router.post("/send", response_model=ApiResponse[ChatResponse])
async def send_message(payload: ChatRequest) -> ApiResponse[ChatResponse]:
    """发送消息，创建或继续会话。"""
    import uuid
    return ApiResponse(data=ChatResponse(
        conversation_id=payload.conversation_id or str(uuid.uuid4()),
        message_id=str(uuid.uuid4()),
        content="你好，我是行政助手，请问有什么可以帮您？",
    ))


@router.get("/history/{conversation_id}", response_model=ApiResponse[dict])
async def get_conversation_history(conversation_id: str) -> ApiResponse[dict]:
    """获取会话历史。"""
    return ApiResponse(data={"conversation_id": conversation_id, "messages": [], "total": 0})


@router.post("/confirm/{task_id}", response_model=ApiResponse[ChatResponse])
async def confirm_action(task_id: str, payload: ConfirmRequest) -> ApiResponse[ChatResponse]:
    """确认或取消高风险操作。"""
    return ApiResponse(data=ChatResponse(
        conversation_id="conv_demo",
        message_id="msg_demo",
        content="操作已确认" if payload.confirmed else "操作已取消",
    ))


@router.post("/transfer/{conversation_id}", response_model=ApiResponse[ChatResponse])
async def transfer_to_human(
    conversation_id: str, payload: TransferRequest
) -> ApiResponse[ChatResponse]:
    """转人工。"""
    return ApiResponse(data=ChatResponse(
        conversation_id=conversation_id,
        message_id="msg_demo",
        content="已为您转接人工客服，请稍候。",
    ))