# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""应用异常层级。"""

from __future__ import annotations


class AppError(Exception):
    """应用基础异常。"""


class UserNotFoundError(AppError):
    """用户不存在。"""


class ToolExecutionError(AppError):
    """工具执行失败。"""


class ExternalSystemError(AppError):
    """外部系统调用失败。"""


class AuthenticationError(AppError):
    """认证失败。"""


class AuthorizationError(AppError):
    """权限不足。"""


class ValidationError(AppError):
    """数据校验失败。"""


class NotFoundError(AppError):
    """资源不存在。"""