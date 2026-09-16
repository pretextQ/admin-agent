# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""FastAPI 应用入口。"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.admin_ai.api.response import register_exception_handlers
from app.admin_ai.api.routes import create_router
from app.admin_ai.config import get_config
from app.admin_ai.core.rules.engine import RuleEngine
from app.admin_ai.core.tools.registry import init_tools
from app.admin_ai.utils.logger import configure_logging

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理。"""
    config = get_config()
    configure_logging(config.LOG_LEVEL)

    # 初始化工具注册
    tool_registry = init_tools(config)
    app.state.tool_registry = tool_registry
    logger.info("工具注册完成", count=len(tool_registry.list_tools()))

    # 初始化规则引擎
    rule_engine = RuleEngine()
    app.state.rule_engine = rule_engine
    logger.info("规则引擎初始化完成")

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

    # WebSocket
    from app.admin_ai.api.websocket import router as ws_router
    app.include_router(ws_router)

    # 健康检查
    @app.get("/api/health")
    async def health():
        return {"status": "healthy", "version": config.APP_VERSION}

    return app


app = create_app()