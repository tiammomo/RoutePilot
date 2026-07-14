"""add versioned, auditable knowledge document lifecycle commands

Revision ID: 20260713_0011
Revises: 20260712_0010
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260713_0011"
down_revision = "20260712_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add CAS versioning and replay-safe lifecycle command audit."""

    op.add_column(
        "v1_knowledge_documents",
        sa.Column(
            "version",
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text("1"),
        ),
    )
    op.create_check_constraint(
        "ck_v1_knowledge_documents_version",
        "v1_knowledge_documents",
        "version >= 1",
    )
    op.create_table(
        "v1_knowledge_document_commands",
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "document_id",
            sa.String(length=96),
            sa.ForeignKey("v1_knowledge_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("target_status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.String(length=512), nullable=True),
        sa.Column("result_status", sa.String(length=32), nullable=False),
        sa.Column("result_reason", sa.String(length=512), nullable=True),
        sa.Column("result_version", sa.BigInteger(), nullable=False),
        sa.Column("result_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "scope_key",
            "idempotency_key",
            name="pk_v1_knowledge_document_commands",
        ),
        sa.CheckConstraint(
            "target_status IN ('published', 'quarantined', 'tombstoned')",
            name="ck_v1_knowledge_document_commands_target",
        ),
        sa.CheckConstraint(
            "result_status IN ('published', 'quarantined', 'tombstoned')",
            name="ck_v1_knowledge_document_commands_result",
        ),
        sa.CheckConstraint(
            "result_version >= 1",
            name="ck_v1_knowledge_document_commands_version",
        ),
    )
    op.execute(
        "ALTER TABLE v1_knowledge_document_commands ENABLE ROW LEVEL SECURITY"
    )
    op.execute(
        "CREATE POLICY v1_knowledge_document_commands_scope "
        "ON v1_knowledge_document_commands "
        "USING (scope_key IN ('__public__', "
        "current_setting('routepilot.tenant_id', true))) "
        "WITH CHECK (scope_key IN ('__public__', "
        "current_setting('routepilot.tenant_id', true)))"
    )


def downgrade() -> None:
    """Remove lifecycle audit and CAS versioning."""

    op.drop_table("v1_knowledge_document_commands")
    op.drop_constraint(
        "ck_v1_knowledge_documents_version",
        "v1_knowledge_documents",
        type_="check",
    )
    op.drop_column("v1_knowledge_documents", "version")
