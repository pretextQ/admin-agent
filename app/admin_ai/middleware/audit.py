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