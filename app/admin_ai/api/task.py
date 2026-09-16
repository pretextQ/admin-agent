# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""任务/待办接口。"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter

from app.admin_ai.api.response import ApiResponse
from app.admin_ai.api.schemas import ApprovalRequest

router = APIRouter(prefix="/tasks", tags=["任务"])


@router.get("/my", response_model=ApiResponse[dict])
async def get_my_tasks(
    status: Optional[str] = None,
    type: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> ApiResponse[dict]:
    """获取我的任务列表。"""
    return ApiResponse(data={
        "tasks": [], "total": 0, "page": page, "page_size": page_size,
        "pending_count": 0, "approving_count": 0,
    })


@router.get("/pending-approval", response_model=ApiResponse[dict])
async def get_pending_approval_tasks(page: int = 1, page_size: int = 20) -> ApiResponse[dict]:
    """获取待我审批的任务。"""
    return ApiResponse(data={"tasks": [], "total": 0, "page": page, "page_size": page_size})


@router.get("/{task_id}", response_model=ApiResponse[dict])
async def get_task_detail(task_id: str) -> ApiResponse[dict]:
    """获取任务详情。"""
    return ApiResponse(data={"id": task_id, "status": "pending"})


@router.post("/{task_id}/approve", response_model=ApiResponse[dict])
async def approve_task(task_id: str, payload: ApprovalRequest) -> ApiResponse[dict]:
    """审批任务。"""
    return ApiResponse(data={"id": task_id, "action": payload.action, "status": "completed"})


@router.post("/{task_id}/cancel", response_model=ApiResponse[dict])
async def cancel_task(task_id: str) -> ApiResponse[dict]:
    """取消任务。"""
    return ApiResponse(data={"id": task_id, "status": "cancelled"})


@router.get("/{task_id}/timeline", response_model=ApiResponse[dict])
async def get_task_timeline(task_id: str) -> ApiResponse[dict]:
    """获取任务状态时间线。"""
    return ApiResponse(data={"task_id": task_id, "timeline": []})