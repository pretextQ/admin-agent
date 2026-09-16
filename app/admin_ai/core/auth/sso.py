# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""飞书 OAuth SSO 模块。"""

from __future__ import annotations

import secrets
from typing import Any

import httpx
import structlog

from app.admin_ai.config import get_config

logger = structlog.get_logger(__name__)

FEISHU_AUTH_URL = "https://open.feishu.cn/open-apis/authen/v1/index"
FEISHU_TOKEN_URL = "https://open.feishu.cn/open-apis/authen/v2/oauth/token"
FEISHU_USER_INFO_URL = "https://open.feishu.cn/open-apis/authen/v1/user_info"


def generate_state() -> str:
    """生成随机 state 用于 CSRF 防护。"""
    return secrets.token_urlsafe(32)


def generate_login_url(state: str) -> str:
    """生成飞书授权跳转地址。"""
    config = get_config()
    return (
        f"{FEISHU_AUTH_URL}"
        f"?app_id={config.FEISHU_APP_ID}"
        f"&redirect_uri={config.FEISHU_REDIRECT_URI}"
        f"&state={state}"
    )


async def exchange_code_for_token(code: str) -> dict[str, Any]:
    """用授权码换取 user_access_token。"""
    config = get_config()
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            FEISHU_TOKEN_URL,
            json={
                "app_id": config.FEISHU_APP_ID,
                "app_secret": config.FEISHU_APP_SECRET,
                "code": code,
                "grant_type": "authorization_code",
            },
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"飞书换取 token 失败: {data.get('msg')}")
        return data.get("data", {})


async def get_user_info(user_access_token: str) -> dict[str, Any]:
    """用 user_access_token 获取用户信息。"""
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            FEISHU_USER_INFO_URL,
            headers={"Authorization": f"Bearer {user_access_token}"},
            timeout=10.0,
        )
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 0:
            raise ValueError(f"飞书获取用户信息失败: {data.get('msg')}")
        return data.get("data", {})