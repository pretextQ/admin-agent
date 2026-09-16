# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""管理后台接口。"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter

from app.admin_ai.api.response import ApiResponse

router = APIRouter(prefix="/admin", tags=["管理后台"])


@router.get("/dashboard", response_model=ApiResponse[dict])
async def get_dashboard() -> ApiResponse[dict]:
    """仪表盘数据。"""
    return ApiResponse(data={
        "today_conversations": 0, "today_tasks": 0,
        "transfer_rate": 0.0, "top_intents": [],
    })


@router.get("/audit-logs", response_model=ApiResponse[dict])
async def get_audit_logs(
    user_id: Optional[str] = None, action: Optional[str] = None,
    page: int = 1, page_size: int = 50,
) -> ApiResponse[dict]:
    """审计日志查询。"""
    return ApiResponse(data={"logs": [], "total": 0, "page": page, "page_size": page_size})


@router.get("/tools", response_model=ApiResponse[dict])
async def list_tools() -> ApiResponse[dict]:
    """工具列表。"""
    return ApiResponse(data={"tools": []})


@router.put("/tools/{tool_id}/config", response_model=ApiResponse[dict])
async def update_tool_config(tool_id: str, config: dict[str, Any]) -> ApiResponse[dict]:
    """更新工具配置。"""
    return ApiResponse(data={"tool_id": tool_id, "config": config, "status": "updated"})


@router.get("/metrics", response_model=ApiResponse[dict])
async def get_metrics() -> ApiResponse[dict]:
    """系统指标。"""
    return ApiResponse(data={
        "llm_calls": 0, "token_cost": 0.0, "avg_response_time": 0.0,
        "completion_rate": 0.0, "transfer_rate": 0.0,
    })