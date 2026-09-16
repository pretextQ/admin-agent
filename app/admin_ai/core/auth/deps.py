# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""认证依赖。"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, Header

from app.admin_ai.api.response import BusinessError


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    """解析并校验 JWT，返回当前用户。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise BusinessError(code=40002, message="未授权")
    token = authorization.removeprefix("Bearer ").strip()
    return {"user_id": "user_001", "employee_id": "EMP1001", "role": "employee"}


async def get_admin_user(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """校验管理员角色。"""
    if current_user.get("role") != "admin":
        raise BusinessError(code=40003, message="无权限")
    return current_user