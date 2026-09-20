# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""LLM 脱敏核心测试（设计见 docs/architecture/LLM数据脱敏与合规设计.md §4）。"""

from __future__ import annotations

import pytest

from app.admin_ai.core.llm_redaction import PlaceholderRegistry, RedactionBlockedError, Redactor


@pytest.fixture
def redactor() -> Redactor:
    return Redactor(known_names={"张三", "李四"})


# ---------------------------------------------------------------- 规则脱敏


def test_redact_phone(redactor: Redactor) -> None:
    result = redactor.redact("我的手机号是 13812345678", session_key="c1")
    assert "13812345678" not in result.text
    assert "[手机1]" in result.text
    assert "phone" in result.categories


def test_blocked_id_card_raises(redactor: Redactor) -> None:
    """身份证属 L4：命中即中止调用，不做「脱敏后送出」（设计 §3 白名单优先于 §4.2 规则）。"""
    with pytest.raises(RedactionBlockedError):
        redactor.redact("身份证 110101199001011234 请办理入职", session_key="c1")


def test_blocked_bank_card_raises(redactor: Redactor) -> None:
    """银行卡同属 L4，命中即中止。"""
    with pytest.raises(RedactionBlockedError):
        redactor.redact("打款到 6222021234567890123", session_key="c1")


def test_redact_email(redactor: Redactor) -> None:
    result = redactor.redact("邮件发到 zhangsan@example.com", session_key="c1")
    assert "zhangsan@example.com" not in result.text
    assert "email" in result.categories


def test_redact_known_person_name(redactor: Redactor) -> None:
    """姓名按已知集合精确匹配（不做通用 NER，避免误判）。"""
    result = redactor.redact("帮张三开个在职证明", session_key="c1")
    assert "张三" not in result.text
    assert "[员工1]" in result.text
    assert "person" in result.categories


def test_unknown_name_left_intact(redactor: Redactor) -> None:
    """不在已知集合中的名字不动（宁少勿错，兜底靠 DPA 与审计）。"""
    result = redactor.redact("帮王五开个证明", session_key="c1")
    assert "王五" in result.text


def test_amount_kept_by_default() -> None:
    redactor = Redactor()
    result = redactor.redact("报销 800 元", session_key="c1")
    assert "800" in result.text
    assert "amount" not in result.categories


def test_amount_redacted_when_configured() -> None:
    redactor = Redactor(redact_amount=True)
    result = redactor.redact("报销 800 元", session_key="c1")
    assert "800" not in result.text
    assert "amount" in result.categories


def test_plain_text_untouched(redactor: Redactor) -> None:
    result = redactor.redact("我想请年假，2026-09-25 到 2026-09-26", session_key="c1")
    assert result.text == "我想请年假，2026-09-25 到 2026-09-26"
    assert result.categories == []


# ------------------------------------------------------- 占位符会话内一致性


def test_same_session_same_placeholder(redactor: Redactor) -> None:
    """同一会话内同一实体必须映射到同一占位符，否则 LLM 会当成两个人。"""
    first = redactor.redact("张三要请假", session_key="c1")
    second = redactor.redact("张三的证明开好了吗", session_key="c1")
    assert "[员工1]" in first.text
    assert "[员工1]" in second.text
    assert "[员工2]" not in second.text


def test_different_entities_get_different_placeholders(redactor: Redactor) -> None:
    result = redactor.redact("张三和李四都要请假", session_key="c1")
    assert "[员工1]" in result.text
    assert "[员工2]" in result.text


def test_session_isolation(redactor: Redactor) -> None:
    """不同会话各自编号，不共享映射。"""
    redactor.redact("张三请假", session_key="c1")
    other = redactor.redact("李四请假", session_key="c2")
    assert "[员工1]" in other.text  # c2 内重新从 1 开始


# ------------------------------------------------------------------- 回填


def test_restore_placeholders(redactor: Redactor) -> None:
    redactor.redact("帮张三开证明，电话 13812345678", session_key="c1")
    restored = redactor.restore("已为 [员工1] 提交申请，稍后发送至 [手机1]", session_key="c1")
    assert "张三" in restored
    assert "13812345678" in restored
    assert "[员工1]" not in restored


def test_restore_unknown_placeholder_kept(redactor: Redactor) -> None:
    """LLM 幻觉出的未登记占位符原样保留，不猜测。"""
    redactor.redact("张三请假", session_key="c1")
    restored = redactor.restore("已通知 [员工9] 处理", session_key="c1")
    assert "[员工9]" in restored


def test_restore_in_unknown_session_is_noop(redactor: Redactor) -> None:
    assert redactor.restore("已为 [员工1] 提交", session_key="never-used") == "已为 [员工1] 提交"


# --------------------------------------------------------------- L4 拦截


def test_contains_blocked_detects_id_card(redactor: Redactor) -> None:
    assert redactor.contains_blocked("身份证 110101199001011234") is not None


def test_contains_blocked_detects_bank_card(redactor: Redactor) -> None:
    assert redactor.contains_blocked("打款到 6222021234567890123") is not None


def test_contains_blocked_returns_none_for_normal_text(redactor: Redactor) -> None:
    assert redactor.contains_blocked("我想请年假") is None


# --------------------------------------------------------- PlaceholderRegistry


def test_registry_numbers_monotonically() -> None:
    registry = PlaceholderRegistry()
    assert registry.to_placeholder("c1", "person", "张三") == "[员工1]"
    assert registry.to_placeholder("c1", "person", "李四") == "[员工2]"
    assert registry.to_placeholder("c1", "person", "张三") == "[员工1]"


def test_registry_clear_session() -> None:
    registry = PlaceholderRegistry()
    registry.to_placeholder("c1", "person", "张三")
    registry.clear("c1")
    assert registry.to_placeholder("c1", "person", "张三") == "[员工1]"
