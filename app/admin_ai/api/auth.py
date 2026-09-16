# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""认证接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.admin_ai.api.deps_context import APIContext, get_api_context
from app.admin_ai.api.response import ApiResponse
from app.admin_ai.api.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(
    payload: LoginRequest,
    context: APIContext = Depends(get_api_context),
) -> ApiResponse[TokenResponse]:
    """登录并签发 JWT。"""
    return ApiResponse(data=TokenResponse(
        access_token="demo-token",
        token_type="bearer",
        expires_in=3600,
    ))


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
async def refresh_token() -> ApiResponse[TokenResponse]:
    """刷新访问令牌。"""
    return ApiResponse(data=TokenResponse(
        access_token="refreshed-token",
        token_type="bearer",
        expires_in=3600,
    ))


@router.get("/me", response_model=ApiResponse[dict])
async def get_me() -> ApiResponse[dict]:
    """获取当前登录用户信息。"""
    return ApiResponse(data={"user_id": "demo", "role": "employee"})