"""add pinned replans, typed resume input, and capability-secured shares"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "20260712_0010"
down_revision = "20260712_0009"
branch_labels = None
depends_on = None

json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _tenant_policy(table_name: str) -> None:
    op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
    op.execute(
        sa.text(
            f'CREATE POLICY "{table_name}_tenant_isolation" ON "{table_name}" '
            "USING (tenant_id = current_setting('routepilot.tenant_id', true)) "
            "WITH CHECK (tenant_id = current_setting('routepilot.tenant_id', true))"
        )
    )


def upgrade() -> None:
    """Create the final V1 replan/resume and public-share control planes."""

    op.add_column("v1_runs", sa.Column("base_artifact_id", sa.String(length=96)))
    op.add_column("v1_runs", sa.Column("pending_input", json_type))
    op.create_check_constraint(
        "ck_v1_runs_base_artifact_pair",
        "v1_runs",
        "(base_artifact_id IS NULL) = (base_artifact_version IS NULL)",
    )

    op.create_table(
        "v1_shares",
        sa.Column("share_id", sa.String(length=96), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("public_id", sa.String(length=96), nullable=False, unique=True),
        sa.Column(
            "trip_id",
            sa.String(length=96),
            sa.ForeignKey("v1_trips.trip_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_artifact_id", sa.String(length=96), nullable=False),
        sa.Column("source_artifact_version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("capability_epoch", sa.BigInteger(), nullable=False),
        sa.Column("capability_secret_hash", sa.String(length=64), nullable=False),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failure_window_started_at", sa.DateTime(timezone=True)),
        sa.Column("blocked_until", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('active', 'revoked')", name="ck_v1_shares_status"),
        sa.CheckConstraint("version >= 1", name="ck_v1_shares_version"),
        sa.CheckConstraint("capability_epoch >= 1", name="ck_v1_shares_epoch"),
        sa.CheckConstraint("failed_attempts >= 0", name="ck_v1_shares_failures"),
    )
    op.create_index(
        "ix_v1_shares_tenant_trip_updated",
        "v1_shares",
        ["tenant_id", "trip_id", "updated_at"],
    )
    op.create_index(
        "ix_v1_shares_tenant_status",
        "v1_shares",
        ["tenant_id", "status"],
    )

    op.create_table(
        "routepilot_share_public_lookup",
        sa.Column("public_id", sa.String(length=96), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column(
            "share_id",
            sa.String(length=96),
            sa.ForeignKey("v1_shares.share_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
    )
    op.create_table(
        "v1_share_snapshots",
        sa.Column("snapshot_id", sa.String(length=96), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column(
            "share_id",
            sa.String(length=96),
            sa.ForeignKey("v1_shares.share_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("snapshot", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "v1_share_sessions",
        sa.Column("session_hash", sa.String(length=64), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column(
            "share_id",
            sa.String(length=96),
            sa.ForeignKey("v1_shares.share_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("capability_epoch", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("capability_epoch >= 1", name="ck_v1_share_sessions_epoch"),
    )
    op.create_index(
        "ix_v1_share_sessions_tenant_share_epoch",
        "v1_share_sessions",
        ["tenant_id", "share_id", "capability_epoch"],
    )
    op.create_index(
        "ix_v1_share_sessions_expires",
        "v1_share_sessions",
        ["expires_at"],
    )
    op.create_table(
        "v1_share_idempotency_keys",
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "response_share_id",
            sa.String(length=96),
            sa.ForeignKey(
                "v1_shares.share_id",
                ondelete="CASCADE",
                deferrable=True,
                initially="DEFERRED",
            ),
            nullable=False,
        ),
        sa.Column("response_version", sa.Integer(), nullable=False),
        sa.Column("response_epoch", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "tenant_id",
            "actor_id",
            "operation",
            "idempotency_key",
            name="pk_v1_share_idempotency_keys",
        ),
        sa.CheckConstraint("response_version >= 1", name="ck_v1_share_idempotency_version"),
        sa.CheckConstraint("response_epoch >= 1", name="ck_v1_share_idempotency_epoch"),
    )
    op.create_index(
        "ix_v1_share_idempotency_keys_expires",
        "v1_share_idempotency_keys",
        ["expires_at"],
    )

    for table_name in (
        "v1_shares",
        "v1_share_snapshots",
        "v1_share_sessions",
        "v1_share_idempotency_keys",
    ):
        _tenant_policy(table_name)

    op.execute(sa.text("REVOKE ALL ON TABLE routepilot_share_public_lookup FROM PUBLIC"))
    op.execute(
        sa.text(
            """
            CREATE FUNCTION routepilot_resolve_share_tenant(p_public_id text)
            RETURNS text
            LANGUAGE sql
            STABLE
            SECURITY DEFINER
            SET search_path = pg_catalog
            AS $$
              SELECT tenant_id
                FROM public.routepilot_share_public_lookup
               WHERE public_id = p_public_id
               LIMIT 1
            $$
            """
        )
    )
    op.execute(
        sa.text("REVOKE ALL ON FUNCTION routepilot_resolve_share_tenant(text) FROM PUBLIC")
    )


def downgrade() -> None:
    """Remove sharing and resume fields in reverse dependency order."""

    op.execute(sa.text("DROP FUNCTION IF EXISTS routepilot_resolve_share_tenant(text)"))
    op.drop_index(
        "ix_v1_share_idempotency_keys_expires",
        table_name="v1_share_idempotency_keys",
    )
    op.drop_table("v1_share_idempotency_keys")
    op.drop_index("ix_v1_share_sessions_expires", table_name="v1_share_sessions")
    op.drop_index(
        "ix_v1_share_sessions_tenant_share_epoch",
        table_name="v1_share_sessions",
    )
    op.drop_table("v1_share_sessions")
    op.drop_table("v1_share_snapshots")
    op.drop_table("routepilot_share_public_lookup")
    op.drop_index("ix_v1_shares_tenant_status", table_name="v1_shares")
    op.drop_index("ix_v1_shares_tenant_trip_updated", table_name="v1_shares")
    op.drop_table("v1_shares")
    op.drop_constraint("ck_v1_runs_base_artifact_pair", "v1_runs", type_="check")
    op.drop_column("v1_runs", "pending_input")
    op.drop_column("v1_runs", "base_artifact_id")
