# -*- coding: utf-8 -*-
"""approval_rule_conditions

补齐设计 §12 偏离项 4/5：审批规则支持**按槽位条件分支**，并把场景文档要求审批、
此前未接入的四个业务类型配置上规则。

1. `approval_rules` 新增 `condition`（JSON，可空）：条件列表（隐式 AND），
   形如 `[{"slot": "days", "op": "gt", "value": 2}]`；算子受限见 conditions.py。
2. 用印拆分支：`合同章 → 法务（role:legal）`，其余印章 → 部门主管（场景 10 §5 规则 2/5）。
3. 新增默认规则（依据场景文档，均可由行政/财务通过管理端调整）：
   - 请假（场景 05 §审批规则）：≤2 天 → 主管；>2 天 → 主管 + HR 复核；兜底 → 主管
   - 差旅（场景 08 §5 规则 3）：≤5 天 → 主管；>5 天 → 总监 + 主管；兜底 → 主管
   - 固定资产（场景 09 §5 规则 3）：价值 ≥5000 → 总监；兜底（≤5000 或价值未知）→ 主管
   - 物资领用（场景 04 §5 规则 3）：单价 ≥100 → 主管；兜底 → 主管

   注：请假/差旅的「天数」由起止日期派生（`conditions.build_rule_context`）；
   物资/资产的「单价/价值」取用户或下游给出的金额槽位，缺失时走兜底规则（不猜测金额）。

Revision ID: 003
Revises: 002
Create Date: 2026-09-20
"""

import uuid
from decimal import Decimal
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# 本迁移新增/替换的规则：(business_type, 金额下限, 金额上限, 步序, 审批人类型, 参数, 条件, 备注)
NEW_RULES: list[dict] = [
    # --- 用印：合同章走法务，其余走部门主管（替换 002 里的单一 seal 规则）---
    {
        "business_type": "seal",
        "amount_min": None,
        "amount_max": None,
        "step_order": 1,
        "approver_type": "role",
        "approver_param": "legal",
        "condition": [{"slot": "seal_type", "op": "eq", "value": "合同章"}],
        "remark": "场景 10 §5 规则 2：合同章使用须经法务专员审核（需有 role=legal 的成员）",
    },
    {
        "business_type": "seal",
        "amount_min": None,
        "amount_max": None,
        "step_order": 1,
        "approver_type": "self_dept_manager",
        "approver_param": None,
        "condition": None,
        "remark": "场景 10 流程图：其他印章走部门负责人审批（兜底规则）",
    },
    # --- 请假（场景 05 审批规则）---
    {
        "business_type": "leave",
        "amount_min": None,
        "amount_max": None,
        "step_order": 1,
        "approver_type": "self_dept_manager",
        "approver_param": None,
        "condition": [{"slot": "days", "op": "lte", "value": 2}],
        "remark": "场景 05：连续请假 ≤2 天 → 直属主管审批",
    },
    {
        "business_type": "leave",
        "amount_min": None,
        "amount_max": None,
        "step_order": 1,
        "approver_type": "self_dept_manager",
        "approver_param": None,
        "condition": [{"slot": "days", "op": "gt", "value": 2}],
        "remark": "场景 05：连续请假 >2 天 → 主管审批（第 1 级）",
    },
    {
        "business_type": "leave",
        "amount_min": None,
        "amount_max": None,
        "step_order": 2,
        "approver_type": "role",
        "approver_param": "hr",
        "condition": [{"slot": "days", "op": "gt", "value": 2}],
        "remark": "场景 05：连续请假 >2 天 → HR 复核（需有 role=hr 的成员）",
    },
    {
        "business_type": "leave",
        "amount_min": None,
        "amount_max": None,
        "step_order": 1,
        "approver_type": "self_dept_manager",
        "approver_param": None,
        "condition": None,
        "remark": "请假兜底：天数算不出（日期缺失）时按主管审批，不静默放行",
    },
    # --- 差旅（场景 08 §5 规则 3）---
    {
        "business_type": "travel",
        "amount_min": None,
        "amount_max": None,
        "step_order": 1,
        "approver_type": "self_dept_manager",
        "approver_param": None,
        "condition": [{"slot": "days", "op": "lte", "value": 5}],
        "remark": "场景 08：出差 ≤5 天 → 主管审批",
    },
    {
        "business_type": "travel",
        "amount_min": None,
        "amount_max": None,
        "step_order": 1,
        "approver_type": "parent_dept_manager",
        "approver_param": None,
        "condition": [{"slot": "days", "op": "gt", "value": 5}],
        "remark": "场景 08：出差 >5 天 → 总监审批（第 1 级）",
    },
    {
        "business_type": "travel",
        "amount_min": None,
        "amount_max": None,
        "step_order": 2,
        "approver_type": "self_dept_manager",
        "approver_param": None,
        "condition": [{"slot": "days", "op": "gt", "value": 5}],
        "remark": "场景 08：出差 >5 天 → 主管审批（第 2 级）",
    },
    {
        "business_type": "travel",
        "amount_min": None,
        "amount_max": None,
        "step_order": 1,
        "approver_type": "self_dept_manager",
        "approver_param": None,
        "condition": None,
        "remark": "差旅兜底：天数算不出时按主管审批",
    },
    # --- 固定资产（场景 09 §5 规则 3）---
    {
        "business_type": "asset",
        "amount_min": Decimal("5000"),
        "amount_max": None,
        "step_order": 1,
        "approver_type": "parent_dept_manager",
        "approver_param": None,
        "condition": None,
        "remark": "场景 09：单项资产价值 >5000 元 → 总监审批",
    },
    {
        "business_type": "asset",
        "amount_min": None,
        "amount_max": None,
        "step_order": 1,
        "approver_type": "self_dept_manager",
        "approver_param": None,
        "condition": None,
        "remark": "场景 09：≤5000 元或价值未知 → 主管审批（兜底规则）",
    },
    # --- 物资领用（场景 04 §5 规则 3）---
    {
        "business_type": "material",
        "amount_min": Decimal("100"),
        "amount_max": None,
        "step_order": 1,
        "approver_type": "self_dept_manager",
        "approver_param": None,
        "condition": None,
        "remark": "场景 04：单价 >100 元的贵重物资 → 主管审批",
    },
    {
        "business_type": "material",
        "amount_min": None,
        "amount_max": None,
        "step_order": 1,
        "approver_type": "self_dept_manager",
        "approver_param": None,
        "condition": None,
        "remark": "物资兜底：单价未知时按主管审批（接入库存单价后可细化为仅贵重物资审批）",
    },
]

# 本迁移新增规则覆盖的业务类型（导入这些规则前先清掉旧规则，保证幂等）
AFFECTED_BUSINESS_TYPES = ("seal", "leave", "travel", "asset", "material")


def upgrade() -> None:
    op.add_column("approval_rules", sa.Column("condition", sa.JSON, nullable=True))
    _reload_default_rules()


def _reload_default_rules() -> None:
    """按业务类型整体替换默认规则（幂等：重复执行结果一致）。"""
    bind = op.get_bind()
    # 仅替换「本迁移负责且尚未配置条件能力」的业务规则；expense 的区间规则保持不变
    bind.execute(
        sa.text("DELETE FROM approval_rules WHERE business_type IN :types").bindparams(
            sa.bindparam("types", value=AFFECTED_BUSINESS_TYPES, expanding=True)
        )
    )
    for rule in NEW_RULES:
        bind.execute(
            sa.text(
                "INSERT INTO approval_rules "
                "(id, business_type, amount_min, amount_max, step_order, approver_type, "
                " approver_param, approval_mode, required, enabled, condition, remark, "
                " created_at, updated_at) "
                "VALUES (:id, :business_type, :amount_min, :amount_max, :step_order, "
                " :approver_type, :approver_param, 'any_one', true, true, "
                " CAST(:condition AS JSON), :remark, now(), now())"
            ),
            {
                "id": str(uuid.uuid4()),
                "business_type": rule["business_type"],
                "amount_min": rule["amount_min"],
                "amount_max": rule["amount_max"],
                "step_order": rule["step_order"],
                "approver_type": rule["approver_type"],
                "approver_param": rule["approver_param"],
                "condition": (
                    None if rule["condition"] is None else _json_dumps(rule["condition"])
                ),
                "remark": rule["remark"],
            },
        )


def _json_dumps(value) -> str:
    import json

    return json.dumps(value, ensure_ascii=False)


def downgrade() -> None:
    # 回滚时删除本迁移新增的业务规则，并恢复 002 版本的用印默认规则（不重建 expense 规则）
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM approval_rules WHERE business_type IN :types").bindparams(
            sa.bindparam("types", value=AFFECTED_BUSINESS_TYPES, expanding=True)
        )
    )
    bind.execute(
        sa.text(
            "INSERT INTO approval_rules "
            "(id, business_type, amount_min, amount_max, step_order, approver_type, "
            " approver_param, approval_mode, required, enabled, remark, created_at, updated_at) "
            "VALUES (:id, 'seal', NULL, NULL, 1, 'self_dept_manager', NULL, 'any_one', "
            " true, true, '用印默认走部门主管审批，行政/法务可改为 role/finance 或会签', "
            " now(), now())"
        ),
        {"id": str(uuid.uuid4())},
    )
    op.drop_column("approval_rules", "condition")
