# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""健康检查与 API 测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

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

    async def test_chat_send_endpoint(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/chat/send", json={"message": "你好"})
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "conversation_id" in data["data"]

    async def test_tasks_my_endpoint(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/tasks/my")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0