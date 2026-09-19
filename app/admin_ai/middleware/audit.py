# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""审计中间件。"""

from __future__ import annotations

import json
import re
from typing import Awaitable, Callable, Optional

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.admin_ai.db.models import AuditLogModel

logger = structlog.get_logger(__name__)

# 写操作才落审计表；查询类请求只走结构化日志
_AUDIT_METHODS = {"POST", "PUT", "DELETE"}
_MAX_INPUT_SIZE = 8000
_UUID_RE = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)


def _extract_user_id(request: Request) -> Optional[str]:
    """从 Authorization 头解析用户 id；匿名或无效 token 返回 None。"""
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        return None
    try:
        from app.admin_ai.core.auth.jwt_token import verify_token

        payload = verify_token(authorization[7:].strip())
    except ValueError:
        return None
    return payload.get("sub")


def _parse_path(path: str) -> tuple[str, Optional[str], Optional[str]]:
    """把 /api/v1/chat/send 解析为 (action, resource_type, resource_id)。"""
    parts = [p for p in path.strip("/").split("/") if p]
    if parts[:2] == ["api", "v1"]:
        parts = parts[2:]
    action = ".".join(parts) if parts else "unknown"
    resource_type = parts[0] if parts else None
    # 仅当末段形如 UUID 时视为资源 id，避免把 send/cancel 等动作段误判为 id
    resource_id = parts[-1] if len(parts) > 1 and _UUID_RE.match(parts[-1]) else None
    return action, resource_type, resource_id


async def _read_body(request: Request) -> Optional[dict]:
    """读取 JSON 请求体；过大或非 JSON 时记录占位说明。

    Starlette 的 _CachedRequest 保证 dispatch 中读取的 body 会回放给下游，
    不影响业务端点再次读取。
    """
    try:
        raw = await request.body()
    except Exception as exc:  # noqa: BLE001 - 审计不能影响请求
        logger.warning("审计读取请求体失败", error=str(exc))
        return None
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        return {"_note": "non-json body", "size": len(raw)}
    if len(raw) > _MAX_INPUT_SIZE:
        return {"_note": "payload truncated", "size": len(raw)}
    return parsed if isinstance(parsed, dict) else {"_value": parsed}


class AuditMiddleware(BaseHTTPMiddleware):
    """审计中间件：记录所有请求，并对写操作落库 audit_logs。"""

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        body: Optional[dict] = None
        if request.method in _AUDIT_METHODS:
            body = await _read_body(request)

        response = await call_next(request)
        logger.info(
            "请求完成",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
        )

        if request.method in _AUDIT_METHODS:
            await self._write_audit(request, response, body)
        return response

    async def _write_audit(self, request: Request, response: Response, body: Optional[dict]) -> None:
        """写审计日志；任何失败只告警，不阻断业务响应。"""
        try:
            action, resource_type, resource_id = _parse_path(request.url.path)
            conversation_id = None
            if isinstance(body, dict) and isinstance(body.get("conversation_id"), str):
                conversation_id = body["conversation_id"]

            from app.admin_ai.db.database import get_session_factory

            session_factory = get_session_factory()
            async with session_factory() as session:
                session.add(AuditLogModel(
                    user_id=_extract_user_id(request),
                    conversation_id=conversation_id,
                    action=action,
                    resource_type=resource_type,
                    resource_id=resource_id,
                    input_data=body,
                    decision=(
                        "success" if response.status_code < 400
                        else f"rejected({response.status_code})"
                    ),
                    ip_address=request.client.host if request.client else None,
                    user_agent=(request.headers.get("User-Agent") or "")[:500] or None,
                ))
                await session.commit()
        except Exception as exc:  # noqa: BLE001 - 审计不能影响业务
            logger.warning("审计日志写入失败", error=str(exc))
