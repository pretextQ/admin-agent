# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""知识库管理接口。"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.api.response import ApiResponse, BusinessError
from app.admin_ai.api.schemas import KnowledgeUploadRequest, KnowledgeSearchRequest
from app.admin_ai.core.auth.deps import get_admin_user, get_current_user
from app.admin_ai.core.rag.retriever import RAGRetriever, chunk_text
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import KnowledgeDocModel

router = APIRouter(prefix="/knowledge", tags=["知识库"])


def _get_retriever(request: Request) -> Optional[RAGRetriever]:
    """从应用状态获取检索器；未初始化时返回 None（降级为关键词检索）。"""
    return getattr(request.app.state, "retriever", None)


@router.post("/upload", response_model=ApiResponse[dict])
async def upload_knowledge(
    payload: KnowledgeUploadRequest,
    request: Request,
    current_user: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """上传知识文档（管理员），内容分片后向量化入库。"""
    doc = KnowledgeDocModel(
        title=payload.title,
        category=payload.category,
        tags=payload.tags,
        content=payload.content,
        source_uri=payload.source_uri,
        created_by=current_user.get("user_id"),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    indexed = 0
    retriever = _get_retriever(request)
    if retriever is not None and payload.content:
        chunks = chunk_text(payload.content)
        metadatas = [
            {
                "doc_id": doc.id,
                "title": doc.title,
                "category": doc.category,
                "source_uri": payload.source_uri or "",
                "chunk_index": i,
            }
            for i in range(len(chunks))
        ]
        indexed = await retriever.add_documents(chunks, metadatas)
        doc.chunk_count = indexed
        await db.commit()
        await db.refresh(doc)

    return ApiResponse(data={
        "id": doc.id,
        "title": doc.title,
        "category": doc.category,
        "chunk_count": indexed,
        "status": "indexed" if indexed else "pending_index",
    })


@router.post("/search", response_model=ApiResponse[dict])
async def search_knowledge(
    payload: KnowledgeSearchRequest,
    request: Request,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """搜索知识库：向量检索优先，不可用或无命中时回退关键词匹配。"""
    retriever = _get_retriever(request)
    results: list[KnowledgeDocModel] = []
    scores: dict[str, float] = {}

    if retriever is not None and payload.query:
        hits = await retriever.retrieve(payload.query, top_k=payload.top_k)
        doc_ids = [h["metadata"].get("doc_id") for h in hits if h.get("metadata", {}).get("doc_id")]
        if doc_ids:
            rows = (
                await db.execute(
                    select(KnowledgeDocModel).where(
                        KnowledgeDocModel.id.in_(doc_ids),
                        KnowledgeDocModel.is_active == True,  # noqa: E712
                    )
                )
            ).scalars().all()
            by_id = {d.id: d for d in rows}
            for hit in hits:
                doc = by_id.get(hit["metadata"].get("doc_id"))
                if doc is None:
                    continue
                if payload.category and doc.category != payload.category:
                    continue
                if doc.id not in scores:
                    results.append(doc)
                    scores[doc.id] = hit.get("distance", 0)

    if not results:
        results, scores = await _keyword_search(db, payload)

    return ApiResponse(data={
        "query": payload.query,
        "results": [
            {
                "id": d.id,
                "title": d.title,
                "category": d.category,
                "tags": d.tags,
                "score": scores.get(d.id),
            }
            for d in results
        ],
        "total": len(results),
    })


async def _keyword_search(
    db: AsyncSession, payload: KnowledgeSearchRequest
) -> tuple[list[KnowledgeDocModel], dict[str, float]]:
    """关键词兜底检索：ILIKE 命中 title/content，另补 tags 匹配（窗口放大后过滤）。"""
    query = select(KnowledgeDocModel).where(KnowledgeDocModel.is_active == True)  # noqa: E712
    if payload.query:
        pattern = f"%{payload.query}%"
        query = query.where(
            KnowledgeDocModel.title.ilike(pattern)
            | KnowledgeDocModel.content.ilike(pattern)
        )
    if payload.category:
        query = query.where(KnowledgeDocModel.category == payload.category)

    # 放大候选窗口，tags 纯匹配的文档也有机会进入结果
    rows = (await db.execute(query.limit(payload.top_k * 5))).scalars().all()
    results = list(rows)

    if payload.query:
        tag_rows = (
            await db.execute(
                select(KnowledgeDocModel)
                .where(
                    KnowledgeDocModel.is_active == True,  # noqa: E712
                    KnowledgeDocModel.tags.isnot(None),
                )
                .limit(200)
            )
        ).scalars().all()
        seen = {d.id for d in results}
        for d in tag_rows:
            if d.id in seen:
                continue
            if payload.category and d.category != payload.category:
                continue
            if any(payload.query in str(t) for t in (d.tags or [])):
                results.append(d)
                seen.add(d.id)

    results = results[: payload.top_k]
    return results, {}


@router.get("/list", response_model=ApiResponse[dict])
async def list_knowledge(
    category: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
    current_user: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """知识库文档列表（管理员）。"""
    query = select(KnowledgeDocModel).where(KnowledgeDocModel.is_active == True)
    if category:
        query = query.where(KnowledgeDocModel.category == category)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(KnowledgeDocModel.created_at.desc())
    result = await db.execute(query)
    docs = result.scalars().all()

    return ApiResponse(data={
        "items": [
            {
                "id": d.id,
                "title": d.title,
                "category": d.category,
                "tags": d.tags,
                "chunk_count": d.chunk_count,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    })


@router.delete("/{doc_id}", response_model=ApiResponse[dict])
async def delete_knowledge(
    doc_id: str,
    request: Request,
    current_user: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """删除知识文档（管理员），同步清理向量分片。"""
    result = await db.execute(
        select(KnowledgeDocModel).where(KnowledgeDocModel.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise BusinessError(code=40004, message="文档不存在")

    doc.is_active = False
    await db.commit()

    retriever = _get_retriever(request)
    if retriever is not None:
        await retriever.delete_documents(doc_id)

    return ApiResponse(data={"id": doc_id, "status": "deleted"})