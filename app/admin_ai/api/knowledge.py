# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""知识库管理接口。"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.api.response import ApiResponse, BusinessError
from app.admin_ai.api.schemas import KnowledgeUploadRequest, KnowledgeSearchRequest
from app.admin_ai.core.auth.deps import get_admin_user, get_current_user
from app.admin_ai.db.database import get_db_session
from app.admin_ai.db.models import KnowledgeDocModel

router = APIRouter(prefix="/knowledge", tags=["知识库"])


@router.post("/upload", response_model=ApiResponse[dict])
async def upload_knowledge(
    request: KnowledgeUploadRequest,
    current_user: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """上传知识文档（管理员）。"""
    doc = KnowledgeDocModel(
        title=request.title,
        category=request.category,
        tags=request.tags,
        content=request.content,
        created_by=current_user.get("user_id"),
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)

    return ApiResponse(data={
        "id": doc.id,
        "title": doc.title,
        "category": doc.category,
        "status": "pending_index",
    })


@router.post("/search", response_model=ApiResponse[dict])
async def search_knowledge(
    request: KnowledgeSearchRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """搜索知识库。"""
    # TODO: 接入 RAG 向量检索，当前使用 ILIKE 关键词匹配作为占位
    query = select(KnowledgeDocModel).where(KnowledgeDocModel.is_active == True)

    if request.query:
        search_pattern = f"%{request.query}%"
        query = query.where(
            KnowledgeDocModel.title.ilike(search_pattern)
            | KnowledgeDocModel.content.ilike(search_pattern)
        )

    if request.category:
        query = query.where(KnowledgeDocModel.category == request.category)

    query = query.limit(request.top_k)
    result = await db.execute(query)
    docs = result.scalars().all()

    # 补充 tags 匹配
    filtered = []
    for d in docs:
        if request.query and request.query not in (d.title or "") and request.query not in (d.content or ""):
            if d.tags and request.query in d.tags:
                filtered.append(d)
        else:
            filtered.append(d)

    return ApiResponse(data={
        "query": request.query,
        "results": [
            {
                "id": d.id,
                "title": d.title,
                "category": d.category,
                "tags": d.tags,
            }
            for d in filtered
        ],
        "total": len(filtered),
    })


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
    current_user: dict = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db_session),
) -> ApiResponse[dict]:
    """删除知识文档（管理员）。"""
    result = await db.execute(
        select(KnowledgeDocModel).where(KnowledgeDocModel.id == doc_id)
    )
    doc = result.scalar_one_or_none()
    if not doc:
        raise BusinessError(code=40004, message="文档不存在")

    doc.is_active = False
    await db.commit()

    return ApiResponse(data={"id": doc_id, "status": "deleted"})