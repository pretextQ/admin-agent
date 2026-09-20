# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""通知服务。"""

from __future__ import annotations

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.db.models import UserModel

logger = structlog.get_logger(__name__)


class NotificationService:
    """通知服务。"""

    async def send_notification(self, user_id: str, title: str, content: str) -> None:
        """发送通知。"""
        logger.info("发送通知", user_id=user_id, title=title)


async def notify_admins(db: AsyncSession, *, title: str, content: str) -> int:
    """通知全部在职管理员（待人工指派审批人、组织同步失败等运维事件）。

    返回通知人数；查询或发送失败只告警不抛异常——通知属旁路，不得阻断业务流程。
    """
    try:
        admin_ids = (
            await db.execute(
                select(UserModel.id).where(
                    UserModel.role == "admin",
                    UserModel.is_active == True,  # noqa: E712
                    UserModel.is_deleted == False,  # noqa: E712
                )
            )
        ).scalars().all()
        service = NotificationService()
        for admin_id in admin_ids:
            await service.send_notification(user_id=admin_id, title=title, content=content)
        return len(admin_ids)
    except Exception as exc:  # noqa: BLE001 - 通知失败不得阻断业务
        logger.warning("管理员通知失败", title=title, error=str(exc))
        return 0