# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""依赖注入上下文。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class APIContext:
    """API 请求上下文。"""
    db: Optional[AsyncSession] = None
    user_id: Optional[str] = None
    employee_id: Optional[str] = None
    role: Optional[str] = None


async def get_api_context() -> APIContext:
    """获取 API 上下文。"""
    return APIContext()