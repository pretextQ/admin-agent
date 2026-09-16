# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""WebSocket 实时对话。"""

from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["WebSocket"])


@router.websocket("/api/v1/chat/ws")
async def websocket_chat(websocket: WebSocket) -> None:
    """WebSocket 实时对话。"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "message")
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "message":
                content = data.get("content", "")
                await websocket.send_json({
                    "type": "reply",
                    "content": f"收到: {content}",
                    "conversation_id": data.get("conversation_id", "conv_ws"),
                })
    except WebSocketDisconnect:
        pass