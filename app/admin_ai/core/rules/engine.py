# -*- coding: utf-8 -*-
# Copyright 2026  Admin AI Team, All rights reserved.
"""规则引擎。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


@dataclass
class ValidationResult:
    """校验结果。"""
    passed: bool = True
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# 差旅标准（场景文档 REQ-08）
TRAVEL_STANDARDS = {
    "hotel": {
        "一线城市": Decimal("500"),
        "二线城市": Decimal("400"),
    },
    "meal": {
        "default": Decimal("150"),  # 每人每餐
    },
    "transport": {
        "市内": Decimal("200"),
        "城际": Decimal("2000"),
    },
}

# 假期余额（示例，实际应从 HR 系统获取）
DEFAULT_LEAVE_BALANCE = {
    "年假": 10,
    "调休": 5,
    "事假": 999,  # 无限制
    "病假": 999,  # 无限制
}

# 报销标准（场景文档 REQ-07）
EXPENSE_STANDARDS = {
    "hotel": {
        "一线城市": Decimal("500"),
        "二线城市": Decimal("400"),
    },
    "meal": {
        "per_person": Decimal("150"),
    },
}

# 用印高风险类型
HIGH_RISK_SEAL_TYPES = ["合同章", "法人章"]


class RuleEngine:
    """规则引擎。"""

    def __init__(self, user_service: Any = None, config_service: Any = None) -> None:
        self._user_service = user_service
        self._config_service = config_service

    async def validate(
        self,
        business_type: str,
        slots: dict[str, Any],
        user_id: str,
    ) -> ValidationResult:
        """校验业务规则。

        Args:
            business_type: 业务类型。
            slots: 槽位数据。
            user_id: 用户 ID。

        Returns:
            校验结果。
        """
        result = ValidationResult()

        validators = {
            "leave": self._validate_leave,
            "expense": self._validate_expense,
            "travel": self._validate_travel,
            "seal": self._validate_seal,
            "material": self._validate_material,
            "meeting_room": self._validate_meeting_room,
        }

        validator = validators.get(business_type)
        if validator:
            await validator(slots, user_id, result)

        return result

    async def _validate_leave(
        self, slots: dict[str, Any], user_id: str, result: ValidationResult
    ) -> None:
        """校验请假规则（场景文档 REQ-05）。"""
        leave_type = slots.get("leave_type")
        start_date = slots.get("start_date")
        end_date = slots.get("end_date")

        if not leave_type or not start_date or not end_date:
            result.errors.append("请假类型、开始日期、结束日期为必填项")
            result.passed = False
            return

        # 计算请假天数
        try:
            start = datetime.strptime(str(start_date), "%Y-%m-%d")
            end = datetime.strptime(str(end_date), "%Y-%m-%d")
            days = (end - start).days + 1
            if days <= 0:
                result.errors.append("结束日期必须晚于开始日期")
                result.passed = False
                return
        except ValueError:
            result.errors.append("日期格式错误，应为 YYYY-MM-DD")
            result.passed = False
            return

        # 校验余额（年假和调休需要校验）
        if leave_type in ["年假", "调休"]:
            balance = DEFAULT_LEAVE_BALANCE.get(leave_type, 0)
            if days > balance:
                result.errors.append(f"{leave_type}余额不足，当前余额{balance}天，申请{days}天")
                result.passed = False

        # 病假3天以上需要提供病假条
        if leave_type == "病假" and days >= 3:
            result.warnings.append("病假3天以上需提供病假条")

    async def _validate_expense(
        self, slots: dict[str, Any], user_id: str, result: ValidationResult
    ) -> None:
        """校验报销规则（场景文档 REQ-07）。"""
        expense_type = slots.get("expense_type")
        amount = slots.get("amount")

        if not expense_type or amount is None:
            result.errors.append("费用类型和金额为必填项")
            result.passed = False
            return

        amount = Decimal(str(amount))

        # 校验发票有效期（180天）
        invoice_date = slots.get("invoice_date")
        if invoice_date:
            try:
                inv_date = datetime.strptime(str(invoice_date), "%Y-%m-%d")
                days_since = (datetime.now() - inv_date).days
                if days_since > 180:
                    result.errors.append("发票已超过180天有效期")
                    result.passed = False
            except ValueError:
                pass

        # 校验报销标准
        if expense_type == "酒店":
            city_level = slots.get("city_level", "二线城市")
            standard = EXPENSE_STANDARDS["hotel"].get(city_level, Decimal("400"))
            if amount > standard:
                result.warnings.append(f"住宿费超标准，{city_level}上限{standard}元/晚")

    async def _validate_travel(
        self, slots: dict[str, Any], user_id: str, result: ValidationResult
    ) -> None:
        """校验差旅规则（场景文档 REQ-08）。"""
        destination = slots.get("destination")
        start_date = slots.get("start_date")
        end_date = slots.get("end_date")

        if not destination or not start_date or not end_date:
            result.errors.append("目的地、开始日期、结束日期为必填项")
            result.passed = False
            return

        # 校验出差天数
        try:
            start = datetime.strptime(str(start_date), "%Y-%m-%d")
            end = datetime.strptime(str(end_date), "%Y-%m-%d")
            days = (end - start).days + 1
            if days <= 0:
                result.errors.append("结束日期必须晚于开始日期")
                result.passed = False
                return
            if days > 30:
                result.warnings.append("出差超过30天需特殊审批")
        except ValueError:
            result.errors.append("日期格式错误，应为 YYYY-MM-DD")
            result.passed = False

    async def _validate_seal(
        self, slots: dict[str, Any], user_id: str, result: ValidationResult
    ) -> None:
        """校验用印规则（场景文档 REQ-10）。"""
        seal_type = slots.get("seal_type")
        document_name = slots.get("document_name")

        if not seal_type or not document_name:
            result.errors.append("印章类型和文件名称为必填项")
            result.passed = False
            return

        # 高风险印章类型需要人工确认
        if seal_type in HIGH_RISK_SEAL_TYPES:
            result.warnings.append(f"{seal_type}属于高风险操作，需要人工确认")

    async def _validate_material(
        self, slots: dict[str, Any], user_id: str, result: ValidationResult
    ) -> None:
        """校验物资领用规则（场景文档 REQ-04）。"""
        item_name = slots.get("item_name")
        quantity = slots.get("quantity")

        if not item_name or quantity is None:
            result.errors.append("物资名称和数量为必填项")
            result.passed = False
            return

        if quantity <= 0:
            result.errors.append("领用数量必须大于0")
            result.passed = False

    async def _validate_meeting_room(
        self, slots: dict[str, Any], user_id: str, result: ValidationResult
    ) -> None:
        """校验会议室预定规则。"""
        start_time = slots.get("start_time")
        end_time = slots.get("end_time")

        if not start_time or not end_time:
            result.errors.append("开始时间和结束时间为必填项")
            result.passed = False
            return

        try:
            start = datetime.fromisoformat(str(start_time))
            end = datetime.fromisoformat(str(end_time))
            duration_hours = (end - start).total_seconds() / 3600

            if duration_hours <= 0:
                result.errors.append("结束时间必须晚于开始时间")
                result.passed = False
                return

            if duration_hours > 8:
                result.errors.append("会议室预定时长不能超过8小时")
                result.passed = False
                return

            if start.date() != end.date():
                result.errors.append("会议室预定必须在同一天内")
                result.passed = False
        except (ValueError, TypeError):
            result.errors.append("时间格式错误")
            result.passed = False