# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""RAG 检索器。"""

from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class RAGRetriever:
    """RAG 检索器。"""

    def __init__(self, chroma_client: Any = None, embedder: Any = None) -> None:
        self._chroma = chroma_client
        self._embedder = embedder

    async def retrieve(
        self,
        query: str,
        top_k: int = 5,
        filters: Optional[dict[str, Any]] = None,
    ) -> list[dict[str, Any]]:
        """检索知识库。"""
        if self._chroma is None:
            return []
        try:
            collection = self._chroma.get_or_create_collection("knowledge_base")
            results = collection.query(query_texts=[query], n_results=top_k)
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