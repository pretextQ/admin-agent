# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""知识库接口测试。"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.core.auth.jwt_token import create_access_token
from app.admin_ai.core.rag.retriever import RAGRetriever
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import KnowledgeDocModel
from app.admin_ai.main import create_app


def _admin_headers() -> dict[str, str]:
    token = create_access_token({"sub": "admin1", "employee_id": "admin001", "role": "admin"})
    return {"Authorization": f"Bearer {token}"}


def _user_headers() -> dict[str, str]:
    token = create_access_token({"sub": "user1", "employee_id": "EMP001", "role": "employee"})
    return {"Authorization": f"Bearer {token}"}


class _MockResult:
    def __init__(self, value=None, rows=None) -> None:
        self._value = value
        self._rows = rows or []

    def scalar_one_or_none(self):
        return self._value

    def scalars(self):
        return self

    def all(self):
        return self._rows


def _install_db(app, results: list[_MockResult]) -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    db.execute = AsyncMock(side_effect=results)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    app.dependency_overrides[get_db_session] = lambda: db
    return db


async def test_upload_requires_admin() -> None:
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/knowledge/upload",
            json={"title": "考勤制度", "category": "hr"},
            headers=_user_headers(),
        )
    assert response.status_code == 403


async def test_upload_indexes_chunks() -> None:
    """上传文档后应分片写入向量库并回填 chunk_count。"""
    app = create_app()
    retriever = AsyncMock(spec=RAGRetriever)
    retriever.add_documents = AsyncMock(return_value=3)
    app.state.retriever = retriever
    _install_db(app, [_MockResult(), _MockResult()])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/knowledge/upload",
            json={
                "title": "考勤制度",
                "category": "hr",
                "content": "字" * 1000,
                "source_uri": "hr/attendance.pdf",
            },
            headers=_admin_headers(),
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "indexed"
    assert data["chunk_count"] == 3

    retriever.add_documents.assert_awaited_once()
    chunks, metadatas = retriever.add_documents.await_args.args
    assert len(chunks) == 3
    assert metadatas[0]["title"] == "考勤制度"
    assert metadatas[0]["source_uri"] == "hr/attendance.pdf"


async def test_search_vector_hits_preserve_order() -> None:
    """向量命中按相似度顺序返回，并带 score。"""
    app = create_app()
    retriever = AsyncMock(spec=RAGRetriever)
    retriever.retrieve = AsyncMock(return_value=[
        {"content": "b", "metadata": {"doc_id": "d2"}, "distance": 0.1},
        {"content": "a", "metadata": {"doc_id": "d1"}, "distance": 0.3},
    ])
    app.state.retriever = retriever

    doc1 = MagicMock(spec=KnowledgeDocModel)
    doc1.id = "d1"
    doc1.title = "A 制度"
    doc1.category = "hr"
    doc1.tags = []
    doc2 = MagicMock(spec=KnowledgeDocModel)
    doc2.id = "d2"
    doc2.title = "B 制度"
    doc2.category = "hr"
    doc2.tags = []
    _install_db(app, [_MockResult(rows=[doc1, doc2])])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/knowledge/search",
            json={"query": "报销"},
            headers=_user_headers(),
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert [r["id"] for r in data["results"]] == ["d2", "d1"]
    assert data["results"][0]["score"] == 0.1


async def test_search_falls_back_to_keyword_and_tags() -> None:
    """检索器不可用时回退关键词检索，且 tags 纯匹配的文档能进入结果。"""
    app = create_app()
    tag_doc = MagicMock(spec=KnowledgeDocModel)
    tag_doc.id = "d-tag"
    tag_doc.title = "员工手册"
    tag_doc.category = "hr"
    tag_doc.tags = ["考勤", "打卡"]
    # 第1次 execute: ILIKE 主查询无命中；第2次: tags 扫描命中
    _install_db(app, [_MockResult(rows=[]), _MockResult(rows=[tag_doc])])

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/knowledge/search",
            json={"query": "考勤"},
            headers=_user_headers(),
        )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["total"] == 1
    assert data["results"][0]["id"] == "d-tag"
    assert data["results"][0]["score"] is None
