"""add durable tenant-scoped A2A Task, dispatch inbox, and event persistence

Revision ID: 20260712_0007
Revises: 20260712_0006
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260712_0007"
down_revision = "20260712_0006"
branch_labels = None
depends_on = None

json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    """Create the A2A durable inbox, Task snapshot, and retained event log."""

    op.create_table(
        "v1_agent_tasks",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("agent_interface_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=96), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=160), nullable=False),
        sa.Column("dispatch_id", sa.String(length=36), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("context_id", sa.String(length=96), nullable=False),
        sa.Column("task_state", sa.Integer(), nullable=False),
        sa.Column("task_proto", sa.LargeBinary(), nullable=False),
        sa.Column("invocation", json_type, nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reference_task_ids", json_type, nullable=False),
        sa.Column("version", sa.BigInteger(), nullable=False),
        sa.Column("event_count", sa.Integer(), nullable=False),
        sa.Column("pending_input_request_id", sa.String(length=128), nullable=True),
        sa.Column("message_fingerprints", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "agent_interface_id",
            "task_id",
            name="pk_v1_agent_tasks",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "agent_interface_id",
            "dispatch_id",
            name="uq_v1_agent_tasks_dispatch",
        ),
        sa.CheckConstraint("version >= 1", name="ck_v1_agent_tasks_version"),
        sa.CheckConstraint(
            "event_count BETWEEN 0 AND 512",
            name="ck_v1_agent_tasks_event_count",
        ),
        sa.CheckConstraint(
            "task_state BETWEEN 1 AND 8",
            name="ck_v1_agent_tasks_state",
        ),
        sa.CheckConstraint(
            "octet_length(task_proto) BETWEEN 1 AND 2097152",
            name="ck_v1_agent_tasks_proto_size",
        ),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_v1_agent_tasks_request_fingerprint",
        ),
        sa.CheckConstraint(
            "dispatch_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            "[0-9a-f]{4}-[0-9a-f]{12}$'",
            name="ck_v1_agent_tasks_dispatch_uuid",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(invocation) = 'object'",
            name="ck_v1_agent_tasks_invocation_object",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(reference_task_ids) = 'array'",
            name="ck_v1_agent_tasks_reference_array",
        ),
        sa.CheckConstraint(
            "jsonb_typeof(message_fingerprints) = 'object'",
            name="ck_v1_agent_tasks_fingerprints_object",
        ),
        sa.CheckConstraint(
            "octet_length(invocation::text) <= 262144",
            name="ck_v1_agent_tasks_invocation_size",
        ),
        sa.CheckConstraint(
            "octet_length(reference_task_ids::text) <= 262144",
            name="ck_v1_agent_tasks_references_size",
        ),
        sa.CheckConstraint(
            "octet_length(message_fingerprints::text) <= 262144",
            name="ck_v1_agent_tasks_fingerprints_size",
        ),
    )
    op.create_index(
        "ix_v1_agent_tasks_tenant_interface_context",
        "v1_agent_tasks",
        ["tenant_id", "agent_interface_id", "context_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_v1_agent_tasks_tenant_run",
        "v1_agent_tasks",
        ["tenant_id", "run_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_v1_agent_tasks_state_deadline",
        "v1_agent_tasks",
        ["tenant_id", "agent_interface_id", "task_state", "deadline"],
        unique=False,
    )

    op.create_table(
        "v1_agent_dispatch_inbox",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("agent_interface_id", sa.String(length=128), nullable=False),
        sa.Column("dispatch_id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=96), nullable=False),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "agent_interface_id",
            "dispatch_id",
            name="pk_v1_agent_dispatch_inbox",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_interface_id", "task_id"],
            [
                "v1_agent_tasks.tenant_id",
                "v1_agent_tasks.agent_interface_id",
                "v1_agent_tasks.task_id",
            ],
            name="fk_v1_agent_dispatch_task",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_v1_agent_dispatch_fingerprint",
        ),
        sa.CheckConstraint(
            "dispatch_id ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-"
            "[0-9a-f]{4}-[0-9a-f]{12}$'",
            name="ck_v1_agent_dispatch_uuid",
        ),
    )
    op.create_index(
        "ix_v1_agent_dispatch_inbox_task",
        "v1_agent_dispatch_inbox",
        ["tenant_id", "agent_interface_id", "task_id"],
        unique=False,
    )

    op.create_table(
        "v1_agent_task_events",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("agent_interface_id", sa.String(length=128), nullable=False),
        sa.Column("task_id", sa.String(length=96), nullable=False),
        sa.Column("event_seq", sa.BigInteger(), nullable=False),
        sa.Column("task_version", sa.BigInteger(), nullable=False),
        sa.Column("event_kind", sa.String(length=64), nullable=False),
        sa.Column("event_proto", sa.LargeBinary(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "agent_interface_id",
            "task_id",
            "event_seq",
            name="pk_v1_agent_task_events",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "agent_interface_id", "task_id"],
            [
                "v1_agent_tasks.tenant_id",
                "v1_agent_tasks.agent_interface_id",
                "v1_agent_tasks.task_id",
            ],
            name="fk_v1_agent_task_events_task",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("event_seq >= 1", name="ck_v1_agent_task_events_seq"),
        sa.CheckConstraint(
            "task_version >= 1",
            name="ck_v1_agent_task_events_version",
        ),
        sa.CheckConstraint(
            "event_kind IN ('message', 'task', 'task_artifact_update', "
            "'task_status_update')",
            name="ck_v1_agent_task_events_kind",
        ),
        sa.CheckConstraint(
            "octet_length(event_proto) BETWEEN 1 AND 1048576",
            name="ck_v1_agent_task_events_proto_size",
        ),
    )
    op.create_index(
        "ix_v1_agent_task_events_replay",
        "v1_agent_task_events",
        [
            "tenant_id",
            "agent_interface_id",
            "task_id",
            "task_version",
            "event_seq",
        ],
        unique=False,
    )

    for table_name in (
        "v1_agent_tasks",
        "v1_agent_dispatch_inbox",
        "v1_agent_task_events",
    ):
        op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
        op.execute(
            sa.text(
                f'CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}" '
                "USING (tenant_id = current_setting('routepilot.tenant_id', true)) "
                "WITH CHECK (tenant_id = current_setting('routepilot.tenant_id', true))"
            )
        )


def downgrade() -> None:
    """Drop A2A durable persistence in reverse dependency order."""

    op.drop_index(
        "ix_v1_agent_task_events_replay",
        table_name="v1_agent_task_events",
    )
    op.drop_table("v1_agent_task_events")
    op.drop_index(
        "ix_v1_agent_dispatch_inbox_task",
        table_name="v1_agent_dispatch_inbox",
    )
    op.drop_table("v1_agent_dispatch_inbox")
    op.drop_index(
        "ix_v1_agent_tasks_state_deadline",
        table_name="v1_agent_tasks",
    )
    op.drop_index(
        "ix_v1_agent_tasks_tenant_run",
        table_name="v1_agent_tasks",
    )
    op.drop_index(
        "ix_v1_agent_tasks_tenant_interface_context",
        table_name="v1_agent_tasks",
    )
    op.drop_table("v1_agent_tasks")
