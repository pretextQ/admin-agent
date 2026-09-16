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