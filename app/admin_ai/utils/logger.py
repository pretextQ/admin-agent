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