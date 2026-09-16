# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""对话服务。"""

from __future__ import annotations

import uuid
from typing import Any, Optional

import structlog

from app.admin_ai.core.agent.dialog import DialogManager
from app.admin_ai.core.agent.orchestrator import AgentContext, Orchestrator

logger = structlog.get_logger(__name__)


class ChatService:
    """对话服务。"""

    def __init__(self, orchestrator: Orchestrator, dialog_manager: DialogManager) -> None:
        self.orchestrator = orchestrator
        self.dialog_manager = dialog_manager

    async def send_message(
        self,
        user_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        attachments: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """发送消息。"""
        if not conversation_id:
            conversation_id = str(uuid.uuid4())

        context = AgentContext(user_id=user_id, conversation_id=conversation_id)
        result = await self.orchestrator.process(message, context, attachments)

        await self.dialog_manager.save_message(conversation_id, "user", message)
        await self.dialog_manager.save_message(conversation_id, "assistant", result.get("content", ""))

        return {
            "conversation_id": conversation_id,
            "message_id": str(uuid.uuid4()),
            "content": result.get("content", ""),
            "content_type": "card" if result.get("card_data") else "text",
            "card_data": result.get("card_data"),
            "suggestions": result.get("suggestions"),
            "requires_action": result.get("requires_action", False),
            "tool_calls": result.get("tool_calls", []),
        }