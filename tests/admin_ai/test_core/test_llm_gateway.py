# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""LLM 统一出入口（LLMGateway）测试。设计见 docs/architecture/LLM数据脱敏与合规设计.md §4.1。"""

from __future__ import annotations

import json
from typing import Any, Optional
from unittest.mock import AsyncMock

import pytest

from app.admin_ai.core.llm_redaction import RedactionBlockedError, Redactor
from app.admin_ai.core.llm_gateway import BusinessTypeExcludedError, LLMGateway


def _stub_client(reply: str = "好的") -> AsyncMock:
    """构造返回固定内容的供应商客户端桩。"""
    client = AsyncMock()
    message = type("Message", (), {"content": reply})()
    choice = type("Choice", (), {"message": message})()
    completion = type("Completion", (), {"choices": [choice]})()
    client.chat.completions.create.return_value = completion
    return client


def _collector() -> tuple[list[dict[str, Any]], Any]:
    records: list[dict[str, Any]] = []

    async def sink(record: dict[str, Any]) -> None:
        records.append(record)

    return records, sink


def _gateway(client: AsyncMock, **kwargs: Any) -> LLMGateway:
    redactor = kwargs.pop("redactor", None) or Redactor(known_names={"张三"})
    return LLMGateway(client=client, redactor=redactor, model="deepseek-flash", **kwargs)


def _sent_prompt(client: AsyncMock) -> str:
    return client.chat.completions.create.call_args.kwargs["messages"][0]["content"]


# --------------------------------------------------------------- 脱敏送出


async def test_gateway_redacts_before_sending() -> None:
    """送出的 prompt 中身份类字段已被替换为占位符。"""
    client = _stub_client()
    gateway = _gateway(client)
    await gateway.chat(
        messages=[{"role": "user", "content": "帮张三办理入职，电话 13812345678"}],
        purpose="intent",
        session_key="c1",
    )

    sent = _sent_prompt(client)
    assert "张三" not in sent
    assert "13812345678" not in sent
    assert "[员工1]" in sent
    assert "[手机1]" in sent


async def test_gateway_restores_response_text() -> None:
    """供应商回复中的占位符被回填为真实值。"""
    client = _stub_client("已为 [员工1] 提交，稍后短信通知 [手机1]")
    gateway = _gateway(client)
    reply = await gateway.chat(
        messages=[{"role": "user", "content": "帮张三办理，电话 13812345678"}],
        purpose="reply_generation",
        session_key="c1",
    )

    assert reply == "已为 张三 提交，稍后短信通知 13812345678"


async def test_gateway_same_session_placeholder_consistency() -> None:
    """同一会话两次调用使用同一占位符（多轮对话语义一致）。"""
    client = _stub_client()
    gateway = _gateway(client)
    await gateway.chat(
        messages=[{"role": "user", "content": "张三请假"}], purpose="intent", session_key="c1"
    )
    await gateway.chat(
        messages=[{"role": "user", "content": "张三的证明"}], purpose="slot", session_key="c1"
    )

    calls = client.chat.completions.create.call_args_list
    assert "[员工1]" in calls[0].kwargs["messages"][0]["content"]
    assert "[员工1]" in calls[1].kwargs["messages"][0]["content"]


# ----------------------------------------------------------------- 拦截


async def test_gateway_blocks_l4_without_calling_provider() -> None:
    """命中 L4 特征时抛异常，且**不发出**任何请求。"""
    client = _stub_client()
    gateway = _gateway(client)

    with pytest.raises(RedactionBlockedError):
        await gateway.chat(
            messages=[{"role": "user", "content": "身份证 110101199001011234 办入职"}],
            purpose="intent",
            session_key="c1",
        )

    client.chat.completions.create.assert_not_called()


async def test_gateway_excludes_sensitive_business_type() -> None:
    """涉密业务默认不走外部 LLM（证明开具、用印）。"""
    client = _stub_client()
    gateway = _gateway(client, excluded_business_types={"certificate", "seal"})

    with pytest.raises(BusinessTypeExcludedError):
        await gateway.chat(
            messages=[{"role": "user", "content": "开个在职证明"}],
            purpose="intent",
            session_key="c1",
            business_type="certificate",
        )

    client.chat.completions.create.assert_not_called()


async def test_gateway_allows_non_excluded_business_type() -> None:
    client = _stub_client()
    gateway = _gateway(client, excluded_business_types={"certificate"})
    await gateway.chat(
        messages=[{"role": "user", "content": "我要请假"}],
        purpose="intent",
        session_key="c1",
        business_type="leave",
    )
    assert client.chat.completions.create.await_count == 1


async def test_gateway_fail_closed_when_redactor_raises() -> None:
    """脱敏组件异常时**拒绝调用**（绝不降级为直发原文）。"""
    client = _stub_client()
    broken = AsyncMock()
    broken.redact = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("redactor boom"))
    gateway = _gateway(client, redactor=broken)

    with pytest.raises(RuntimeError):
        await gateway.chat(
            messages=[{"role": "user", "content": "帮张三办理"}], purpose="intent", session_key="c1"
        )

    client.chat.completions.create.assert_not_called()


# ----------------------------------------------------------------- 审计


async def test_gateway_audit_records_categories_not_values() -> None:
    """审计记录脱敏类别与用量，且**不含任何真值**。"""
    records, sink = _collector()
    client = _stub_client()
    gateway = _gateway(client, audit_sink=sink)

    await gateway.chat(
        messages=[{"role": "user", "content": "帮张三办理，电话 13812345678"}],
        purpose="intent",
        session_key="c1",
    )

    assert len(records) == 1
    record = records[0]
    assert record["purpose"] == "intent"
    assert record["model"] == "deepseek-flash"
    assert set(record["redacted_categories"]) == {"person", "phone"}
    assert record["blocked"] is False

    dumped = json.dumps(record, ensure_ascii=False)
    assert "张三" not in dumped
    assert "13812345678" not in dumped


async def test_gateway_audit_records_blocked_call() -> None:
    records, sink = _collector()
    client = _stub_client()
    gateway = _gateway(client, audit_sink=sink)

    with pytest.raises(RedactionBlockedError):
        await gateway.chat(
            messages=[{"role": "user", "content": "身份证 110101199001011234"}],
            purpose="slot",
            session_key="c1",
        )

    assert records and records[0]["blocked"] is True


# --------------------------------------------------------------- 开关


async def test_gateway_disabled_bypasses_redaction() -> None:
    """显式关闭时旁路脱敏（仅供开发环境；生产由 fail-fast 拦截）。"""
    client = _stub_client()
    gateway = _gateway(client, enabled=False)

    await gateway.chat(
        messages=[{"role": "user", "content": "帮张三办理，电话 13812345678"}],
        purpose="intent",
        session_key="c1",
    )

    sent = _sent_prompt(client)
    assert "张三" in sent
    assert "13812345678" in sent
