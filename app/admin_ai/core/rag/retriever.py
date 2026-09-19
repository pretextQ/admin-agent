# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""RAG 检索器。"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)

CHUNK_SIZE = 400
CHUNK_OVERLAP = 50
COLLECTION_NAME = "knowledge_base"
# 单次向量库调用（含首次嵌入模型加载）的超时；超时按不可用降级，避免请求挂起
RAG_TIMEOUT_SECONDS = 30


def chunk_text(text: str) -> list[str]:
    """把文档内容切成带重叠的片段，供向量化入库。"""
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= CHUNK_SIZE:
        return [text]
    chunks = []
    start = 0
    while start < len(text):
        chunks.append(text[start:start + CHUNK_SIZE])
        start += CHUNK_SIZE - CHUNK_OVERLAP
    return chunks


class RAGRetriever:
    """RAG 检索器。

    chroma_client 未初始化（依赖缺失/初始化失败）时所有方法优雅降级：
    retrieve 返回空列表，add_documents 返回 0。
    """

    def __init__(self, chroma_client: Any = None, embedder: Any = None) -> None:
        self._chroma = chroma_client
        self._embedder = embedder

    def _get_collection(self) -> Any:
        return self._chroma.get_or_create_collection(COLLECTION_NAME)

    @staticmethod
    async def _run(func: Any, *args: Any, **kwargs: Any) -> Any:
        """在线程中执行同步的 Chroma 调用，并施加超时保护。"""
        return await asyncio.wait_for(
            asyncio.to_thread(func, *args, **kwargs), timeout=RAG_TIMEOUT_SECONDS
        )

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """检索知识库，返回 [{content, metadata, distance}]。"""
        if self._chroma is None:
            return []
        try:
            collection = await self._run(self._get_collection)
            results = await self._run(
                collection.query,
                query_texts=[query],
                n_results=top_k,
                where=filters or None,
            )
            docs = []
            for i, doc in enumerate(results["documents"][0]):
                docs.append({
                    "content": doc,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0,
                })
            return docs
        except Exception as e:
            logger.error("RAG 检索失败", error=str(e))
            return []

    async def add_documents(self, chunks: list[str], metadatas: list[dict[str, Any]]) -> int:
        """把分片写入向量库，返回成功写入数量。"""
        if self._chroma is None or not chunks:
            return 0
        try:
            collection = await self._run(self._get_collection)
            ids = [str(uuid.uuid4()) for _ in chunks]
            await self._run(
                collection.add, documents=chunks, metadatas=metadatas, ids=ids
            )
            return len(chunks)
        except Exception as e:
            logger.error("RAG 写入失败", error=str(e))
            return 0

    async def delete_documents(self, doc_id: str) -> None:
        """按文档 id 删除其全部分片。"""
        if self._chroma is None:
            return
        try:
            collection = await self._run(self._get_collection)
            await self._run(collection.delete, where={"doc_id": doc_id})
        except Exception as e:
            logger.error("RAG 删除失败", error=str(e))


def build_retriever(config: Any) -> RAGRetriever:
    """按配置构建检索器。

    优先连接 Chroma 服务（CHROMA_HOST/PORT，探活失败视为未部署），
    回退到本地嵌入式持久化目录，仍失败则返回降级实例。
    """
    try:
        import chromadb
    except ImportError:
        logger.warning("chromadb 未安装，RAG 不可用")
        return RAGRetriever(None)

    try:
        client = chromadb.HttpClient(host=config.CHROMA_HOST, port=config.CHROMA_PORT)
        client.heartbeat()
        logger.info("RAG 使用 Chroma 服务", host=config.CHROMA_HOST, port=config.CHROMA_PORT)
        return RAGRetriever(client)
    except Exception:
        logger.info("Chroma 服务不可用，使用本地嵌入式向量库", path=config.CHROMA_PERSIST_PATH)

    try:
        client = chromadb.PersistentClient(path=config.CHROMA_PERSIST_PATH)
        return RAGRetriever(client)
    except Exception as e:
        logger.warning("本地向量库初始化失败，RAG 不可用", error=str(e))
        return RAGRetriever(None)
