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

    # ============ LLM 脱敏与合规（设计见 docs/architecture/LLM数据脱敏与合规设计.md）============
    # 是否启用「脱敏 + L4 拦截」。生产环境禁止关闭（见下方 fail-fast 校验）。
    LLM_REDACTION_ENABLED: bool = True
    # 是否记录 LLM 调用审计（只记脱敏类别与用量，不记原文）
    LLM_AUDIT_ENABLED: bool = True
    # 是否连金额一并占位化（合规要求更严时开启）
    REDACT_AMOUNT: bool = False
    # 不走外部 LLM 的业务类型（涉密：证明开具、用印/合同）
    LLM_EXCLUDED_BUSINESS_TYPES: list[str] = Field(
        default_factory=lambda: ["certificate", "seal"]
    )
    # 工号识别正则（留空则不识别）；示例："EMP\\d{4,}"
    LLM_EMPLOYEE_ID_PATTERN: str = ""

    CHROMA_HOST: str = "localhost"
    CHROMA_PORT: int = 8005
    # 本地嵌入式持久化目录：Chroma 服务不可达时使用，无需独立部署
    CHROMA_PERSIST_PATH: str = "data/chroma"

    # ============ 组织架构与审批路由（设计见 docs/architecture/组织架构与审批路由设计.md）============
    # 组织数据来源：csv（HR 导出文件导入，默认）/ http（HR 组织接口）/ disabled
    ORG_SYNC_PROVIDER: str = "csv"
    ORG_SYNC_CSV_DIR: str = "data/org"
    HR_ORG_BASE_URL: str = ""
    HR_ORG_TOKEN: str = ""
    ORG_SYNC_TIMEOUT_SECONDS: float = 10.0
    # 必须走审批链的业务类型：落在其中的业务若一条规则都没配 → 转人工指派并告警（不静默完成）。
    # ⚠️ 增删此项等于改变业务的审批要求，需与行政/财务确认；规则本身用
    # scripts/manage_approval_rules.py 或 /admin/approval-rules 维护。
    APPROVAL_REQUIRED_BUSINESS_TYPES: list[str] = Field(
        default_factory=lambda: ["expense", "seal", "leave", "material", "asset", "travel"]
    )

    OA_SERVICE_URL: str = "http://localhost:8001"
    FINANCE_SERVICE_URL: str = "http://localhost:8002"
    MATERIAL_SERVICE_URL: str = "http://localhost:8003"

    SSO_ENABLED: bool = False
    SSO_URL: str = ""

    FEISHU_APP_ID: str = ""
    FEISHU_APP_SECRET: str = ""
    FEISHU_REDIRECT_URI: str = ""

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
            if not self.FEISHU_APP_ID:
                raise ValueError("生产环境必须配置 FEISHU_APP_ID")
            if not self.FEISHU_APP_SECRET:
                raise ValueError("生产环境必须配置 FEISHU_APP_SECRET")
            if not self.FEISHU_REDIRECT_URI:
                raise ValueError("生产环境必须配置 FEISHU_REDIRECT_URI")
            if not self.LLM_REDACTION_ENABLED:
                raise ValueError(
                    "生产环境必须启用 LLM_REDACTION_ENABLED（关闭将导致 L3 数据未经脱敏发往外部 LLM）"
                )
            if self.DEBUG:
                raise ValueError(
                    "生产环境必须关闭 DEBUG（SQL echo 会把含业务数据的 SQL 打进日志，"
                    "绕过脱敏层的保护范围）"
                )
        return self


@lru_cache(maxsize=1)
def get_config() -> Settings:
    """获取全局配置单例。"""
    return Settings()