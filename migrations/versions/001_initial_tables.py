# -*- coding: utf-8 -*-
"""initial_tables

Revision ID: 001
Revises:
Create Date: 2026-09-16
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- users ---
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("employee_id", sa.String(50), unique=True, index=True, nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("open_id", sa.String(100), unique=True, index=True, nullable=True),
        sa.Column("department", sa.String(100), index=True, nullable=True),
        sa.Column("position", sa.String(100), nullable=True),
        sa.Column("email", sa.String(200), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("role", sa.String(50), nullable=False, server_default="employee"),
        sa.Column("permissions", sa.JSON, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("is_deleted", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # --- conversations ---
    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), index=True, nullable=False),
        sa.Column(
            "status",
            sa.Enum("active", "completed", "transferred", name="conversationstatus"),
            nullable=False,
            server_default="active",
        ),
        sa.Column("intent", sa.String(100), nullable=True),
        sa.Column("business_type", sa.String(100), nullable=True),
        sa.Column("context", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # --- messages ---
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            index=True,
            nullable=False,
        ),
        sa.Column(
            "role",
            sa.Enum("user", "assistant", "system", name="messagerole"),
            nullable=False,
        ),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("meta", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )

    # --- tasks ---
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id"), index=True, nullable=False),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            nullable=True,
        ),
        sa.Column(
            "type",
            sa.Enum(
                "leave", "expense", "travel", "meeting_room", "vehicle",
                "material", "asset", "seal", "certificate", "onboarding",
                name="tasktype",
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "pending", "processing", "approving",
                "completed", "failed", "cancelled",
                name="taskstatus",
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("title", sa.String(200), nullable=True),
        sa.Column("data", sa.JSON, nullable=True),
        sa.Column("external_id", sa.String(100), nullable=True),
        sa.Column("approver_id", sa.String(36), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="low"),
        sa.Column(
            "requires_confirmation", sa.Boolean, nullable=False, server_default=sa.text("false")
        ),
        sa.Column("idempotency_key", sa.String(64), unique=True, nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )

    # --- approvals ---
    op.create_table(
        "approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "task_id", sa.String(36), sa.ForeignKey("tasks.id"), index=True, nullable=False
        ),
        sa.Column(
            "approver_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            index=True,
            nullable=False,
        ),
        sa.Column("step", sa.Integer, nullable=False, server_default="1"),
        sa.Column(
            "action",
            sa.Enum("approve", "reject", "add_sign", name="approvalaction"),
            nullable=True,
        ),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("comment", sa.Text, nullable=True),
        sa.Column(
            "add_sign_user_id",
            sa.String(36),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime, nullable=True),
    )

    # --- audit_logs ---
    op.create_table(
        "audit_logs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), index=True, nullable=True),
        sa.Column("conversation_id", sa.String(36), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("resource_type", sa.String(100), nullable=True),
        sa.Column("resource_id", sa.String(100), nullable=True),
        sa.Column("input_data", sa.JSON, nullable=True),
        sa.Column("output_data", sa.JSON, nullable=True),
        sa.Column("tool_calls", sa.JSON, nullable=True),
        sa.Column("decision", sa.String(200), nullable=True),
        sa.Column("decision_reason", sa.Text, nullable=True),
        sa.Column("ip_address", sa.String(50), nullable=True),
        sa.Column("user_agent", sa.String(500), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime,
            index=True,
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # --- knowledge_docs ---
    op.create_table(
        "knowledge_docs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("category", sa.String(50), index=True, nullable=False),
        sa.Column("tags", sa.JSON, nullable=True),
        sa.Column("content", sa.Text, nullable=True),
        sa.Column("source_uri", sa.String(500), nullable=True),
        sa.Column("chunk_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("created_by", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("knowledge_docs")
    op.drop_table("audit_logs")
    op.drop_table("approvals")
    op.drop_table("tasks")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("users")
    op.execute("DROP TYPE IF EXISTS approvalaction")
    op.execute("DROP TYPE IF EXISTS taskstatus")
    op.execute("DROP TYPE IF EXISTS tasktype")
    op.execute("DROP TYPE IF EXISTS messagerole")
    op.execute("DROP TYPE IF EXISTS conversationstatus")