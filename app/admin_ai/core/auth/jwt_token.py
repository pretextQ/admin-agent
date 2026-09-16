# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""JWT 令牌签发与验签。"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from jose import JWTError, jwt
import structlog

from app.admin_ai.config import get_config

logger = structlog.get_logger(__name__)

ALGORITHM = "HS256"


def create_access_token(
    data: dict[str, Any],
    expires_delta: Optional[timedelta] = None,
) -> str:
    """签发访问令牌。

    Args:
        data: 令牌载荷，至少包含 sub（用户ID）和 role。
        expires_delta: 过期时长，默认从配置读取。

    Returns:
        编码后的 JWT 字符串。
    """
    config = get_config()
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> dict[str, Any]:
    """验签并解码令牌。

    Args:
        token: JWT 字符串。

    Returns:
        令牌载荷字典。

    Raises:
        ValueError: 令牌无效或已过期。
    """
    config = get_config()
    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[str] = payload.get("sub")
        if user_id is None:
            raise ValueError("令牌缺少 sub 字段")
        return payload
    except JWTError as exc:
        logger.warning("JWT 验签失败", error=str(exc))
        raise ValueError(f"令牌无效: {exc}") from exc
