# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""RAG 检索器测试。"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.admin_ai.core.rag.retriever import RAGRetriever, chunk_text


def test_chunk_text_short_returns_single() -> None:
    assert chunk_text("短文本") == ["短文本"]
    assert chunk_text("") == []
    assert chunk_text("   ") == []


def test_chunk_text_long_splits_with_overlap() -> None:
    text = "字" * 1000
    chunks = chunk_text(text)
    assert len(chunks) >= 3
    assert all(len(c) <= 400 for c in chunks)
    # 相邻分片有重叠
    assert chunks[0][-50:] == chunks[1][:50]


def _fake_chroma(query_result: dict | None = None) -> tuple[MagicMock, MagicMock]:
    collection = MagicMock()
    if query_result is not None:
        collection.query.return_value = query_result
    client = MagicMock()
    client.get_or_create_collection.return_value = collection
    return client, collection


async def test_retrieve_parses_chroma_results() -> None:
    client, collection = _fake_chroma({
        "documents": [["年假按司龄计算"]],
        "metadatas": [[{"title": "考勤制度", "doc_id": "d1"}]],
        "distances": [[0.15]],
    })
    retriever = RAGRetriever(client)
    docs = await retriever.retrieve("年假", top_k=1)

    assert docs == [{
        "content": "年假按司龄计算",
        "metadata": {"title": "考勤制度", "doc_id": "d1"},
        "distance": 0.15,
    }]
    collection.query.assert_called_once()


async def test_retrieve_degrades_without_client() -> None:
    retriever = RAGRetriever(None)
    assert await retriever.retrieve("anything") == []


async def test_retrieve_degrades_on_error() -> None:
    client, collection = _fake_chroma()
    collection.query.side_effect = RuntimeError("boom")
    retriever = RAGRetriever(client)
    assert await retriever.retrieve("anything") == []


async def test_retrieve_times_out_and_degrades(monkeypatch) -> None:
    """向量库调用挂起（如嵌入模型下载卡住）时按超时降级而不是无限等待。"""
    import time

    import app.admin_ai.core.rag.retriever as retriever_module

    monkeypatch.setattr(retriever_module, "RAG_TIMEOUT_SECONDS", 0.05)
    client, collection = _fake_chroma()

    def slow_query(**kwargs):
        time.sleep(0.3)
        return {"documents": [["x"]], "metadatas": [[{}]], "distances": [[0.1]]}

    collection.query.side_effect = slow_query
    retriever = RAGRetriever(client)
    assert await retriever.retrieve("q") == []


async def test_add_documents_returns_count() -> None:
    client, collection = _fake_chroma()
    retriever = RAGRetriever(client)
    count = await retriever.add_documents(["a", "b"], [{"doc_id": "d"}, {"doc_id": "d"}])

    assert count == 2
    collection.add.assert_called_once()
    kwargs = collection.add.call_args.kwargs
    assert len(kwargs["ids"]) == 2
    assert kwargs["documents"] == ["a", "b"]


async def test_add_documents_degrades_without_client() -> None:
    retriever = RAGRetriever(None)
    assert await retriever.add_documents(["a"], []) == 0
    assert await retriever.add_documents([], [{"doc_id": "d"}]) == 0


async def test_delete_documents_filters_by_doc_id() -> None:
    client, collection = _fake_chroma()
    retriever = RAGRetriever(client)
    await retriever.delete_documents("doc-123")
    collection.delete.assert_called_once_with(where={"doc_id": "doc-123"})
