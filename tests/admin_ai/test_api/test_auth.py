# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""认证接口测试。"""

from __future__ import annotations

import sys
from types import ModuleType
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.core.auth.jwt_token import create_access_token
from app.admin_ai.main import create_app


def _mock_db_session(user: MagicMock | None = None) -> AsyncSession:
    """构造 mock 数据库会话。"""
    mock_session = AsyncMock(spec=AsyncSession)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_session.execute.return_value = mock_result
    return mock_session


def _make_redis_mock() -> tuple[MagicMock, MagicMock]:
    """构造 mock redis 模块和客户端。"""
    mock_redis_client = AsyncMock()
    mock_redis_client.get.return_value = b"1"
    mock_redis_client.set = AsyncMock()
    mock_redis_client.delete = AsyncMock()
    mock_redis_client.close = AsyncMock()

    mock_redis_asyncio = MagicMock()
    mock_redis_asyncio.from_url.return_value = mock_redis_client

    mock_redis = ModuleType("redis")
    mock_redis.asyncio = mock_redis_asyncio  # type: ignore[attr-defined]

    return mock_redis, mock_redis_asyncio


async def test_dev_login_works_in_development() -> None:
    """dev-login 在开发环境可用。"""
    app = create_app()
    transport = ASGITransport(app=app)
    mock_db = _mock_db_session(user=None)

    from app.admin_ai.db.database import get_db_session

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override_db
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/auth/dev-login?employee_id=test001")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "access_token" in data["data"]
        assert data["data"]["token_type"] == "bearer"
    finally:
        app.dependency_overrides.clear()


async def test_feishu_callback_with_mock() -> None:
    """飞书回调全链路（mock exchange_code_for_token 和 get_user_info）。"""
    app = create_app()
    transport = ASGITransport(app=app)
    mock_db = _mock_db_session(user=None)
    mock_redis, _ = _make_redis_mock()

    from app.admin_ai.db.database import get_db_session

    async def _override_db():
        yield mock_db

    app.dependency_overrides[get_db_session] = _override_db

    with patch("app.admin_ai.api.auth.exchange_code_for_token", new_callable=AsyncMock) as mock_exchange, \
         patch("app.admin_ai.api.auth.get_user_info", new_callable=AsyncMock) as mock_user_info, \
         patch.dict(sys.modules, {"redis": mock_redis, "redis.asyncio": mock_redis.asyncio}):
        mock_exchange.return_value = {"access_token": "test_feishu_token"}
        mock_user_info.return_value = {
            "open_id": "ou_test123",
            "name": "测试用户",
            "employee_number": "EMP999",
        }
        try:
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get(
                    "/api/v1/auth/feishu/callback?code=test_code&state=test_state"
                )
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert "access_token" in data["data"]
            mock_exchange.assert_called_once_with("test_code")
            mock_user_info.assert_called_once_with("test_feishu_token")
        finally:
            app.dependency_overrides.clear()


async def test_no_token_returns_401() -> None:
    """无 Token 访问 /chat/send 返回 40002。"""
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/chat/send", json={"message": "你好"})
    assert response.status_code == 401
    data = response.json()
    assert data["code"] == 40002