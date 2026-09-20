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
from app.admin_ai.core.agent.dialog import DialogManager
from app.admin_ai.core.agent.intent import IntentRecognizer
from app.admin_ai.core.agent.orchestrator import Orchestrator
from app.admin_ai.core.agent.slot import SlotExtractor
from app.admin_ai.core.agent.state_store import build_state_store
from app.admin_ai.core.llm import build_llm_client
from app.admin_ai.core.rag.retriever import build_retriever
from app.admin_ai.core.rules.engine import RuleEngine
from app.admin_ai.core.tools.registry import init_tools
from app.admin_ai.middleware.audit import AuditMiddleware
from app.admin_ai.middleware.logging import TraceIdMiddleware
from app.admin_ai.utils.logger import configure_logging

logger = structlog.get_logger(__name__)


async def _load_known_names(gateway) -> None:
    """从 users 表加载姓名，供脱敏层做精确匹配（不做通用 NER，避免误判）。

    加载失败只告警不阻断启动：姓名脱敏降级为仅正则规则（手机号/邮箱等仍生效）。
    """
    try:
        from sqlalchemy import select

        from app.admin_ai.db.database import get_session_factory
        from app.admin_ai.db.models import UserModel

        factory = get_session_factory()
        async with factory() as session:
            rows = (
                await session.execute(
                    select(UserModel.name).where(
                        UserModel.is_active == True,  # noqa: E712
                        UserModel.is_deleted == False,  # noqa: E712
                    )
                )
            ).scalars().all()
        names = {name for name in rows if name}
        gateway.update_known_names(names)
        logger.info("脱敏层已加载已知姓名", count=len(names))
    except Exception as exc:  # noqa: BLE001 - 姓名脱敏失效不应阻断启动
        logger.warning("加载已知姓名失败，姓名脱敏降级为正则规则", error=str(exc))


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

    # 初始化 LLM 客户端（未配置密钥时降级为规则回退）
    llm_client = build_llm_client(config)
    # 加载已知姓名供脱敏层精确匹配（200 人规模，启动时一次加载开销可忽略）
    if llm_client is not None and config.LLM_REDACTION_ENABLED:
        await _load_known_names(llm_client)

    # 初始化 RAG 检索器（Chroma 服务优先，回退本地嵌入式）
    retriever = build_retriever(config)
    app.state.retriever = retriever

    # 初始化编排器
    intent_recognizer = IntentRecognizer(llm_client=llm_client, model=config.LLM_MODEL)
    slot_extractor = SlotExtractor(llm_client=llm_client, model=config.LLM_MODEL)
    dialog_manager = DialogManager()
    orchestrator = Orchestrator(
        intent_recognizer=intent_recognizer,
        slot_extractor=slot_extractor,
        dialog_manager=dialog_manager,
        rule_engine=rule_engine,
        tool_registry=tool_registry,
        retriever=retriever,
        llm_client=llm_client,
        model=config.LLM_MODEL,
    )
    app.state.orchestrator = orchestrator
    logger.info("编排器初始化完成")

    # 初始化会话状态存储（Redis 不可用时回退进程内）
    app.state.state_store = build_state_store(config.REDIS_URL)
    logger.info("会话状态存储初始化完成")

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

    # 后添加的中间件在外层：TraceId 最先处理请求，审计日志因此带有 trace 上下文
    app.add_middleware(AuditMiddleware)
    app.add_middleware(TraceIdMiddleware)

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
