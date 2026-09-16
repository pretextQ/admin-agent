# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""Pydantic Schema 定义。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class BaseSchema(BaseModel):
    """所有 Schema 的基类。"""
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class UserCreateSchema(BaseSchema):
    """创建用户请求。"""
    employee_id: str = Field(..., min_length=1, max_length=50, description="工号")
    name: str = Field(..., min_length=1, max_length=100, description="姓名")
    department: Optional[str] = Field(None, max_length=100, description="部门")
    email: Optional[str] = Field(None, max_length=200, description="邮箱")


class UserResponse(BaseSchema):
    """用户响应。"""
    id: str
    employee_id: str
    name: str
    department: Optional[str] = None
    role: str
    is_active: bool
    created_at: datetime


class TaskCreateSchema(BaseSchema):
    """创建任务请求。"""
    type: str = Field(..., description="任务类型")
    title: Optional[str] = Field(None, max_length=200, description="标题")
    data: Optional[Dict[str, Any]] = Field(None, description="业务数据")


class TaskResponse(BaseSchema):
    """任务响应。"""
    id: str
    type: str
    status: str
    title: Optional[str] = None
    risk_level: str
    created_at: datetime


class TaskListResponse(BaseSchema):
    """任务列表响应。"""
    tasks: List[TaskResponse]
    total: int
    page: int = 1
    page_size: int = 20
    pending_count: int = 0
    approving_count: int = 0