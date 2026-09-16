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