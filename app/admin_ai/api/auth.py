# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""认证接口。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.api.response import ApiResponse, BusinessError
from app.admin_ai.api.schemas import TokenResponse
from app.admin_ai.config import Environment, get_config
from app.admin_ai.core.auth.deps import get_current_user
from app.admin_ai.core.auth.jwt_token import create_access_token
from app.admin_ai.core.auth.sso import (
    exchange_code_for_token,
    generate_login_url,
    generate_state,
    get_user_info,
)
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import UserModel

router = APIRouter(prefix="/auth", tags=["认证"])


@router.get("/feishu/login-url", response_model=ApiResponse[dict])
async def feishu_login_url(request: Request) -> ApiResponse[dict]:
    """生成飞书授权跳转地址。"""
    import redis.asyncio as redis

    config = get_config()
    state = generate_state()
    try:
        redis_client = redis.from_url(config.REDIS_URL)
        await redis_client.set(f"feishu_state:{state}", "1", ex=300)
        await redis_client.close()
    except Exception:
        pass  # Redis 不可用时仍返回 state（开发环境）
    url = generate_login_url(state)
    return ApiResponse(data={"login_url": url, "state": state})


@router.get("/feishu/callback", response_model=ApiResponse[TokenResponse])
async def feishu_callback(
    code: str = Query(...),
    state: str = Query(...),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[TokenResponse]:
    """飞书 OAuth 回调。"""
    import redis.asyncio as redis

    config = get_config()

    # 1. 校验 state
    try:
        redis_client = redis.from_url(config.REDIS_URL)
        stored = await redis_client.get(f"feishu_state:{state}")
        await redis_client.delete(f"feishu_state:{state}")
        await redis_client.close()
        if not stored:
            raise BusinessError(code=40001, message="无效的 state 参数")
    except BusinessError:
        raise
    except Exception:
        pass  # Redis 不可用时跳过校验（开发环境）

    # 2. 换取 token
    try:
        token_data = await exchange_code_for_token(code)
    except Exception as e:
        raise BusinessError(code=50002, message=f"换取飞书 token 失败: {e}")

    user_access_token = token_data.get("access_token")
    if not user_access_token:
        raise BusinessError(code=50002, message="飞书未返回 access_token")

    # 3. 获取用户信息
    try:
        user_info = await get_user_info(user_access_token)
    except Exception as e:
        raise BusinessError(code=50002, message=f"获取飞书用户信息失败: {e}")

    open_id = user_info.get("open_id")
    name = user_info.get("name", "未知用户")
    employee_number = user_info.get("employee_number", open_id)

    if not open_id:
        raise BusinessError(code=50002, message="飞书未返回 open_id")

    # 4. upsert 本地 users 表
    result = await db.execute(select(UserModel).where(UserModel.open_id == open_id))
    user = result.scalar_one_or_none()
    if not user:
        user = UserModel(
            employee_id=employee_number,
            name=name,
            open_id=open_id,
            role="employee",
        )
        db.add(user)
        await db.flush()

    # 5. 签发本地 JWT
    jwt_token = create_access_token(data={
        "sub": user.id,
        "employee_id": user.employee_id,
        "role": user.role,
    })

    return ApiResponse(data=TokenResponse(
        access_token=jwt_token,
        token_type="bearer",
        expires_in=config.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    ))


@router.get("/dev-login", response_model=ApiResponse[TokenResponse])
async def dev_login(
    employee_id: str = Query("admin001"),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[TokenResponse]:
    """开发环境登录（仅 development 可用）。"""
    config = get_config()
    if config.ENVIRONMENT != Environment.DEVELOPMENT:
        raise BusinessError(code=40003, message="dev-login 仅开发环境可用")

    # 查询或创建用户
    result = await db.execute(select(UserModel).where(UserModel.employee_id == employee_id))
    user = result.scalar_one_or_none()
    if not user:
        user = UserModel(
            employee_id=employee_id,
            name=f"开发用户-{employee_id}",
            role="admin" if employee_id == "admin001" else "employee",
        )
        db.add(user)
        await db.flush()

    token = create_access_token(data={
        "sub": user.id,
        "employee_id": user.employee_id,
        "role": user.role,
    })
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