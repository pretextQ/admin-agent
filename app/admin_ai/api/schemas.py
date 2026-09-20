# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""API 请求/响应 Schema。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求。"""
    employee_id: str
    password: str


class TokenResponse(BaseModel):
    """令牌响应。"""
    access_token: str
    token_type: str = "bearer"
    expires_in: int


class ChatRequest(BaseModel):
    """对话请求。"""
    conversation_id: Optional[str] = None
    message: str
    attachments: Optional[list[str]] = None


class ChatResponse(BaseModel):
    """对话响应。"""
    conversation_id: str
    message_id: str
    content: str
    content_type: str = "text"
    card_data: Optional[dict[str, Any]] = None
    suggestions: Optional[list[str]] = None
    requires_action: bool = False
    tool_calls: Optional[list[dict[str, Any]]] = None


class ConfirmRequest(BaseModel):
    """高风险操作确认。"""
    confirmed: bool
    comment: Optional[str] = None


class TransferRequest(BaseModel):
    """转人工请求。"""
    reason: Optional[str] = None


class ApprovalRequest(BaseModel):
    """审批请求。"""
    action: str
    comment: Optional[str] = None
    add_sign_user_id: Optional[str] = None


class KnowledgeUploadRequest(BaseModel):
    """知识上传。"""
    title: str
    category: str
    tags: list[str] = []
    content: Optional[str] = None
    source_uri: Optional[str] = None


class KnowledgeSearchRequest(BaseModel):
    """知识搜索。"""
    query: str
    category: Optional[str] = None
    top_k: int = 5


class ApprovalRuleRequest(BaseModel):
    """审批规则新增/更新（设计 §2.3）。"""
    id: Optional[str] = None
    business_type: str
    amount_min: Optional[float] = None
    amount_max: Optional[float] = None
    step_order: int = 1
    approver_type: str
    approver_param: Optional[str] = None
    approval_mode: str = "any_one"
    required: bool = True
    enabled: bool = True
    remark: Optional[str] = None


class ApprovalDelegationRequest(BaseModel):
    """代理审批委派新增（设计 §2.4）。"""
    delegator_id: str
    delegate_id: str
    start_at: datetime
    end_at: datetime
    business_types: Optional[list[str]] = None


class OrgSyncRequest(BaseModel):
    """手动触发组织同步。"""
    provider: Optional[str] = None
    csv_dir: Optional[str] = None