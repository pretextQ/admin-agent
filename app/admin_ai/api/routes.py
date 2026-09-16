# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""路由汇总。"""

from __future__ import annotations

from fastapi import APIRouter

from app.admin_ai.api import auth, chat, task, knowledge, admin


def create_router() -> APIRouter:
    """创建并汇总所有路由。"""
    router = APIRouter(prefix="/api/v1")
    router.include_router(auth.router)
    router.include_router(chat.router)
    router.include_router(task.router)
    router.include_router(knowledge.router)
    router.include_router(admin.router)
    return router