"""add fenced execution recovery for durable A2A Tasks

Revision ID: 20260712_0009
Revises: 20260712_0008
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260712_0009"
down_revision = "20260712_0008"
branch_labels = None
depends_on = None

json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    """Persist typed resume input and a database-clock A2A execution fence."""

    op.add_column(
        "v1_agent_tasks",
        sa.Column("execution_input", json_type, nullable=True),
    )
    op.add_column(
        "v1_agent_tasks",
        sa.Column("execution_lease_owner", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "v1_agent_tasks",
        sa.Column("execution_lease_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "v1_agent_tasks",
        sa.Column(
            "execution_attempt",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_v1_agent_tasks_execution_attempt",
        "v1_agent_tasks",
        "execution_attempt >= 0",
    )
    op.create_check_constraint(
        "ck_v1_agent_tasks_execution_lease_pair",
        "v1_agent_tasks",
        "(execution_lease_owner IS NULL) = (execution_lease_until IS NULL)",
    )
    op.create_check_constraint(
        "ck_v1_agent_tasks_execution_input_object",
        "v1_agent_tasks",
        "execution_input IS NULL OR jsonb_typeof(execution_input) = 'object'",
    )
    op.create_check_constraint(
        "ck_v1_agent_tasks_execution_input_size",
        "v1_agent_tasks",
        "execution_input IS NULL OR octet_length(execution_input::text) <= 262144",
    )
    op.create_index(
        "ix_v1_agent_tasks_recoverable_execution",
        "v1_agent_tasks",
        ["tenant_id", "task_state", "execution_lease_until"],
        unique=False,
    )


def downgrade() -> None:
    """Remove A2A recovery fencing and the current typed resume input."""

    op.drop_index(
        "ix_v1_agent_tasks_recoverable_execution",
        table_name="v1_agent_tasks",
    )
    op.drop_constraint(
        "ck_v1_agent_tasks_execution_input_size",
        "v1_agent_tasks",
        type_="check",
    )
    op.drop_constraint(
        "ck_v1_agent_tasks_execution_input_object",
        "v1_agent_tasks",
        type_="check",
    )
    op.drop_constraint(
        "ck_v1_agent_tasks_execution_lease_pair",
        "v1_agent_tasks",
        type_="check",
    )
    op.drop_constraint(
        "ck_v1_agent_tasks_execution_attempt",
        "v1_agent_tasks",
        type_="check",
    )
    op.drop_column("v1_agent_tasks", "execution_attempt")
    op.drop_column("v1_agent_tasks", "execution_lease_until")
    op.drop_column("v1_agent_tasks", "execution_lease_owner")
    op.drop_column("v1_agent_tasks", "execution_input")
