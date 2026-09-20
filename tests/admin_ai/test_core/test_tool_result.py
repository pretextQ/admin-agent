# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""工具结果解析测试（受理编号回填依赖它）。"""

from __future__ import annotations

import pytest

from app.admin_ai.core.tools.base import (
    ToolResult,
    extract_external_id,
    parse_downstream_payload,
)

# 开发桩的真实响应形态（str(dict) 后为 Python repr）
STUB_TEXT = str({
    "code": 0,
    "message": "success (dev stub)",
    "path": "expense/create_draft",
    "data": {
        "draft_id": "MOCK-2046C424",
        "status": "draft_created",
        "external_id": "MOCK-2046C424",
        "received": {"amount": 500},
    },
    "operator": None,
})


def test_text_classmethod_still_usable() -> None:
    """`ToolResult.text()` 构造器不得被实例属性遮蔽。

    前科：曾给 ToolResult 加了一个叫 `text` 的实例 property，静默覆盖同名 classmethod，
    12 个工具的构造调用全部变成 `'property' object is not callable`。
    """
    result = ToolResult.text("ok")
    assert result.content == [{"type": "text", "text": "ok"}]
    assert result.text_content == "ok"


def test_external_id_from_stub_repr() -> None:
    """开发桩的 Python repr 响应也能取到受理编号。"""
    assert ToolResult.text(STUB_TEXT).external_id == "MOCK-2046C424"


def test_external_id_from_json() -> None:
    """真实服务的 JSON 响应同样支持。"""
    result = ToolResult.text('{"code": 0, "data": {"external_id": "MOCK-F9D673BA"}}')
    assert result.external_id == "MOCK-F9D673BA"


def test_external_id_absent_returns_none() -> None:
    """响应里没有编号时返回 None，不能编一个出来。"""
    assert ToolResult.text('{"code": 0, "data": {"draft_id": "x"}}').external_id is None


def test_external_id_skipped_on_error() -> None:
    """失败的执行结果不携带编号，避免把上一次的编号写进任务。"""
    assert ToolResult.error(STUB_TEXT).external_id is None


def test_external_id_unparseable_text_returns_none() -> None:
    """非结构化文本（如 LLM 话术）不应抛异常。"""
    assert ToolResult.text("操作已完成").external_id is None


@pytest.mark.parametrize("text", ["", "not a dict", "[1, 2, 3]", "None"])
def test_parse_downstream_payload_tolerates_garbage(text: str) -> None:
    """解析器只认字典结构，其余一律返回空字典。"""
    assert parse_downstream_payload(text) == {}


def test_extract_external_id_accepts_flat_payload() -> None:
    """没有 data 信封时也认顶层的 external_id。"""
    assert extract_external_id('{"external_id": "MOCK-1"}') == "MOCK-1"
