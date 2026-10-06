# Admin AI Agent - 项目骨架实施计划

> **历史归档（2026-10-06 整理）**：保留原始方案、评审和交接记录供追溯。文中的机器路径、服务运行状态、测试结果、预算与进度只代表记录当时；提交号来自历史重写前，可能无法在当前仓库解析。后续开发请以 [文档导航](../../README.md)、[当前状态](../../guides/当前状态.md) 和 [开发计划](../../planning/开发计划.md) 为准。

> **For agentic workers:** 使用 writing-plans skill 生成。按 Task 顺序执行，每个 Task 独立可测。

**Goal:** 搭建 FastAPI 项目骨架，实现最小可运行的 API 服务，包含数据库、认证、对话、任务、知识库、管理后台完整路由与核心模块。

**Architecture:** 分层架构 `api → services → core → db`，FastAPI + SQLAlchemy 2.0 (async) + Redis + ChromaDB。统一响应信封 `{code, message, data}`，全局异常处理器，structlog 结构化日志。

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.0, Pydantic v2, structlog, uv

## Global Constraints

- 主包: `app/admin_ai/`，导入: `from app.admin_ai.xxx import yyy`
- 迁移目录: `migrations/`（仓库根）
- 测试目录: `tests/admin_ai/`（与主包同构）
- 行宽 100，4 空格缩进，双引号，Ruff format
- 所有函数必须类型注解，Google 风格 docstring
- 禁止 `metadata` 列名，用 `meta`
- 主键 UUID `String(36)`，时间存 UTC
- 统一响应信封 `{code: 0, message: "success", data: {...}}`
- 版本统一 `0.1.0`

---

### Task 1: 项目基础结构与配置

**Files:**
- Create: `app/__init__.py`
- Create: `app/admin_ai/__init__.py`
- Create: `app/admin_ai/config.py`
- Create: `app/admin_ai/utils/__init__.py`
- Create: `app/admin_ai/utils/logger.py`
- Create: `app/admin_ai/utils/exceptions.py`

- [ ] **Step 1: 创建包结构**

```python
# app/__init__.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""根包。"""
```

```python
# app/admin_ai/__init__.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""企业行政智能系统主包。"""

__version__ = "0.1.0"
```

- [ ] **Step 2: 创建配置模块**

```python
# app/admin_ai/config.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""应用配置模块。

集中管理环境变量与运行期配置，提供模块级单例 get_config()。
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_SECRET_KEY = "your-random-secret-key-change-in-production"
MIN_SECRET_KEY_LENGTH = 32


class Environment(str, Enum):
    """运行环境枚举。"""

    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class Settings(BaseSettings):
    """应用配置。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=True,
    )

    APP_NAME: str = "企业行政智能系统"
    APP_VERSION: str = "0.1.0"
    ENVIRONMENT: Environment = Environment.DEVELOPMENT
    DEBUG: bool = False
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])

    DATABASE_URL: str = "postgresql+asyncpg://postgres:password@localhost:5432/admin_ai"
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    OPENAI_API_KEY: str = ""
    OPENAI_BASE_URL: str = "https://api.openai.com/v1"
    LLM_MODEL: str = "gpt-4o-mini"
    LLM_TEMPERATURE: float = 0.0

    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8005

    OA_SERVICE_URL: str = "http://localhost:8001"
    FINANCE_SERVICE_URL: str = "http://localhost:8002"
    MATERIAL_SERVICE_URL: str = "http://localhost:8003"

    SSO_ENABLED: bool = False
    SSO_URL: str = ""

    SECRET_KEY: str = DEFAULT_SECRET_KEY
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    RATE_LIMIT_DEFAULT: str = "100/minute"
    LOG_LEVEL: str = "INFO"

    @model_validator(mode="after")
    def _check_secrets(self) -> Settings:
        """生产环境校验密钥配置。"""
        if self.ENVIRONMENT is Environment.PRODUCTION:
            if self.SECRET_KEY == DEFAULT_SECRET_KEY or len(self.SECRET_KEY) < MIN_SECRET_KEY_LENGTH:
                raise ValueError("生产环境必须配置长度 >=32 的非默认 SECRET_KEY")
            if not self.OPENAI_API_KEY:
                raise ValueError("生产环境必须配置 OPENAI_API_KEY")
            if "*" in self.CORS_ORIGINS:
                raise ValueError("生产环境禁止 CORS_ORIGINS 包含通配符 *")
        return self


@lru_cache(maxsize=1)
def get_config() -> Settings:
    """获取全局配置单例。"""
    return Settings()
```

- [ ] **Step 3: 创建日志模块**

```python
# app/admin_ai/utils/logger.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""结构化日志配置。"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog


def configure_logging(level: str = "INFO") -> None:
    """初始化 structlog 与标准库 logging。"""
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=level)
    shared_processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    structlog.configure(
        processors=[*shared_processors, structlog.processors.JSONRenderer(ensure_ascii=False)],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
```

- [ ] **Step 4: 创建异常体系**

```python
# app/admin_ai/utils/exceptions.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""应用异常层级。"""

from __future__ import annotations


class AppError(Exception):
    """应用基础异常。"""


class UserNotFoundError(AppError):
    """用户不存在。"""


class ToolExecutionError(AppError):
    """工具执行失败。"""


class ExternalSystemError(AppError):
    """外部系统调用失败。"""


class AuthenticationError(AppError):
    """认证失败。"""


class AuthorizationError(AppError):
    """权限不足。"""


class ValidationError(AppError):
    """数据校验失败。"""


class NotFoundError(AppError):
    """资源不存在。"""
```

- [ ] **Step 5: 创建 utils __init__**

```python
# app/admin_ai/utils/__init__.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""工具函数包。"""
```

- [ ] **Step 6: 验证配置可加载**

Run: `python -c "from app.admin_ai.config import get_config; c = get_config(); print(c.APP_VERSION)"`

Expected: `0.1.0`

- [ ] **Step 7: Commit**

```bash
git add app/
git commit -m "feat(config): 添加项目基础结构与配置模块"
```

---

### Task 2: 数据库层

**Files:**
- Create: `app/admin_ai/db/__init__.py`
- Create: `app/admin_ai/db/database.py`
- Create: `app/admin_ai/db/models.py`
- Create: `app/admin_ai/db/schemas.py`
- Create: `app/admin_ai/db/redis.py`

- [ ] **Step 1: 创建数据库连接**

```python
# app/admin_ai/db/__init__.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""数据库包。"""
```

```python
# app/admin_ai/db/database.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""数据库引擎与会话管理。"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.admin_ai.config import get_config


class Base(DeclarativeBase):
    """所有 ORM 模型的基类。"""
    pass


_engine = None
_session_factory = None


def get_engine():
    """获取或创建异步引擎。"""
    global _engine
    if _engine is None:
        config = get_config()
        _engine = create_async_engine(config.DATABASE_URL, pool_pre_ping=True, echo=config.DEBUG)
    return _engine


def get_session_factory():
    """获取或创建会话工厂。"""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI 依赖：获取数据库会话。"""
    factory = get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

- [ ] **Step 2: 创建数据模型**

```python
# app/admin_ai/db/models.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""SQLAlchemy 数据模型。"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.admin_ai.db.database import Base


def generate_uuid() -> str:
    """生成 UUID 字符串。"""
    return str(uuid.uuid4())


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


class UserModel(Base):
    """用户模型。"""
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    employee_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[Optional[str]] = mapped_column(String(100), index=True, nullable=True)
    position: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    role: Mapped[str] = mapped_column(String(50), default="employee", nullable=False)
    permissions: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    conversations: Mapped[list[ConversationModel]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    tasks: Mapped[list[TaskModel]] = relationship(
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
        SAEnum(ConversationStatus), default=ConversationStatus.ACTIVE, nullable=False
    )
    intent: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    business_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    context: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    user: Mapped[UserModel] = relationship(back_populates="conversations")
    messages: Mapped[list[MessageModel]] = relationship(
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
    role: Mapped[MessageRole] = mapped_column(SAEnum(MessageRole), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    meta: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)

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
    type: Mapped[TaskType] = mapped_column(SAEnum(TaskType), nullable=False)
    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus), default=TaskStatus.PENDING, nullable=False
    )
    title: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    external_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    approver_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    risk_level: Mapped[str] = mapped_column(String(20), default="low", nullable=False)
    requires_confirmation: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    user: Mapped[UserModel] = relationship(back_populates="tasks", foreign_keys=[user_id])
    approver: Mapped[Optional[UserModel]] = relationship(foreign_keys=[approver_id])
    approvals: Mapped[list[ApprovalModel]] = relationship(
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
    action: Mapped[Optional[ApprovalAction]] = mapped_column(SAEnum(ApprovalAction), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending", nullable=False)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    add_sign_user_id: Mapped[Optional[str]] = mapped_column(ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    task: Mapped[TaskModel] = relationship(back_populates="approvals")

    def __repr__(self) -> str:
        return f"<ApprovalModel(id={self.id}, task_id={self.task_id}, status={self.status})>"


class AuditLogModel(Base):
    """审计日志模型。"""
    __tablename__ = "audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    user_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    conversation_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    resource_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resource_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    input_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    output_data: Mapped[Optional[dict[str, Any]]] = mapped_column(JSON, nullable=True)
    tool_calls: Mapped[Optional[list[dict[str, Any]]]] = mapped_column(JSON, nullable=True)
    decision: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    decision_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, index=True, nullable=False
    )

    def __repr__(self) -> str:
        return f"<AuditLogModel(id={self.id}, action={self.action})>"


class KnowledgeDocModel(Base):
    """知识库文档模型。"""
    __tablename__ = "knowledge_docs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=generate_uuid)
    title: Mapped[str] = mapped_column(String(300), nullable=False)
    category: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    tags: Mapped[Optional[list[str]]] = mapped_column(JSON, nullable=True)
    source_uri: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedding_model: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_by: Mapped[Optional[str]] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return f"<KnowledgeDocModel(id={self.id}, title={self.title})>"
```

- [ ] **Step 3: 创建 Pydantic Schema**

```python
# app/admin_ai/db/schemas.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""Pydantic Schema 定义。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

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
    data: Optional[dict[str, Any]] = Field(None, description="业务数据")


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
    tasks: list[TaskResponse]
    total: int
    page: int = 1
    page_size: int = 20
    pending_count: int = 0
    approving_count: int = 0
```

- [ ] **Step 4: 创建 Redis 连接**

```python
# app/admin_ai/db/redis.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""Redis 连接管理。"""

from __future__ import annotations

from typing import Optional

import redis.asyncio as aioredis

from app.admin_ai.config import get_config

_redis_client: Optional[aioredis.Redis] = None


async def get_redis() -> aioredis.Redis:
    """获取 Redis 客户端单例。"""
    global _redis_client
    if _redis_client is None:
        config = get_config()
        _redis_client = aioredis.from_url(config.REDIS_URL, decode_responses=True)
    return _redis_client


async def close_redis() -> None:
    """关闭 Redis 连接。"""
    global _redis_client
    if _redis_client is not None:
        await _redis_client.close()
        _redis_client = None
```

- [ ] **Step 5: 验证模型可导入**

Run: `python -c "from app.admin_ai.db.models import UserModel, TaskModel; print('OK')"`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add app/admin_ai/db/
git commit -m "feat(db): 添加数据模型与数据库连接层"
```

---

### Task 3: API 层 - 统一响应与路由

**Files:**
- Create: `app/admin_ai/api/__init__.py`
- Create: `app/admin_ai/api/response.py`
- Create: `app/admin_ai/api/deps_context.py`
- Create: `app/admin_ai/api/schemas.py`
- Create: `app/admin_ai/api/routes.py`

- [ ] **Step 1: 创建统一响应信封**

```python
# app/admin_ai/api/__init__.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""API 路由包。"""
```

```python
# app/admin_ai/api/response.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""统一响应信封与全局异常处理器。"""

from __future__ import annotations

from typing import Any, Generic, Optional, TypeVar

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

T = TypeVar("T")


class ApiResponse(BaseModel, Generic[T]):
    """统一成功响应。"""
    code: int = 0
    message: str = "success"
    data: Optional[T] = None


class ErrorResponse(BaseModel):
    """统一错误响应。"""
    code: int
    message: str
    details: Optional[dict[str, Any]] = None


class BusinessError(Exception):
    """业务异常，携带统一错误码。"""

    def __init__(self, code: int, message: str, details: Optional[dict[str, Any]] = None) -> None:
        self.code = code
        self.message = message
        self.details = details
        super().__init__(message)


ERROR_TO_HTTP: dict[int, int] = {
    40001: 400,
    40002: 401,
    40003: 403,
    40004: 404,
    40005: 429,
    50001: 500,
    50002: 502,
    50003: 503,
}


def register_exception_handlers(app: FastAPI) -> None:
    """注册全局异常处理器。"""

    @app.exception_handler(BusinessError)
    async def handle_business_error(request: Request, exc: BusinessError) -> JSONResponse:
        body = ErrorResponse(code=exc.code, message=exc.message, details=exc.details)
        return JSONResponse(
            status_code=ERROR_TO_HTTP.get(exc.code, 400), content=body.model_dump()
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        body = ErrorResponse(code=40001, message="参数错误", details={"errors": exc.errors()})
        return JSONResponse(status_code=400, content=body.model_dump())

    @app.exception_handler(Exception)
    async def handle_unexpected(request: Request, exc: Exception) -> JSONResponse:
        body = ErrorResponse(code=50001, message="内部错误")
        return JSONResponse(status_code=500, content=body.model_dump())
```

- [ ] **Step 2: 创建依赖注入上下文**

```python
# app/admin_ai/api/deps_context.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""依赖注入上下文。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.admin_ai.db.database import get_db_session


@dataclass
class APIContext:
    """API 请求上下文。"""
    db: AsyncSession
    user_id: Optional[str] = None
    employee_id: Optional[str] = None
    role: Optional[str] = None


async def get_api_context(db: AsyncSession = None) -> APIContext:
    """获取 API 上下文。"""
    return APIContext(db=db)
```

- [ ] **Step 3: 创建 API Schema**

```python
# app/admin_ai/api/schemas.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""API 请求/响应 Schema。"""

from __future__ import annotations

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


class KnowledgeSearchRequest(BaseModel):
    """知识搜索。"""
    query: str
    category: Optional[str] = None
    top_k: int = 5
```

- [ ] **Step 4: 创建路由汇总**

```python
# app/admin_ai/api/routes.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""路由汇总。"""

from __future__ import annotations

from fastapi import APIRouter

from app.admin_ai.api import auth, chat, task, knowledge, admin


def create_router() -> APIRouter:
    """创建并汇总所有路由。"""
    router = APIRouter(prefix="/api/v1")
    router.include_router(auth.router)
    router.include_router(chat.router)
    router.include_router(task.router)
    router.include_router(knowledge.router)
    router.include_router(admin.router)
    return router
```

- [ ] **Step 5: Commit**

```bash
git add app/admin_ai/api/
git commit -m "feat(api): 添加统一响应信封与路由框架"
```

---

### Task 4: API 路由实现

**Files:**
- Create: `app/admin_ai/api/auth.py`
- Create: `app/admin_ai/api/chat.py`
- Create: `app/admin_ai/api/task.py`
- Create: `app/admin_ai/api/knowledge.py`
- Create: `app/admin_ai/api/admin.py`
- Create: `app/admin_ai/api/websocket.py`

- [ ] **Step 1: 创建认证路由**

```python
# app/admin_ai/api/auth.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""认证接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.admin_ai.api.deps_context import APIContext, get_api_context
from app.admin_ai.api.response import ApiResponse
from app.admin_ai.api.schemas import LoginRequest, TokenResponse

router = APIRouter(prefix="/auth", tags=["认证"])


@router.post("/login", response_model=ApiResponse[TokenResponse])
async def login(
    payload: LoginRequest,
    context: APIContext = Depends(get_api_context),
) -> ApiResponse[TokenResponse]:
    """登录并签发 JWT。"""
    return ApiResponse(data=TokenResponse(
        access_token="demo-token",
        token_type="bearer",
        expires_in=3600,
    ))


@router.post("/refresh", response_model=ApiResponse[TokenResponse])
async def refresh_token() -> ApiResponse[TokenResponse]:
    """刷新访问令牌。"""
    return ApiResponse(data=TokenResponse(
        access_token="refreshed-token",
        token_type="bearer",
        expires_in=3600,
    ))


@router.get("/me", response_model=ApiResponse[dict])
async def get_me() -> ApiResponse[dict]:
    """获取当前登录用户信息。"""
    return ApiResponse(data={"user_id": "demo", "role": "employee"})
```

- [ ] **Step 2: 创建对话路由**

```python
# app/admin_ai/api/chat.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""对话接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from app.admin_ai.api.response import ApiResponse
from app.admin_ai.api.schemas import ChatRequest, ChatResponse, ConfirmRequest, TransferRequest

router = APIRouter(prefix="/chat", tags=["对话"])


@router.post("/send", response_model=ApiResponse[ChatResponse])
async def send_message(payload: ChatRequest) -> ApiResponse[ChatResponse]:
    """发送消息，创建或继续会话。"""
    return ApiResponse(data=ChatResponse(
        conversation_id="conv_demo",
        message_id="msg_demo",
        content="你好，我是行政助手，请问有什么可以帮您？",
    ))


@router.get("/history/{conversation_id}", response_model=ApiResponse[dict])
async def get_conversation_history(conversation_id: str) -> ApiResponse[dict]:
    """获取会话历史。"""
    return ApiResponse(data={"conversation_id": conversation_id, "messages": [], "total": 0})


@router.post("/confirm/{task_id}", response_model=ApiResponse[ChatResponse])
async def confirm_action(task_id: str, payload: ConfirmRequest) -> ApiResponse[ChatResponse]:
    """确认或取消高风险操作。"""
    return ApiResponse(data=ChatResponse(
        conversation_id="conv_demo",
        message_id="msg_demo",
        content="操作已确认" if payload.confirmed else "操作已取消",
    ))


@router.post("/transfer/{conversation_id}", response_model=ApiResponse[ChatResponse])
async def transfer_to_human(
    conversation_id: str, payload: TransferRequest
) -> ApiResponse[ChatResponse]:
    """转人工。"""
    return ApiResponse(data=ChatResponse(
        conversation_id=conversation_id,
        message_id="msg_demo",
        content="已为您转接人工客服，请稍候。",
    ))
```

- [ ] **Step 3: 创建任务路由**

```python
# app/admin_ai/api/task.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""任务/待办接口。"""

from __future__ import annotations

from typing import Any, Optional

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
        "tasks": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
        "pending_count": 0,
        "approving_count": 0,
    })


@router.get("/pending-approval", response_model=ApiResponse[dict])
async def get_pending_approval_tasks(
    page: int = 1, page_size: int = 20
) -> ApiResponse[dict]:
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
```

- [ ] **Step 4: 创建知识库路由**

```python
# app/admin_ai/api/knowledge.py
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
```

- [ ] **Step 5: 创建管理后台路由**

```python
# app/admin_ai/api/admin.py
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
        "today_conversations": 0,
        "today_tasks": 0,
        "transfer_rate": 0.0,
        "top_intents": [],
    })


@router.get("/audit-logs", response_model=ApiResponse[dict])
async def get_audit_logs(
    user_id: Optional[str] = None,
    action: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
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
        "llm_calls": 0,
        "token_cost": 0.0,
        "avg_response_time": 0.0,
        "completion_rate": 0.0,
        "transfer_rate": 0.0,
    })
```

- [ ] **Step 6: 创建 WebSocket 路由**

```python
# app/admin_ai/api/websocket.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""WebSocket 实时对话。"""

from __future__ import annotations

import json

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["WebSocket"])


@router.websocket("/api/v1/chat/ws")
async def websocket_chat(websocket: WebSocket) -> None:
    """WebSocket 实时对话。"""
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "message")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
            elif msg_type == "message":
                content = data.get("content", "")
                await websocket.send_json({
                    "type": "reply",
                    "content": f"收到: {content}",
                    "conversation_id": data.get("conversation_id", "conv_ws"),
                })
    except WebSocketDisconnect:
        pass
```

- [ ] **Step 7: Commit**

```bash
git add app/admin_ai/api/
git commit -m "feat(api): 实现全部 API 路由（认证/对话/任务/知识库/管理/WebSocket）"
```

---

### Task 5: FastAPI 应用入口与中间件

**Files:**
- Create: `app/admin_ai/main.py`
- Create: `app/admin_ai/middleware/__init__.py`
- Create: `app/admin_ai/middleware/audit.py`
- Create: `app/admin_ai/middleware/logging.py`

- [ ] **Step 1: 创建 FastAPI 入口**

```python
# app/admin_ai/main.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""FastAPI 应用入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.admin_ai.api.response import register_exception_handlers
from app.admin_ai.api.routes import create_router
from app.admin_ai.config import get_config
from app.admin_ai.utils.logger import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    config = get_config()
    configure_logging(config.LOG_LEVEL)
    yield


def create_app() -> FastAPI:
    """创建 FastAPI 应用实例。"""
    config = get_config()

    app = FastAPI(
        title=config.APP_NAME,
        version=config.APP_VERSION,
        docs_url="/docs" if config.DEBUG else None,
        redoc_url="/redoc" if config.DEBUG else None,
        lifespan=lifespan,
    )

    # CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # 异常处理器
    register_exception_handlers(app)

    # 路由
    router = create_router()
    app.include_router(router)

    # 健康检查
    @app.get("/api/health")
    async def health():
        return {"status": "healthy", "version": config.APP_VERSION}

    return app


app = create_app()
```

- [ ] **Step 2: 创建中间件**

```python
# app/admin_ai/middleware/__init__.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""中间件包。"""
```

```python
# app/admin_ai/middleware/audit.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""审计中间件。"""

from __future__ import annotations

from typing import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = structlog.get_logger(__name__)


class AuditMiddleware(BaseHTTPMiddleware):
    """审计中间件：记录所有请求。"""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        logger.info(
            "请求完成",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        )
        return response
```

```python
# app/admin_ai/middleware/logging.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""日志中间件。"""

from __future__ import annotations

import uuid
from typing import Awaitable, Callable

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

TRACE_HEADER = "X-Request-Id"


class TraceIdMiddleware(BaseHTTPMiddleware):
    """trace id 注入中间件。"""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        trace_id = request.headers.get(TRACE_HEADER) or str(uuid.uuid4())
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(trace_id=trace_id)
        response = await call_next(request)
        response.headers[TRACE_HEADER] = trace_id
        return response
```

- [ ] **Step 3: 验证应用可启动**

Run: `python -c "from app.admin_ai.main import app; print(app.title, app.version)"`

Expected: `企业行政智能系统 0.1.0`

- [ ] **Step 4: Commit**

```bash
git add app/admin_ai/main.py app/admin_ai/middleware/
git commit -m "feat(app): 添加 FastAPI 入口与中间件"
```

---

### Task 6: 核心模块 - 智能体

**Files:**
- Create: `app/admin_ai/core/__init__.py`
- Create: `app/admin_ai/core/agent/__init__.py`
- Create: `app/admin_ai/core/agent/orchestrator.py`
- Create: `app/admin_ai/core/agent/intent.py`
- Create: `app/admin_ai/core/agent/slot.py`
- Create: `app/admin_ai/core/agent/dialog.py`
- Create: `app/admin_ai/core/agent/prompt.py`

- [ ] **Step 1: 创建核心包 __init__**

```python
# app/admin_ai/core/__init__.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""核心业务逻辑包。"""
```

```python
# app/admin_ai/core/agent/__init__.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""智能体模块。"""
```

- [ ] **Step 2: 创建 Prompt 模板**

```python
# app/admin_ai/core/agent/prompt.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""Prompt 模板管理。"""

from __future__ import annotations

INTENT_PROMPT = """你是一个企业行政助手的意图识别模块。

根据用户的输入，识别用户的意图和业务类型。

## 支持的意图
- policy_query: 制度/规则/流程/FAQ 查询
- meeting_room_booking: 会议室/车辆预定
- status_query: 状态查询
- material_request: 物资领用
- leave_request: 请假申请
- certificate_request: 证明开具
- expense_request: 报销申请
- travel_request: 差旅申请/订票
- asset_request: 固定资产领用/归还
- seal_request: 用印/盖章/合同
- onboarding_request: 入离职办理
- greeting: 问候
- other: 其他

请以 JSON 格式返回：
{"intent": "<意图标签>", "business_type": "<业务类型>", "confidence": <置信度>}
"""

SLOT_PROMPT = """你是一个企业行政助手的槽位抽取模块。

根据用户输入和意图，抽取业务所需的字段。

{slot_schema}

请以 JSON 格式返回抽取到的字段：
{"slots": {字段名: 字段值}, "missing": [缺失字段列表]}
"""

REPLY_PROMPT = """你是一个企业行政智能助手。请根据以下信息回复用户：

意图: {intent}
业务数据: {slots}
RAG 参考: {rag_results}

请用简洁友好的中文回复。
"""
```

- [ ] **Step 3: 创建意图识别**

```python
# app/admin_ai/core/agent/intent.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""意图识别模块。"""

from __future__ import annotations

import json
from typing import Any, Optional

import structlog

from app.admin_ai.core.agent.prompt import INTENT_PROMPT

logger = structlog.get_logger(__name__)

VALID_INTENTS = {
    "policy_query", "meeting_room_booking", "status_query",
    "material_request", "leave_request", "certificate_request",
    "expense_request", "travel_request", "asset_request",
    "seal_request", "onboarding_request", "greeting", "other",
}


class IntentRecognizer:
    """意图识别器。"""

    def __init__(self, llm_client: Any = None) -> None:
        self._llm = llm_client

    async def recognize(
        self,
        message: str,
        conversation_history: Optional[list[dict]] = None,
    ) -> dict[str, Any]:
        """识别用户意图。"""
        if self._llm is None:
            return self._fallback_recognize(message)

        try:
            response = await self._llm.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": INTENT_PROMPT},
                    {"role": "user", "content": message},
                ],
                temperature=0,
                response_format={"type": "json_object"},
            )
            result = json.loads(response.choices[0].message.content)
            intent = result.get("intent", "other")
            if intent not in VALID_INTENTS:
                intent = "other"
            result["intent"] = intent
            return result
        except Exception as e:
            logger.error("意图识别失败", error=str(e))
            return {"intent": "other", "confidence": 0.0}

    def _fallback_recognize(self, message: str) -> dict[str, Any]:
        """无 LLM 时的规则回退。"""
        keywords = {
            "请假": "leave_request",
            "报销": "expense_request",
            "会议室": "meeting_room_booking",
            "物资": "material_request",
            "证明": "certificate_request",
            "差旅": "travel_request",
            "资产": "asset_request",
            "盖章": "seal_request",
            "入职": "onboarding_request",
            "离职": "onboarding_request",
            "你好": "greeting",
        }
        for keyword, intent in keywords.items():
            if keyword in message:
                return {"intent": intent, "confidence": 0.7}
        return {"intent": "other", "confidence": 0.5}
```

- [ ] **Step 4: 创建槽位抽取**

```python
# app/admin_ai/core/agent/slot.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""槽位抽取模块。"""

from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)

SLOT_SCHEMAS = {
    "leave": ["leave_type", "start_date", "end_date"],
    "expense": ["expense_type", "amount", "invoice"],
    "travel": ["destination", "start_date", "end_date", "purpose"],
    "meeting_room": ["date", "start_time", "end_time", "capacity"],
    "vehicle": ["date", "start_time", "end_time", "destination"],
    "material": ["item_name", "quantity"],
    "asset": ["asset_name", "quantity", "action"],
    "seal": ["document_name", "seal_type", "copies"],
    "certificate": ["certificate_type", "purpose"],
    "onboarding": ["employee_name", "onboard_date", "action"],
}


class SlotExtractor:
    """槽位抽取器。"""

    def __init__(self, llm_client: Any = None) -> None:
        self._llm = llm_client

    async def extract(
        self,
        message: str,
        intent: str,
        business_type: Optional[str] = None,
        existing_slots: Optional[dict[str, Any]] = None,
        attachments: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """从消息中抽取槽位。"""
        existing = existing_slots or {}
        if self._llm is None:
            return self._fallback_extract(message, business_type, existing)
        return existing

    def _fallback_extract(
        self,
        message: str,
        business_type: Optional[str],
        existing: dict[str, Any],
    ) -> dict[str, Any]:
        """规则回退抽取。"""
        import re
        slots = dict(existing)

        date_match = re.findall(r"\d{4}-\d{2}-\d{2}", message)
        if date_match:
            if "start_date" not in slots:
                slots["start_date"] = date_match[0]
            if len(date_match) > 1 and "end_date" not in slots:
                slots["end_date"] = date_match[1]

        days_match = re.search(r"(\d+)\s*天", message)
        if days_match and "days" not in slots:
            slots["days"] = int(days_match.group(1))

        return slots

    def get_required_slots(self, business_type: str) -> list[str]:
        """获取业务类型所需的必填槽位。"""
        return SLOT_SCHEMAS.get(business_type, [])

    def check_completeness(self, business_type: str, slots: dict[str, Any]) -> list[str]:
        """检查槽位完整性，返回缺失列表。"""
        required = self.get_required_slots(business_type)
        return [s for s in required if s not in slots or slots[s] is None]
```

- [ ] **Step 5: 创建对话管理**

```python
# app/admin_ai/core/agent/dialog.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""多轮对话管理。"""

from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class DialogManager:
    """对话管理器。"""

    def __init__(self, redis_client: Any = None) -> None:
        self._redis = redis_client

    async def get_history(self, conversation_id: str) -> list[dict[str, Any]]:
        """获取对话历史。"""
        if self._redis is None:
            return []
        try:
            data = await self._redis.get(f"conversation:{conversation_id}")
            if data:
                import json
                return json.loads(data)
        except Exception as e:
            logger.warning("获取对话历史失败", error=str(e))
        return []

    async def save_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
    ) -> None:
        """保存消息到历史。"""
        if self._redis is None:
            return
        try:
            import json
            history = await self.get_history(conversation_id)
            history.append({"role": role, "content": content})
            await self._redis.set(
                f"conversation:{conversation_id}",
                json.dumps(history, ensure_ascii=False),
                ex=86400,
            )
        except Exception as e:
            logger.warning("保存消息失败", error=str(e))

    async def clear(self, conversation_id: str) -> None:
        """清空对话历史。"""
        if self._redis is None:
            return
        try:
            await self._redis.delete(f"conversation:{conversation_id}")
        except Exception as e:
            logger.warning("清空对话失败", error=str(e))
```

- [ ] **Step 6: 创建编排器**

```python
# app/admin_ai/core/agent/orchestrator.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""智能体编排器。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

import structlog

from app.admin_ai.core.agent.dialog import DialogManager
from app.admin_ai.core.agent.intent import IntentRecognizer
from app.admin_ai.core.agent.slot import SlotExtractor

logger = structlog.get_logger(__name__)


class AgentState(str, Enum):
    """智能体状态。"""
    IDLE = "idle"
    INTENT_RECOGNIZING = "intent_recognizing"
    SLOT_FILLING = "slot_filling"
    VALIDATING = "validating"
    EXECUTING = "executing"
    CONFIRMING = "confirming"
    COMPLETED = "completed"
    FAILED = "failed"
    TRANSFERRED = "transferred"


@dataclass
class AgentContext:
    """智能体上下文。"""
    user_id: str
    conversation_id: str
    state: AgentState = AgentState.IDLE
    intent: Optional[str] = None
    business_type: Optional[str] = None
    slots: dict[str, Any] = field(default_factory=dict)
    rag_results: list[dict] = field(default_factory=list)
    tool_calls: list[dict] = field(default_factory=list)
    risk_level: str = "low"
    confirmed: bool = False


class Orchestrator:
    """智能体编排器。"""

    def __init__(
        self,
        intent_recognizer: IntentRecognizer,
        slot_extractor: SlotExtractor,
        dialog_manager: DialogManager,
    ) -> None:
        self.intent_recognizer = intent_recognizer
        self.slot_extractor = slot_extractor
        self.dialog_manager = dialog_manager

    async def process(
        self,
        user_message: str,
        context: AgentContext,
        attachments: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """处理用户消息的主流程。"""
        try:
            # 1. 意图识别
            intent_result = await self.intent_recognizer.recognize(user_message)
            context.intent = intent_result["intent"]
            context.business_type = intent_result.get("business_type")

            # 2. 问候直接回复
            if context.intent == "greeting":
                return {"content": "你好，我是行政助手，请问有什么可以帮您？"}

            # 3. 制度查询走 RAG
            if context.intent == "policy_query":
                return {"content": "正在为您查询相关制度...", "needs_rag": True}

            # 4. 槽位抽取
            slots = await self.slot_extractor.extract(
                user_message, context.intent, context.business_type, context.slots, attachments
            )
            context.slots.update(slots)

            # 5. 检查完整性
            missing = self.slot_extractor.check_completeness(
                context.business_type or "", context.slots
            )
            if missing:
                questions = {
                    "leave_type": "请问您要请什么假？（年假/调休/事假/病假）",
                    "start_date": "请问开始日期是哪天？",
                    "end_date": "请问结束日期是哪天？",
                    "amount": "请问金额是多少？",
                    "destination": "请问目的地是哪里？",
                }
                return {
                    "content": questions.get(missing[0], f"请提供{missing[0]}信息"),
                    "requires_action": True,
                }

            # 6. 风险评估
            high_risk = ["expense", "seal"]
            if context.business_type in high_risk and not context.confirmed:
                return {
                    "content": "请确认以下操作",
                    "card_data": {
                        "type": "confirmation",
                        "data": context.slots,
                        "warning": "此操作将产生重要影响，请仔细核对",
                    },
                    "requires_action": True,
                }

            # 7. 执行
            return {
                "content": f"操作已完成：{context.business_type}",
                "task_id": "task_demo",
            }

        except Exception as e:
            logger.error("处理异常", error=str(e))
            return {"content": "抱歉，处理过程中出现错误，请稍后重试"}
```

- [ ] **Step 7: Commit**

```bash
git add app/admin_ai/core/agent/
git commit -m "feat(agent): 添加智能体核心模块（编排/意图/槽位/对话/Prompt）"
```

---

### Task 7: 核心模块 - RAG / Tools / Rules / Auth

**Files:**
- Create: `app/admin_ai/core/rag/__init__.py`
- Create: `app/admin_ai/core/rag/retriever.py`
- Create: `app/admin_ai/core/tools/__init__.py`
- Create: `app/admin_ai/core/tools/base.py`
- Create: `app/admin_ai/core/tools/registry.py`
- Create: `app/admin_ai/core/rules/__init__.py`
- Create: `app/admin_ai/core/rules/engine.py`
- Create: `app/admin_ai/core/auth/__init__.py`
- Create: `app/admin_ai/core/auth/deps.py`

- [ ] **Step 1: RAG 检索器**

```python
# app/admin_ai/core/rag/__init__.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""RAG 知识检索模块。"""
```

```python
# app/admin_ai/core/rag/retriever.py
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
```

- [ ] **Step 2: 工具基类与注册中心**

```python
# app/admin_ai/core/tools/__init__.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""工具调用层。"""
```

```python
# app/admin_ai/core/tools/base.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""工具基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """工具执行结果。"""
    content: list[dict] = field(default_factory=list)
    details: dict[str, Any] = field(default_factory=dict)
    is_error: bool = False

    @classmethod
    def text(cls, text: str, details: Optional[dict] = None) -> ToolResult:
        """构造文本结果。"""
        return cls(content=[{"type": "text", "text": text}], details=details or {})

    @classmethod
    def error(cls, message: str, details: Optional[dict] = None) -> ToolResult:
        """构造错误结果。"""
        return cls(
            content=[{"type": "text", "text": message}],
            details=details or {},
            is_error=True,
        )


class BaseTool(ABC):
    """工具基类。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称。"""

    @property
    @abstractmethod
    def description(self) -> str:
        """工具描述。"""

    @abstractmethod
    async def execute(self, params: dict[str, Any], user_id: str) -> ToolResult:
        """执行工具。"""
```

```python
# app/admin_ai/core/tools/registry.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""工具注册中心。"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from app.admin_ai.core.tools.base import BaseTool

logger = structlog.get_logger(__name__)


class ToolRegistry:
    """工具注册中心。"""

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    def register(self, tool: BaseTool) -> None:
        """注册工具。"""
        self._tools[tool.name] = tool
        logger.info("工具已注册", tool_name=tool.name)

    def get_tool(self, name: str) -> Optional[BaseTool]:
        """获取工具。"""
        return self._tools.get(name)

    def list_tools(self) -> list[dict[str, str]]:
        """列出所有工具。"""
        return [{"name": t.name, "description": t.description} for t in self._tools.values()]
```

- [ ] **Step 3: 规则引擎**

```python
# app/admin_ai/core/rules/__init__.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""规则引擎模块。"""
```

```python
# app/admin_ai/core/rules/engine.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""规则引擎。"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ValidationResult:
    """校验结果。"""
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class RuleEngine:
    """规则引擎。"""

    def __init__(self, user_service: Any = None, config_service: Any = None) -> None:
        self._user_service = user_service
        self._config_service = config_service

    async def validate(
        self,
        business_type: str,
        slots: dict[str, Any],
        user_id: str,
    ) -> ValidationResult:
        """校验业务规则。"""
        result = ValidationResult()

        if business_type == "leave":
            await self._validate_leave(slots, user_id, result)
        elif business_type == "expense":
            await self._validate_expense(slots, user_id, result)

        return result

    async def _validate_leave(
        self, slots: dict[str, Any], user_id: str, result: ValidationResult
    ) -> None:
        """校验请假规则。"""
        pass

    async def _validate_expense(
        self, slots: dict[str, Any], user_id: str, result: ValidationResult
    ) -> None:
        """校验报销规则。"""
        pass
```

- [ ] **Step 4: 认证依赖**

```python
# app/admin_ai/core/auth/__init__.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""认证鉴权模块。"""
```

```python
# app/admin_ai/core/auth/deps.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""认证依赖。"""

from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, Header

from app.admin_ai.api.response import BusinessError


async def get_current_user(authorization: Optional[str] = Header(None)) -> dict[str, Any]:
    """解析并校验 JWT，返回当前用户。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise BusinessError(code=40002, message="未授权")
    token = authorization.removeprefix("Bearer ").strip()
    return {"user_id": "user_001", "employee_id": "EMP1001", "role": "employee"}


async def get_admin_user(
    current_user: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """校验管理员角色。"""
    if current_user.get("role") != "admin":
        raise BusinessError(code=40003, message="无权限")
    return current_user
```

- [ ] **Step 5: Commit**

```bash
git add app/admin_ai/core/
git commit -m "feat(core): 添加 RAG/工具/规则/认证核心模块"
```

---

### Task 8: 服务层

**Files:**
- Create: `app/admin_ai/services/__init__.py`
- Create: `app/admin_ai/services/chat_service.py`
- Create: `app/admin_ai/services/task_service.py`
- Create: `app/admin_ai/services/knowledge_service.py`
- Create: `app/admin_ai/services/notification_service.py`

- [ ] **Step 1: 创建服务层**

```python
# app/admin_ai/services/__init__.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""服务层。"""
```

```python
# app/admin_ai/services/chat_service.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""对话服务。"""

from __future__ import annotations

from typing import Any, Optional

import structlog

from app.admin_ai.core.agent.dialog import DialogManager
from app.admin_ai.core.agent.intent import IntentRecognizer
from app.admin_ai.core.agent.orchestrator import AgentContext, AgentState, Orchestrator
from app.admin_ai.core.agent.slot import SlotExtractor

logger = structlog.get_logger(__name__)


class ChatService:
    """对话服务。"""

    def __init__(
        self,
        orchestrator: Orchestrator,
        dialog_manager: DialogManager,
    ) -> None:
        self.orchestrator = orchestrator
        self.dialog_manager = dialog_manager

    async def send_message(
        self,
        user_id: str,
        message: str,
        conversation_id: Optional[str] = None,
        attachments: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """发送消息。"""
        if not conversation_id:
            import uuid
            conversation_id = str(uuid.uuid4())

        context = AgentContext(
            user_id=user_id,
            conversation_id=conversation_id,
        )

        result = await self.orchestrator.process(message, context, attachments)

        await self.dialog_manager.save_message(conversation_id, "user", message)
        await self.dialog_manager.save_message(
            conversation_id, "assistant", result.get("content", "")
        )

        return {
            "conversation_id": conversation_id,
            "message_id": str(uuid.uuid4()),
            "content": result.get("content", ""),
            "content_type": "card" if result.get("card_data") else "text",
            "card_data": result.get("card_data"),
            "suggestions": result.get("suggestions"),
            "requires_action": result.get("requires_action", False),
            "tool_calls": result.get("tool_calls", []),
        }
```

```python
# app/admin_ai/services/task_service.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""任务服务。"""

from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class TaskService:
    """任务服务。"""

    async def get_my_tasks(
        self,
        user_id: str,
        status: Optional[str] = None,
        task_type: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """获取我的任务列表。"""
        return {"tasks": [], "total": 0, "page": page, "page_size": page_size}

    async def get_task_detail(self, task_id: str, user_id: str) -> dict[str, Any]:
        """获取任务详情。"""
        return {"id": task_id}

    async def approve_task(
        self, task_id: str, user_id: str, action: str, comment: Optional[str] = None
    ) -> dict[str, Any]:
        """审批任务。"""
        return {"id": task_id, "action": action, "status": "completed"}

    async def cancel_task(self, task_id: str, user_id: str, reason: Optional[str] = None) -> dict[str, Any]:
        """取消任务。"""
        return {"id": task_id, "status": "cancelled"}
```

```python
# app/admin_ai/services/knowledge_service.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""知识库服务。"""

from __future__ import annotations

from typing import Any, Optional

import structlog

logger = structlog.get_logger(__name__)


class KnowledgeService:
    """知识库服务。"""

    async def upload_document(
        self,
        title: str,
        category: str,
        content: Optional[str] = None,
        tags: Optional[list[str]] = None,
    ) -> dict[str, Any]:
        """上传知识文档。"""
        return {"id": "doc_demo", "title": title, "status": "indexed"}

    async def search(self, query: str, category: Optional[str] = None, top_k: int = 5) -> dict[str, Any]:
        """搜索知识库。"""
        return {"query": query, "results": [], "total": 0}

    async def list_documents(
        self, category: Optional[str] = None, page: int = 1, page_size: int = 20
    ) -> dict[str, Any]:
        """列出文档。"""
        return {"documents": [], "total": 0, "page": page, "page_size": page_size}

    async def delete_document(self, doc_id: str) -> dict[str, Any]:
        """删除文档。"""
        return {"id": doc_id, "status": "deleted"}
```

```python
# app/admin_ai/services/notification_service.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""通知服务。"""

from __future__ import annotations

import structlog

logger = structlog.get_logger(__name__)


class NotificationService:
    """通知服务。"""

    async def send_notification(self, user_id: str, title: str, content: str) -> None:
        """发送通知。"""
        logger.info("发送通知", user_id=user_id, title=title)
```

- [ ] **Step 2: Commit**

```bash
git add app/admin_ai/services/
git commit -m "feat(services): 添加服务层（对话/任务/知识库/通知）"
```

---

### Task 9: Alembic 迁移配置

**Files:**
- Create: `alembic.ini`
- Create: `migrations/env.py`
- Create: `migrations/versions/.gitkeep`

- [ ] **Step 1: 创建 Alembic 配置**

```ini
# alembic.ini
[alembic]
script_location = migrations
prepend_sys_path = .
version_path_separator = os

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARNING
handlers = console
qualname =

[logger_sqlalchemy]
level = WARNING
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %H:%M:%S
```

- [ ] **Step 2: 创建迁移环境**

```python
# migrations/env.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""Alembic 迁移环境。"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig
from typing import Any

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from app.admin_ai.config import get_config
from app.admin_ai.db import models  # noqa: F401
from app.admin_ai.db.database import Base

config = context.config
config.set_main_option("sqlalchemy.url", get_config().DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def do_run_migrations(connection: Any) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    context.configure(
        url=get_config().DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
```

- [ ] **Step 3: 创建版本目录**

```bash
mkdir -p migrations/versions
touch migrations/versions/.gitkeep
```

- [ ] **Step 4: Commit**

```bash
git add alembic.ini migrations/
git commit -m "chore: 添加 Alembic 迁移配置"
```

---

### Task 10: 测试基础设施

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Create: `tests/admin_ai/__init__.py`
- Create: `tests/admin_ai/test_api/__init__.py`
- Create: `tests/admin_ai/test_core/__init__.py`
- Create: `tests/admin_ai/test_services/__init__.py`

- [ ] **Step 1: 创建测试目录结构**

```python
# tests/__init__.py
# -*- coding: utf-8 -*-
"""测试包。"""
```

```python
# tests/conftest.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""全局测试 fixtures。"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest


def pytest_configure(config) -> None:
    """注册自定义标记。"""
    markers = {
        "slow": "耗时较长的用例",
        "integration": "需要 PostgreSQL / Redis 等真实依赖的集成测试",
        "e2e": "跨模块端到端用例",
        "llm": "调用真实 LLM 的用例",
    }
    for name, description in markers.items():
        config.addinivalue_line("markers", f"{name}: {description}")


@pytest.fixture
def mock_llm() -> AsyncMock:
    """LLM 桩。"""
    mock = AsyncMock()

    def _completion(content: str) -> Any:
        message = type("Message", (), {"content": content})()
        choice = type("Choice", (), {"message": message})()
        return type("Completion", (), {"choices": [choice]})()

    async def _create(*args: Any, **kwargs: Any) -> Any:
        prompt = kwargs.get("messages", [{}])[-1].get("content", "")
        if "请假" in prompt:
            return _completion(
                '{"intent": "leave_request", "business_type": "leave", "confidence": 0.95}'
            )
        return _completion('{"intent": "policy_query", "confidence": 0.9}')

    mock.chat.completions.create.side_effect = _create
    return mock
```

```python
# tests/admin_ai/__init__.py
# -*- coding: utf-8 -*-
"""admin_ai 测试包。"""
```

```python
# tests/admin_ai/test_api/__init__.py
# -*- coding: utf-8 -*-
"""API 测试包。"""
```

```python
# tests/admin_ai/test_core/__init__.py
# -*- coding: utf-8 -*-
"""核心模块测试包。"""
```

```python
# tests/admin_ai/test_services/__init__.py
# -*- coding: utf-8 -*-
"""服务层测试包。"""
```

- [ ] **Step 2: Commit**

```bash
git add tests/
git commit -m "test: 添加测试基础设施与 fixtures"
```

---

### Task 11: 单元测试

**Files:**
- Create: `tests/admin_ai/test_core/test_intent.py`
- Create: `tests/admin_ai/test_core/test_slot.py`
- Create: `tests/admin_ai/test_api/test_health.py`

- [ ] **Step 1: 意图识别测试**

```python
# tests/admin_ai/test_core/test_intent.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""意图识别测试。"""

from __future__ import annotations

import pytest

from app.admin_ai.core.agent.intent import IntentRecognizer


class TestIntentRecognizer:
    """意图识别测试。"""

    @pytest.fixture
    def recognizer(self, mock_llm) -> IntentRecognizer:
        return IntentRecognizer(llm_client=mock_llm)

    async def test_recognize_leave_request(self, recognizer: IntentRecognizer) -> None:
        result = await recognizer.recognize("我想请两天年假")
        assert result["intent"] == "leave_request"
        assert result["confidence"] >= 0.8

    async def test_recognize_policy_query(self, recognizer: IntentRecognizer) -> None:
        result = await recognizer.recognize("年假有几天")
        assert result["intent"] == "policy_query"

    async def test_recognize_fallback_greeting(self) -> None:
        recognizer = IntentRecognizer(llm_client=None)
        result = await recognizer.recognize("你好")
        assert result["intent"] == "greeting"

    async def test_recognize_fallback_leave(self) -> None:
        recognizer = IntentRecognizer(llm_client=None)
        result = await recognizer.recognize("我想请假")
        assert result["intent"] == "leave_request"

    async def test_recognize_fallback_unknown(self) -> None:
        recognizer = IntentRecognizer(llm_client=None)
        result = await recognizer.recognize("今天天气怎么样")
        assert result["intent"] == "other"
```

- [ ] **Step 2: 槽位抽取测试**

```python
# tests/admin_ai/test_core/test_slot.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""槽位抽取测试。"""

from __future__ import annotations

import pytest

from app.admin_ai.core.agent.slot import SlotExtractor


class TestSlotExtractor:
    """槽位抽取测试。"""

    @pytest.fixture
    def extractor(self) -> SlotExtractor:
        return SlotExtractor(llm_client=None)

    async def test_extract_dates(self, extractor: SlotExtractor) -> None:
        result = await extractor.extract("2026-09-20 到 2026-09-21", "leave", "leave")
        assert result.get("start_date") == "2026-09-20"
        assert result.get("end_date") == "2026-09-21"

    async def test_extract_days(self, extractor: SlotExtractor) -> None:
        result = await extractor.extract("请两天假", "leave", "leave")
        assert result.get("days") == 2

    async def test_get_required_slots(self, extractor: SlotExtractor) -> None:
        slots = extractor.get_required_slots("leave")
        assert "leave_type" in slots
        assert "start_date" in slots
        assert "end_date" in slots

    async def test_check_completeness_missing(self, extractor: SlotExtractor) -> None:
        missing = extractor.check_completeness("leave", {"leave_type": "年假"})
        assert "start_date" in missing
        assert "end_date" in missing

    async def test_check_completeness_complete(self, extractor: SlotExtractor) -> None:
        missing = extractor.check_completeness("leave", {
            "leave_type": "年假", "start_date": "2026-09-20", "end_date": "2026-09-21"
        })
        assert len(missing) == 0
```

- [ ] **Step 3: 健康检查 API 测试**

```python
# tests/admin_ai/test_api/test_health.py
# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""健康检查测试。"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from app.admin_ai.main import create_app


class TestHealthAPI:
    """健康检查 API 测试。"""

    async def test_health_endpoint(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["version"] == "0.1.0"

    async def test_chat_send_endpoint(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post(
                "/api/v1/chat/send",
                json={"message": "你好"},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
        assert "conversation_id" in data["data"]

    async def test_tasks_my_endpoint(self) -> None:
        app = create_app()
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/v1/tasks/my")
        assert response.status_code == 200
        data = response.json()
        assert data["code"] == 0
```

- [ ] **Step 4: 运行测试**

Run: `pytest tests/ -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: 添加意图识别、槽位抽取、API 单元测试"
```

---

### Task 12: 配置文件与文档同步

**Files:**
- Update: `requirements.txt`
- Update: `requirements-dev.txt`
- Create: `scripts/__init__.py`
- Create: `.gitignore` (if not exists, verify)

- [ ] **Step 1: 验证 requirements 文件存在**

Run: `cat requirements.txt | head -5`

Expected: 看到 fastapi, uvicorn 等依赖

- [ ] **Step 2: 验证 .gitignore 包含必要条目**

```gitignore
# .gitignore
.env
.env.*
!.env.example
__pycache__/
*.pyc
.pytest_cache/
.mypy_cache/
.ruff_cache/
htmlcov/
coverage.xml
*.egg-info/
dist/
build/
.venv/
venv/
```

- [ ] **Step 3: 创建 scripts 目录**

```python
# scripts/__init__.py
# -*- coding: utf-8 -*-
"""运维脚本包。"""
```

- [ ] **Step 4: 最终验证**

Run: `python -c "from app.admin_ai.main import app; print('App created:', app.title)"`

Expected: `App created: 企业行政智能系统`

Run: `pytest tests/ -v --tb=short`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add .
git commit -m "chore: 同步配置文件与 .gitignore"
```

---

### Task 13: 推送到 Gitee

- [ ] **Step 1: 验证远程仓库**

Run: `git remote -v`

Expected: `origin https://gitee.com/qiulongfei4408/admin-ai-agent.git`

- [ ] **Step 2: 推送**

Run: `git push origin main`

- [ ] **Step 3: 验证推送成功**

访问 https://gitee.com/qiulongfei4408/admin-ai-agent 确认代码已更新。

---

## 实施计划总结

| Task | 内容 | 文件数 |
|------|------|--------|
| 1 | 项目基础结构与配置 | 6 |
| 2 | 数据库层 | 5 |
| 3 | API 层 - 统一响应与路由 | 5 |
| 4 | API 路由实现 | 6 |
| 5 | FastAPI 入口与中间件 | 4 |
| 6 | 核心模块 - 智能体 | 7 |
| 7 | 核心模块 - RAG/Tools/Rules/Auth | 8 |
| 8 | 服务层 | 5 |
| 9 | Alembic 迁移配置 | 3 |
| 10 | 测试基础设施 | 6 |
| 11 | 单元测试 | 3 |
| 12 | 配置文件与文档同步 | 2 |
| 13 | 推送到 Gitee | - |
| **合计** | | **~60 文件** |
