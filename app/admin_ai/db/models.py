# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""SQLAlchemy 数据模型。"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.admin_ai.db.database import Base


def generate_uuid() -> str:
    """生成 UUID 字符串。"""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """无时区 UTC 时间，与 TIMESTAMP WITHOUT TIME ZONE 列约定一致。

    全项目时间统一使用本函数，禁止混用 datetime.utcnow 与带时区的 now()。
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ConversationStatus(str, Enum):
    """会话状态。"""
    ACTIVE = "active"
    COMPLETED = "completed"
    TRANSFERRED = "transferred"


class MessageRole(str, Enum):
    """消息角色。"""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class TaskStatus(str, Enum):
    """任务状态。"""
    PENDING = "pending"
    PROCESSING = "processing"
    APPROVING = "approving"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskType(str, Enum):
    """任务类型。"""
    LEAVE = "leave"
    EXPENSE = "expense"
    TRAVEL = "travel"
    MEETING_ROOM = "meeting_room"
    VEHICLE = "vehicle"
    MATERIAL = "material"
    ASSET = "asset"
    SEAL = "seal"
    CERTIFICATE = "certificate"
    ONBOARDING = "onboarding"


class ApprovalAction(str, Enum):
    """审批动作。"""
    APPROVE = "approve"
    REJECT = "reject"
    ADD_SIGN = "add_sign"


class ApprovalStatus(str, Enum):
    """审批记录状态。

    `approvals.status` 列为普通字符串（沿用首次迁移），故这里仅作取值约定：
    pending 待审 / approve 通过 / reject 驳回 / done 已处理（加签场景关闭原记录）
    / skipped 任一人通过后自动关闭的同步骤其他记录。
    """
    PENDING = "pending"
    APPROVE = "approve"
    REJECT = "reject"
    DONE = "done"
    SKIPPED = "skipped"


class ApproverType(str, Enum):
    """审批人解析方式（设计 §4.2）。"""
    SELF_DEPT_MANAGER = "self_dept_manager"
    PARENT_DEPT_MANAGER = "parent_dept_manager"
    TOP_DEPT_MANAGER = "top_dept_manager"
    ROLE = "role"
    USER = "user"


class ApprovalMode(str, Enum):
    """同一审批步骤多人的判定方式（设计 §4.3）。

    ANY_ONE 任一人通过即该步完成（默认，D-2 决策）；ALL_MUST 会签，全部通过才算完成。
    """
    ANY_ONE = "any_one"
    ALL_MUST = "all_must"


class UserModel(Base):
    """用户模型。"""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    employee_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)
    department_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("departments.id"), index=True, nullable=True
    )
    position: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    open_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, index=True, nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="employee", nullable=False)
    permissions: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    conversations: Mapped[List[ConversationModel]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tasks: Mapped[List[TaskModel]] = relationship(
        back_populates="user", foreign_keys="TaskModel.user_id"
    )

    def __repr__(self) -> str:
        return f"<UserModel(id={self.id}, employee_id={self.employee_id})>"


class ConversationModel(Base):
    """会话模型。"""
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    status: Mapped[ConversationStatus] = mapped_column(
        SAEnum(ConversationStatus, values_callable=lambda x: [e.value for e in x]), default=ConversationStatus.ACTIVE, nullable=False
    )
    intent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    business_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    context: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    user: Mapped[UserModel] = relationship(back_populates="conversations")
    messages: Mapped[List[MessageModel]] = relationship(
        back_populates="conversation",
        order_by="MessageModel.created_at",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ConversationModel(id={self.id}, user_id={self.user_id})>"


class MessageModel(Base):
    """消息模型。"""
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"), index=True, nullable=False
    )
    role: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole, values_callable=lambda x: [e.value for e in x]), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)

    conversation: Mapped[ConversationModel] = relationship(back_populates="messages")

    def __repr__(self) -> str:
        return f"<MessageModel(id={self.id}, role={self.role})>"


class TaskModel(Base):
    """任务模型。"""
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    conversation_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("conversations.id"), nullable=True
    )
    type: Mapped[TaskType] = mapped_column(SAEnum(TaskType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus, values_callable=lambda x: [e.value for e in x]), default=TaskStatus.PENDING, nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    approver_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped[UserModel] = relationship(back_populates="tasks", foreign_keys=[user_id])
    approver: Mapped[Optional[UserModel]] = relationship(foreign_keys=[approver_id])
    approvals: Mapped[List[ApprovalModel]] = relationship(
        back_populates="task", cascade="all, delete-orphan", order_by="ApprovalModel.created_at"
    )

    def __repr__(self) -> str:
        return f"<TaskModel(id={self.id}, type={self.type}, status={self.status})>"


class ApprovalModel(Base):
    """审批记录模型。"""
    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True, nullable=False)
    approver_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    step: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    action: Mapped[Optional[ApprovalAction]] = mapped_column(SAEnum(ApprovalAction, values_callable=lambda x: [e.value for e in x]), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    add_sign_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    # 审批人解析来源（ApproverType 取值），供审计追溯「为何是这个人审批」
    approver_source: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    # 该步骤多人判定方式快照（ApprovalMode 取值）；规则事后修改不影响在途审批
    mode: Mapped[str] = mapped_column(String(20), default="any_one", nullable=False)
    # 代理审批：本条记录由 delegated_from 委派给 approver_id 处理
    delegated_from: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    task: Mapped[TaskModel] = relationship(back_populates="approvals")

    def __repr__(self) -> str:
        return f"<ApprovalModel(id={self.id}, task_id={self.task_id}, status={self.status})>"


class DepartmentModel(Base):
    """部门树（设计 §2.1）。

    用物化路径（`path`）而非闭包表：200 人企业部门树 2~3 层，
    「本部门及所有子部门」查询退化为 `path LIKE '/公司/技术部%'`，无需递归 CTE。
    """
    __tablename__ = "departments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    parent_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("departments.id"), index=True, nullable=True
    )
    path: Mapped[str] = mapped_column(String(500), index=True, nullable=False)
    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    manager_id: Mapped[Optional[str]] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=True
    )
    # 上游（HR）部门 ID，同步幂等键；首期无上游接口时留空
    external_id: Mapped[Optional[str]] = mapped_column(String(100), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    def __repr__(self) -> str:
        return f"<DepartmentModel(id={self.id}, name={self.name})>"


class ApprovalRuleModel(Base):
    """审批路由规则（设计 §2.3）。

    金额区间为「含 amount_min、不含 amount_max」，NULL 表示无界；
    金额为空（如用印）的业务只匹配区间全为 NULL 的规则。
    """
    __tablename__ = "approval_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    business_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    amount_min: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    amount_max: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    step_order: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    approver_type: Mapped[ApproverType] = mapped_column(
        SAEnum(ApproverType, values_callable=lambda x: [e.value for e in x]), nullable=False
    )
    approver_param: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    approval_mode: Mapped[ApprovalMode] = mapped_column(
        SAEnum(ApprovalMode, values_callable=lambda x: [e.value for e in x]),
        default=ApprovalMode.ANY_ONE,
        nullable=False,
    )
    required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    remark: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    def __repr__(self) -> str:
        return f"<ApprovalRuleModel(id={self.id}, business_type={self.business_type})>"


class ApprovalDelegationModel(Base):
    """代理审批委派（设计 §2.4）：主管休假时把审批权临时交给他人。"""
    __tablename__ = "approval_delegations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    delegator_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    delegate_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True, nullable=False)
    start_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    # NULL = 全部业务类型
    business_types: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    def __repr__(self) -> str:
        return f"<ApprovalDelegationModel(id={self.id}, delegator_id={self.delegator_id})>"


class AuditLogModel(Base):
    """审计日志模型。"""
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    input_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    output_data: Mapped[Optional[Dict[str, Any]]] = mapped_column(JSON, nullable=True)
    tool_calls: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    decision: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, index=True, nullable=False
    )

    def __repr__(self) -> str:
        return f"<AuditLogModel(id={self.id}, action={self.action})>"


class KnowledgeDocModel(Base):
    """知识库文档模型。"""
    __tablename__ = "knowledge_docs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    tags: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_uri: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now, nullable=False
    )

    def __repr__(self) -> str:
        return f"<KnowledgeDocModel(id={self.id}, title={self.title})>"