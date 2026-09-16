# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""认证依赖。"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, Header

from app.admin_ai.api.response import BusinessError
from app.admin_ai.core.auth.jwt_token import verify_token


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    """解析并校验 JWT，返回当前用户。

    从 Authorization 头提取 Bearer token，验签后返回载荷。
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise BusinessError(code=40002, message="未授权")
    token = authorization[7:].strip()  # len("Bearer ") == 7
    try:
        payload = verify_token(token)
    except ValueError as exc:
        raise BusinessError(code=40002, message=f"令牌无效: {exc}") from exc
    return {
        "user_id": payload.get("sub"),
        "employee_id": payload.get("employee_id"),
        "role": payload.get("role", "employee"),
    }


async def get_admin_user(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """校验管理员角色。"""
    if current_user.get("role") != "admin":
        raise BusinessError(code=40003, message="无权限")
    return current_user