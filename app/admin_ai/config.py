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
    # 本地嵌入式持久化目录：Chroma 服务不可达时使用，无需独立部署
    CHROMA_PERSIST_PATH: str = "data/chroma"

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
        return self


@lru_cache(maxsize=1)
def get_config() -> Settings:
    """获取全局配置单例。"""
    return Settings()