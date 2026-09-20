# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""健康检查与 API 测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.admin_ai.core.auth.jwt_token import create_access_token
from app.admin_ai.main import create_app


class TestHealthAPI:
    """健康检查 API 测试。"""

    async def test_health_endpoint(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"

    async def test_chat_send_requires_auth(self) -> None:
        """认证上线后，未携带 Token 的对话请求返回 401。"""
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/chat/send", json={"message": "你好"})
        assert response.status_code == 401
        data = response.json()
        assert data["code"] == 40002

    @pytest.mark.integration
    async def test_tasks_my_endpoint(self) -> None:
        """需要数据库的集成测试。

        注意：全局 `stub_audit_db` fixture 会把 `get_session_factory` 打桩成 MagicMock，
        而本用例要打真实 PostgreSQL，因此这里自建引擎并覆盖 `get_db_session` 依赖
        （原实现未覆盖，导致该用例被 `-m integration` 选中时必挂）。
        """
        from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

        from app.admin_ai.config import get_config
        from app.admin_ai.db.database import get_db_session

        engine = create_async_engine(get_config().DATABASE_URL)
        factory = async_sessionmaker(engine, expire_on_commit=False)
        app = create_app()

        async def _override_db():
            async with factory() as session:
                yield session

        app.dependency_overrides[get_db_session] = _override_db
        try:
            transport = ASGITransport(app=app)
            token = create_access_token(
                {"sub": "user_001", "employee_id": "EMP1001", "role": "employee"}
            )
            headers = {"Authorization": f"Bearer {token}"}
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.get("/api/v1/tasks/my", headers=headers)
            assert response.status_code == 200
            data = response.json()
            assert data["code"] == 0
            assert data["data"]["scope"] == "my"
        finally:
            app.dependency_overrides.clear()
            await engine.dispose()