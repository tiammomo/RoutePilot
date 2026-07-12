"""SQLAlchemy Core tables for the durable RoutePilot V1 control plane."""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import JSON


metadata = MetaData()
json_type = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")

trips_table = Table(
    "v1_trips",
    metadata,
    Column("trip_id", String(96), primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column("owner_id", String(128), nullable=False),
    Column("title", String(160), nullable=False),
    Column("locale", String(32), nullable=False),
    Column("timezone", String(64), nullable=False),
    Column("status", String(32), nullable=False),
    Column("version", Integer, nullable=False),
    Column("current_artifact_id", String(96), nullable=True),
    Column("current_artifact_version", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

Index("ix_v1_trips_tenant_owner_updated", trips_table.c.tenant_id, trips_table.c.owner_id, trips_table.c.updated_at)
Index("ix_v1_trips_tenant_status", trips_table.c.tenant_id, trips_table.c.status)

trip_members_table = Table(
    "v1_trip_members",
    metadata,
    Column("tenant_id", String(128), nullable=False),
    Column("trip_id", String(96), ForeignKey("v1_trips.trip_id", ondelete="CASCADE"), nullable=False),
    Column("user_id", String(128), nullable=False),
    Column("role", String(32), nullable=False),
    Column("version", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("trip_id", "user_id", name="pk_v1_trip_members"),
)

Index(
    "ix_v1_trip_members_tenant_user",
    trip_members_table.c.tenant_id,
    trip_members_table.c.user_id,
    trip_members_table.c.trip_id,
)

runs_table = Table(
    "v1_runs",
    metadata,
    Column("run_id", String(96), primary_key=True),
    Column("trip_id", String(96), ForeignKey("v1_trips.trip_id", ondelete="CASCADE"), nullable=False),
    Column("tenant_id", String(128), nullable=False),
    Column("actor_id", String(128), nullable=False),
    Column("trace_id", String(96), nullable=False),
    Column("lifecycle_state", String(32), nullable=False),
    Column("phase", String(64), nullable=False),
    Column("control_version", Integer, nullable=False),
    Column("command", json_type, nullable=False),
    Column("base_artifact_id", String(96), nullable=True),
    Column("base_artifact_version", Integer, nullable=True),
    Column("pending_input", json_type, nullable=True),
    Column("result_artifact_id", String(96), nullable=True),
    Column("result_artifact_version", Integer, nullable=True),
    Column("public_error_code", String(96), nullable=True),
    Column("execution_lease_owner", String(128), nullable=True),
    Column("execution_lease_until", DateTime(timezone=True), nullable=True),
    Column("execution_attempt", BigInteger, nullable=False, server_default="0"),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

Index("ix_v1_runs_tenant_trip_created", runs_table.c.tenant_id, runs_table.c.trip_id, runs_table.c.created_at)
Index("ix_v1_runs_tenant_lifecycle_updated", runs_table.c.tenant_id, runs_table.c.lifecycle_state, runs_table.c.updated_at)
Index(
    "ix_v1_runs_recoverable_execution",
    runs_table.c.tenant_id,
    runs_table.c.lifecycle_state,
    runs_table.c.execution_lease_until,
)

run_public_events_table = Table(
    "v1_run_public_events",
    metadata,
    Column("event_id", String(96), primary_key=True),
    Column("schema_version", Integer, nullable=False),
    Column("seq", BigInteger, nullable=False),
    Column("type", String(64), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False),
    Column("tenant_id", String(128), nullable=False),
    Column("trip_id", String(96), nullable=False),
    Column("run_id", String(96), ForeignKey("v1_runs.run_id", ondelete="CASCADE"), nullable=False),
    Column("trace_id", String(96), nullable=False),
    Column("audience", String(32), nullable=False),
    Column("data", json_type, nullable=False),
    UniqueConstraint("run_id", "seq", name="uq_v1_run_public_events_run_seq"),
)

Index("ix_v1_run_public_events_tenant_run_seq", run_public_events_table.c.tenant_id, run_public_events_table.c.run_id, run_public_events_table.c.seq)

artifacts_table = Table(
    "v1_artifacts",
    metadata,
    Column("artifact_id", String(96), primary_key=True),
    Column("trip_id", String(96), ForeignKey("v1_trips.trip_id", ondelete="CASCADE"), nullable=False),
    Column("tenant_id", String(128), nullable=False),
    Column("artifact_type", String(96), nullable=False),
    Column("created_by", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

Index("ix_v1_artifacts_tenant_trip_created", artifacts_table.c.tenant_id, artifacts_table.c.trip_id, artifacts_table.c.created_at)

artifact_versions_table = Table(
    "v1_artifact_versions",
    metadata,
    Column("artifact_id", String(96), ForeignKey("v1_artifacts.artifact_id", ondelete="CASCADE"), nullable=False),
    Column("tenant_id", String(128), nullable=False),
    Column("version", Integer, nullable=False),
    Column("schema_version", Integer, nullable=False),
    Column("status", String(32), nullable=False),
    Column("content", json_type, nullable=False),
    Column("parent_version", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint("artifact_id", "version", name="pk_v1_artifact_versions"),
)

Index("ix_v1_artifact_versions_status", artifact_versions_table.c.status)

idempotency_keys_table = Table(
    "v1_idempotency_keys",
    metadata,
    Column("tenant_id", String(128), nullable=False),
    Column("actor_id", String(128), nullable=False),
    Column("operation", String(64), nullable=False),
    Column("idempotency_key", String(200), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column(
        "response_run_id",
        String(96),
        ForeignKey("v1_runs.run_id", deferrable=True, initially="DEFERRED"),
        nullable=False,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint(
        "tenant_id",
        "actor_id",
        "operation",
        "idempotency_key",
        name="pk_v1_idempotency_keys",
    ),
)

Index("ix_v1_idempotency_keys_expires", idempotency_keys_table.c.expires_at)

outbox_events_table = Table(
    "v1_outbox_events",
    metadata,
    Column("outbox_id", String(96), primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column("aggregate_type", String(64), nullable=False),
    Column("aggregate_id", String(96), nullable=False),
    Column("event_type", String(96), nullable=False),
    Column("payload", json_type, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("available_at", DateTime(timezone=True), nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=True),
    Column("locked_at", DateTime(timezone=True), nullable=True),
    Column("locked_by", String(128), nullable=True),
    Column("publish_attempts", Integer, nullable=False, default=0),
    Column("last_error", String(512), nullable=True),
)

Index(
    "ix_v1_outbox_events_unpublished",
    outbox_events_table.c.published_at,
    outbox_events_table.c.available_at,
    outbox_events_table.c.created_at,
)


# Public sharing deliberately separates the non-secret public-id lookup from
# tenant data.  The lookup contains no capability material or snapshot data;
# it exists so an unauthenticated exchange can discover the tenant and then
# enter the same forced-RLS boundary as every authenticated operation.
share_public_lookup_table = Table(
    "routepilot_share_public_lookup",
    metadata,
    Column("public_id", String(96), primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column(
        "share_id",
        String(96),
        ForeignKey("v1_shares.share_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
)

shares_table = Table(
    "v1_shares",
    metadata,
    Column("share_id", String(96), primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column("public_id", String(96), nullable=False, unique=True),
    Column(
        "trip_id",
        String(96),
        ForeignKey("v1_trips.trip_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("source_artifact_id", String(96), nullable=False),
    Column("source_artifact_version", Integer, nullable=False),
    Column("status", String(24), nullable=False),
    Column("version", Integer, nullable=False),
    Column("capability_epoch", BigInteger, nullable=False),
    Column("capability_secret_hash", String(64), nullable=False),
    Column("failed_attempts", Integer, nullable=False, default=0),
    Column("failure_window_started_at", DateTime(timezone=True), nullable=True),
    Column("blocked_until", DateTime(timezone=True), nullable=True),
    Column("created_by", String(128), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
)

Index(
    "ix_v1_shares_tenant_trip_updated",
    shares_table.c.tenant_id,
    shares_table.c.trip_id,
    shares_table.c.updated_at,
)
Index(
    "ix_v1_shares_tenant_status",
    shares_table.c.tenant_id,
    shares_table.c.status,
)

share_snapshots_table = Table(
    "v1_share_snapshots",
    metadata,
    Column("snapshot_id", String(96), primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column(
        "share_id",
        String(96),
        ForeignKey("v1_shares.share_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    ),
    Column("snapshot", json_type, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

share_sessions_table = Table(
    "v1_share_sessions",
    metadata,
    Column("session_hash", String(64), primary_key=True),
    Column("tenant_id", String(128), nullable=False),
    Column(
        "share_id",
        String(96),
        ForeignKey("v1_shares.share_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("capability_epoch", BigInteger, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
)

Index(
    "ix_v1_share_sessions_tenant_share_epoch",
    share_sessions_table.c.tenant_id,
    share_sessions_table.c.share_id,
    share_sessions_table.c.capability_epoch,
)
Index("ix_v1_share_sessions_expires", share_sessions_table.c.expires_at)

share_idempotency_keys_table = Table(
    "v1_share_idempotency_keys",
    metadata,
    Column("tenant_id", String(128), nullable=False),
    Column("actor_id", String(128), nullable=False),
    Column("operation", String(64), nullable=False),
    Column("idempotency_key", String(200), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column(
        "response_share_id",
        String(96),
        ForeignKey(
            "v1_shares.share_id",
            ondelete="CASCADE",
            deferrable=True,
            initially="DEFERRED",
        ),
        nullable=False,
    ),
    Column("response_version", Integer, nullable=False),
    Column("response_epoch", BigInteger, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint(
        "tenant_id",
        "actor_id",
        "operation",
        "idempotency_key",
        name="pk_v1_share_idempotency_keys",
    ),
)

Index(
    "ix_v1_share_idempotency_keys_expires",
    share_idempotency_keys_table.c.expires_at,
)
