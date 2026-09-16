# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""认证接口。"""

from __future__ import annotations

from datetime import timedelta

from fastapi import APIRouter, Depends

from app.admin_ai.api.response import ApiResponse, BusinessError
from app.admin_ai.api.schemas import LoginRequest, TokenResponse
from app.admin_ai.config import get_config
from app.admin_ai.core.auth.deps import get_current_user
from app.admin_ai.core.auth.jwt_token import create_access_token

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(payload: EmployeeLoginRequest) -> ApiResponse[TokenResponse]:
    """账号密码登录，签发 JWT。

    注意：当前为简化实现，仅校验 employee_id 非空。
    生产环境应对接 SSO 或数据库校验密码。
    """
    if not payload.employee_id:
        raise BusinessError(code=40001, message="工号不能为空")

    config = get_config()
    token = create_access_token(
        data={
            "sub": payload.employee_id,
            "employee_id": payload.employee_id,
            "role": "employee",
        },
        expires_delta=timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return ApiResponse(data=TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=config.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    ))


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
async def refresh_token(
    current_user: dict = Depends(get_current_user),
) -> ApiResponse[TokenResponse]:
    """刷新访问令牌。"""
    config = get_config()
    token = create_access_token(
        data={
            "sub": current_user["user_id"],
            "employee_id": current_user.get("employee_id"),
            "role": current_user.get("role", "employee"),
        },
        expires_delta=timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES),
    )
    return ApiResponse(data=TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=config.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    ))


@router.get("/me", response_model=ApiResponse[dict])
async def get_me(
    current_user: dict = Depends(get_current_user),
) -> ApiResponse[dict]:
    """获取当前登录用户信息。"""
    return ApiResponse(data=current_user)


class EmployeeLoginRequest(LoginRequest):
    """员工登录请求。"""
    pass