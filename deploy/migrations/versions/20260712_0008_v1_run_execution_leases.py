"""add fenced execution leases for crash-recoverable V1 Product Runs

Revision ID: 20260712_0008
Revises: 20260712_0007
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260712_0008"
down_revision = "20260712_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add owner/expiry/attempt fencing state without changing public Run JSON."""

    op.add_column(
        "v1_runs",
        sa.Column("execution_lease_owner", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "v1_runs",
        sa.Column("execution_lease_until", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "v1_runs",
        sa.Column(
            "execution_attempt",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_v1_runs_execution_attempt",
        "v1_runs",
        "execution_attempt >= 0",
    )
    op.create_check_constraint(
        "ck_v1_runs_execution_lease_pair",
        "v1_runs",
        "(execution_lease_owner IS NULL) = (execution_lease_until IS NULL)",
    )
    op.create_index(
        "ix_v1_runs_recoverable_execution",
        "v1_runs",
        ["tenant_id", "lifecycle_state", "execution_lease_until"],
        unique=False,
    )


def downgrade() -> None:
    """Remove Product Run execution fencing state."""

    op.drop_index("ix_v1_runs_recoverable_execution", table_name="v1_runs")
    op.drop_constraint(
        "ck_v1_runs_execution_lease_pair",
        "v1_runs",
        type_="check",
    )
    op.drop_constraint(
        "ck_v1_runs_execution_attempt",
        "v1_runs",
        type_="check",
    )
    op.drop_column("v1_runs", "execution_attempt")
    op.drop_column("v1_runs", "execution_lease_until")
    op.drop_column("v1_runs", "execution_lease_owner")
