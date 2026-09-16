# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""知识库管理接口。"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from app.admin_ai.api.response import ApiResponse
from app.admin_ai.api.schemas import KnowledgeUploadRequest, KnowledgeSearchRequest

router = APIRouter(prefix="/knowledge", tags=["知识库"])


@router.post("/upload", response_model=ApiResponse[dict])
async def upload_knowledge(request: KnowledgeUploadRequest) -> ApiResponse[dict]:
    """上传知识文档。"""
    return ApiResponse(data={"id": "doc_demo", "title": request.title, "status": "indexed"})


@router.post("/search", response_model=ApiResponse[dict])
async def search_knowledge(request: KnowledgeSearchRequest) -> ApiResponse[dict]:
    """搜索知识库。"""
    return ApiResponse(data={"query": request.query, "results": [], "total": 0})


@router.get("/list", response_model=ApiResponse[dict])
async def list_knowledge(
    category: Optional[str] = None, page: int = 1, page_size: int = 20
) -> ApiResponse[dict]:
    """知识库文档列表。"""
    return ApiResponse(data={"documents": [], "total": 0, "page": page, "page_size": page_size})


@router.delete("/{doc_id}", response_model=ApiResponse[dict])
async def delete_knowledge(doc_id: str) -> ApiResponse[dict]:
    """删除知识文档。"""
    return ApiResponse(data={"id": doc_id, "status": "deleted"})