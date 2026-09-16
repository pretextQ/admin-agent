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