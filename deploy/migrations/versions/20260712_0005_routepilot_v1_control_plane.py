"""add the durable RoutePilot V1 control plane and transactional outbox"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260712_0005"
down_revision = None
branch_labels = None
depends_on = None

json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    """Create V1 aggregate, immutable Artifact, event, idempotency, and outbox tables."""

    op.create_table(
        "v1_trips",
        sa.Column("trip_id", sa.String(length=96), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("owner_id", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("locale", sa.String(length=32), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("current_artifact_id", sa.String(length=96), nullable=True),
        sa.Column("current_artifact_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('active', 'archived')", name="ck_v1_trips_status"),
        sa.CheckConstraint("version >= 1", name="ck_v1_trips_version"),
    )
    op.create_index(
        "ix_v1_trips_tenant_owner_updated",
        "v1_trips",
        ["tenant_id", "owner_id", "updated_at"],
        unique=False,
    )
    op.create_index(
        "ix_v1_trips_tenant_status",
        "v1_trips",
        ["tenant_id", "status"],
        unique=False,
    )

    op.create_table(
        "v1_trip_members",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column(
            "trip_id",
            sa.String(length=96),
            sa.ForeignKey("v1_trips.trip_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("user_id", sa.String(length=128), nullable=False),
        sa.Column("role", sa.String(length=32), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("trip_id", "user_id", name="pk_v1_trip_members"),
        sa.CheckConstraint("role IN ('owner', 'editor', 'viewer')", name="ck_v1_trip_members_role"),
        sa.CheckConstraint("version >= 1", name="ck_v1_trip_members_version"),
    )
    op.create_index(
        "ix_v1_trip_members_tenant_user",
        "v1_trip_members",
        ["tenant_id", "user_id", "trip_id"],
        unique=False,
    )

    op.create_table(
        "v1_runs",
        sa.Column("run_id", sa.String(length=96), primary_key=True),
        sa.Column(
            "trip_id",
            sa.String(length=96),
            sa.ForeignKey("v1_trips.trip_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("trace_id", sa.String(length=96), nullable=False),
        sa.Column("lifecycle_state", sa.String(length=32), nullable=False),
        sa.Column("phase", sa.String(length=64), nullable=False),
        sa.Column("control_version", sa.Integer(), nullable=False),
        sa.Column("command", json_type, nullable=False),
        sa.Column("base_artifact_version", sa.Integer(), nullable=True),
        sa.Column("result_artifact_id", sa.String(length=96), nullable=True),
        sa.Column("result_artifact_version", sa.Integer(), nullable=True),
        sa.Column("public_error_code", sa.String(length=96), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "lifecycle_state IN ('queued', 'running', 'waiting_input', "
            "'cancel_requested', 'completed', 'failed', 'canceled')",
            name="ck_v1_runs_lifecycle",
        ),
        sa.CheckConstraint("control_version >= 1", name="ck_v1_runs_control_version"),
    )
    op.create_index(
        "ix_v1_runs_tenant_trip_created",
        "v1_runs",
        ["tenant_id", "trip_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_v1_runs_tenant_lifecycle_updated",
        "v1_runs",
        ["tenant_id", "lifecycle_state", "updated_at"],
        unique=False,
    )

    op.create_table(
        "v1_run_public_events",
        sa.Column("event_id", sa.String(length=96), primary_key=True),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("seq", sa.BigInteger(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("trip_id", sa.String(length=96), nullable=False),
        sa.Column(
            "run_id",
            sa.String(length=96),
            sa.ForeignKey("v1_runs.run_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("trace_id", sa.String(length=96), nullable=False),
        sa.Column("audience", sa.String(length=32), nullable=False),
        sa.Column("data", json_type, nullable=False),
        sa.UniqueConstraint("run_id", "seq", name="uq_v1_run_public_events_run_seq"),
        sa.CheckConstraint("schema_version = 1", name="ck_v1_public_events_schema"),
        sa.CheckConstraint("seq >= 1", name="ck_v1_public_events_seq"),
        sa.CheckConstraint(
            "audience = 'trip_members'",
            name="ck_v1_public_events_audience",
        ),
    )
    op.create_index(
        "ix_v1_run_public_events_tenant_run_seq",
        "v1_run_public_events",
        ["tenant_id", "run_id", "seq"],
        unique=False,
    )

    op.create_table(
        "v1_artifacts",
        sa.Column("artifact_id", sa.String(length=96), primary_key=True),
        sa.Column(
            "trip_id",
            sa.String(length=96),
            sa.ForeignKey("v1_trips.trip_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("artifact_type", sa.String(length=96), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_v1_artifacts_tenant_trip_created",
        "v1_artifacts",
        ["tenant_id", "trip_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "v1_artifact_versions",
        sa.Column(
            "artifact_id",
            sa.String(length=96),
            sa.ForeignKey("v1_artifacts.artifact_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("content", json_type, nullable=False),
        sa.Column("parent_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("artifact_id", "version", name="pk_v1_artifact_versions"),
        sa.CheckConstraint("version >= 1", name="ck_v1_artifact_versions_version"),
        sa.CheckConstraint("schema_version >= 1", name="ck_v1_artifact_versions_schema"),
        sa.CheckConstraint(
            "status IN ('candidate', 'selected', 'validated', 'published', "
            "'superseded', 'revoked')",
            name="ck_v1_artifact_versions_status",
        ),
    )
    op.create_index(
        "ix_v1_artifact_versions_status",
        "v1_artifact_versions",
        ["status"],
        unique=False,
    )

    op.create_table(
        "v1_idempotency_keys",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "response_run_id",
            sa.String(length=96),
            sa.ForeignKey("v1_runs.run_id", deferrable=True, initially="DEFERRED"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "actor_id",
            "operation",
            "idempotency_key",
            name="pk_v1_idempotency_keys",
        ),
    )
    op.create_index(
        "ix_v1_idempotency_keys_expires",
        "v1_idempotency_keys",
        ["expires_at"],
        unique=False,
    )

    op.create_table(
        "v1_outbox_events",
        sa.Column("outbox_id", sa.String(length=96), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("aggregate_type", sa.String(length=64), nullable=False),
        sa.Column("aggregate_id", sa.String(length=96), nullable=False),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=128), nullable=True),
        sa.Column("publish_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.String(length=512), nullable=True),
        sa.CheckConstraint("publish_attempts >= 0", name="ck_v1_outbox_attempts"),
    )
    op.create_index(
        "ix_v1_outbox_events_unpublished",
        "v1_outbox_events",
        ["published_at", "available_at", "created_at"],
        unique=False,
    )

    tenant_tables = (
        "v1_trips",
        "v1_trip_members",
        "v1_runs",
        "v1_run_public_events",
        "v1_artifacts",
        "v1_artifact_versions",
        "v1_idempotency_keys",
        "v1_outbox_events",
    )
    for table_name in tenant_tables:
        op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
        op.execute(
            sa.text(
                f'CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}" '
                "USING (tenant_id = current_setting('routepilot.tenant_id', true)) "
                "WITH CHECK (tenant_id = current_setting('routepilot.tenant_id', true))"
            )
        )


def downgrade() -> None:
    """Drop the V1 control plane in reverse dependency order."""

    op.drop_index("ix_v1_outbox_events_unpublished", table_name="v1_outbox_events")
    op.drop_table("v1_outbox_events")
    op.drop_index("ix_v1_idempotency_keys_expires", table_name="v1_idempotency_keys")
    op.drop_table("v1_idempotency_keys")
    op.drop_index("ix_v1_artifact_versions_status", table_name="v1_artifact_versions")
    op.drop_table("v1_artifact_versions")
    op.drop_index("ix_v1_artifacts_tenant_trip_created", table_name="v1_artifacts")
    op.drop_table("v1_artifacts")
    op.drop_index(
        "ix_v1_run_public_events_tenant_run_seq",
        table_name="v1_run_public_events",
    )
    op.drop_table("v1_run_public_events")
    op.drop_index("ix_v1_runs_tenant_lifecycle_updated", table_name="v1_runs")
    op.drop_index("ix_v1_runs_tenant_trip_created", table_name="v1_runs")
    op.drop_table("v1_runs")
    op.drop_index("ix_v1_trips_tenant_status", table_name="v1_trips")
    op.drop_index("ix_v1_trip_members_tenant_user", table_name="v1_trip_members")
    op.drop_table("v1_trip_members")
    op.drop_index("ix_v1_trips_tenant_owner_updated", table_name="v1_trips")
    op.drop_table("v1_trips")
