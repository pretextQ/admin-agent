"""org_and_approval_routing

评审 B-2（组织架构与审批路由）的 Expand 阶段迁移：
新增 departments / approval_rules / approval_delegations 三表，
users 加 department_id，approvals 加 approver_source / mode / delegated_from。

回填策略（设计 §7）：
1. 按 users.department 现有名称生成扁平部门（旧模型只有字符串，无层级信息）；
2. **不回填 manager_id** —— 组织数据不完整时宁可走人工指派，也不猜审批人；
   上线后需由 HR 同步或人工补主管，详见 docs/architecture/组织架构与审批路由设计.md §3；
3. 导入默认审批规则（APR-001/002 与用印默认规则），可由管理端调整。

Revision ID: 002
Revises: 001
Create Date: 2026-09-20
"""

import uuid
from collections.abc import Sequence
from decimal import Decimal

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: str | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# 默认审批规则（设计 §2.3 示例 + 用印默认）
DEFAULT_RULES = [
    {
        "business_type": "expense",
        "amount_min": Decimal("0"),
        "amount_max": Decimal("2000"),
        "step_order": 1,
        "approver_type": "self_dept_manager",
        "approver_param": None,
        "remark": "APR-001 单笔 ≤2000 元：部门主管审批",
    },
    {
        "business_type": "expense",
        "amount_min": Decimal("2000"),
        "amount_max": None,
        "step_order": 1,
        "approver_type": "parent_dept_manager",
        "approver_param": None,
        "remark": "APR-002 >2000 元：上级部门主管（总监）审批 → 部门主管审批",
    },
    {
        "business_type": "expense",
        "amount_min": Decimal("2000"),
        "amount_max": None,
        "step_order": 2,
        "approver_type": "self_dept_manager",
        "approver_param": None,
        "remark": "APR-002 第二级：部门主管审批",
    },
    {
        "business_type": "seal",
        "amount_min": None,
        "amount_max": None,
        "step_order": 1,
        "approver_type": "self_dept_manager",
        "approver_param": None,
        "remark": "用印默认走部门主管审批，行政/法务可改为 role/finance 或会签",
    },
]


def upgrade() -> None:
    # --- departments（部门树，物化路径）---
    op.create_table(
        "departments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column(
            "parent_id", sa.String(36), sa.ForeignKey("departments.id"), index=True, nullable=True
        ),
        sa.Column("path", sa.String(500), index=True, nullable=False),
        sa.Column("level", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "manager_id", sa.String(36), sa.ForeignKey("users.id"), index=True, nullable=True
        ),
        sa.Column("external_id", sa.String(100), unique=True, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # --- approval_rules（审批路由规则）---
    op.create_table(
        "approval_rules",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("business_type", sa.String(50), index=True, nullable=False),
        sa.Column("amount_min", sa.Numeric(12, 2), nullable=True),
        sa.Column("amount_max", sa.Numeric(12, 2), nullable=True),
        sa.Column("step_order", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "approver_type",
            sa.Enum(
                "self_dept_manager",
                "parent_dept_manager",
                "top_dept_manager",
                "role",
                "user",
                name="approvertype",
            ),
            nullable=False,
        ),
        sa.Column("approver_param", sa.String(100), nullable=True),
        sa.Column(
            "approval_mode",
            sa.Enum("any_one", "all_must", name="approvalmode"),
            nullable=False,
            server_default="any_one",
        ),
        sa.Column("required", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("remark", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # --- approval_delegations（代理审批）---
    op.create_table(
        "approval_delegations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "delegator_id", sa.String(36), sa.ForeignKey("users.id"), index=True, nullable=False
        ),
        sa.Column(
            "delegate_id", sa.String(36), sa.ForeignKey("users.id"), index=True, nullable=False
        ),
        sa.Column("start_at", sa.DateTime, nullable=False),
        sa.Column("end_at", sa.DateTime, nullable=False),
        sa.Column("business_types", sa.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # --- users.department_id（兼容期与 users.department 并存，Contract 阶段再删旧列）---
    op.add_column("users", sa.Column("department_id", sa.String(36), nullable=True))
    op.create_foreign_key("fk_users_department_id", "users", "departments", ["department_id"], ["id"])
    op.create_index("ix_users_department_id", "users", ["department_id"])

    # --- approvals 扩展列 ---
    op.add_column("approvals", sa.Column("approver_source", sa.String(50), nullable=True))
    op.add_column(
        "approvals",
        sa.Column("mode", sa.String(20), nullable=False, server_default="any_one"),
    )
    op.add_column("approvals", sa.Column("delegated_from", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_approvals_delegated_from", "approvals", "users", ["delegated_from"], ["id"]
    )

    _backfill_departments()
    _seed_default_rules()


def _backfill_departments() -> None:
    """旧 `users.department` 字符串 → 部门行 + 回填 users.department_id。

    只建扁平部门且不设主管：旧数据没有层级与汇报线信息，猜出来的审批人没有授权效力。
    """
    bind = op.get_bind()
    names = [
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT DISTINCT department FROM users "
                "WHERE department IS NOT NULL AND department <> ''"
            )
        ).fetchall()
    ]
    for name in names:
        department_id = str(uuid.uuid4())
        bind.execute(
            sa.text(
                "INSERT INTO departments (id, name, path, level, is_active, created_at, updated_at) "
                "VALUES (:id, :name, :path, 1, true, now(), now())"
            ),
            {"id": department_id, "name": name, "path": f"/{name}"},
        )
        bind.execute(
            sa.text("UPDATE users SET department_id = :id WHERE department = :name"),
            {"id": department_id, "name": name},
        )


def _seed_default_rules() -> None:
    """导入默认审批规则（幂等：仅当表为空时写入）。"""
    bind = op.get_bind()
    existing = bind.execute(sa.text("SELECT COUNT(*) FROM approval_rules")).scalar()
    if existing:
        return
    for rule in DEFAULT_RULES:
        bind.execute(
            sa.text(
                "INSERT INTO approval_rules "
                "(id, business_type, amount_min, amount_max, step_order, approver_type, "
                " approver_param, approval_mode, required, enabled, remark, created_at, updated_at) "
                "VALUES (:id, :business_type, :amount_min, :amount_max, :step_order, "
                " :approver_type, :approver_param, 'any_one', true, true, :remark, now(), now())"
            ),
            {
                "id": str(uuid.uuid4()),
                "business_type": rule["business_type"],
                "amount_min": rule["amount_min"],
                "amount_max": rule["amount_max"],
                "step_order": rule["step_order"],
                "approver_type": rule["approver_type"],
                "approver_param": rule["approver_param"],
                "remark": rule["remark"],
            },
        )


def downgrade() -> None:
    op.drop_constraint("fk_approvals_delegated_from", "approvals", type_="foreignkey")
    op.drop_column("approvals", "delegated_from")
    op.drop_column("approvals", "mode")
    op.drop_column("approvals", "approver_source")

    op.drop_index("ix_users_department_id", table_name="users")
    op.drop_constraint("fk_users_department_id", "users", type_="foreignkey")
    op.drop_column("users", "department_id")

    op.drop_table("approval_delegations")
    op.drop_table("approval_rules")
    op.drop_table("departments")

    op.execute("DROP TYPE IF EXISTS approvalmode")
    op.execute("DROP TYPE IF EXISTS approvertype")
