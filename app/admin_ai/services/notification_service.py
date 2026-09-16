# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""通知服务。"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class NotificationService:
    """通知服务。"""

    async def send_notification(self, user_id: str, title: str, content: str) -> None:
        """发送通知。"""
        logger.info("发送通知", user_id=user_id, title=title)