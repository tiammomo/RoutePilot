"""add RoutePilot V1 provenance-aware hybrid knowledge retrieval

Revision ID: 20260712_0006
Revises: 20260712_0005
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260712_0006"
down_revision = "20260712_0005"
branch_labels = None
depends_on = None

json_type = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    """Create lexical knowledge tables and an optional pgvector side index."""

    # Managed PostgreSQL may deny CREATE EXTENSION or omit pgvector.  Those two
    # expected capability failures leave a fully functional lexical schema.  A
    # malformed extension/install still fails the migration instead of hiding
    # an unsafe partial state.
    op.execute(
        """
        DO $routepilot_vector_extension$
        BEGIN
          BEGIN
            CREATE EXTENSION IF NOT EXISTS vector;
          EXCEPTION
            WHEN insufficient_privilege OR undefined_file OR feature_not_supported THEN
              RAISE WARNING
                'pgvector unavailable; RoutePilot RAG will run lexical-only until installed';
          END;
        END
        $routepilot_vector_extension$;
        """
    )

    op.create_table(
        "v1_knowledge_sources",
        sa.Column("source_id", sa.String(length=96), primary_key=True),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("visibility_scope", sa.String(length=16), nullable=False),
        sa.Column("canonical_source_uri", sa.String(length=2_048), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("trust_tier", sa.String(length=32), nullable=False),
        sa.Column("license_id", sa.String(length=128), nullable=False),
        sa.Column("license_url", sa.String(length=2_048), nullable=True),
        sa.Column("usage_policy", sa.Text(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "scope_key",
            "canonical_source_uri",
            name="uq_v1_knowledge_sources_scope_uri",
        ),
        sa.CheckConstraint(
            "visibility_scope IN ('public', 'tenant')",
            name="ck_v1_knowledge_sources_visibility",
        ),
        sa.CheckConstraint(
            "(visibility_scope = 'public' AND tenant_id IS NULL AND scope_key = '__public__') "
            "OR (visibility_scope = 'tenant' AND tenant_id IS NOT NULL "
            "AND scope_key = tenant_id)",
            name="ck_v1_knowledge_sources_scope_tenant",
        ),
        sa.CheckConstraint(
            "trust_tier IN ('official', 'operator', 'trusted_media', 'community', "
            "'user_private')",
            name="ck_v1_knowledge_sources_trust",
        ),
        sa.CheckConstraint(
            "retention_days IS NULL OR retention_days BETWEEN 1 AND 36500",
            name="ck_v1_knowledge_sources_retention",
        ),
    )
    op.create_index(
        "ix_v1_knowledge_sources_tenant_visibility",
        "v1_knowledge_sources",
        ["tenant_id", "visibility_scope"],
        unique=False,
    )

    op.create_table(
        "v1_knowledge_documents",
        sa.Column("document_id", sa.String(length=96), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(length=96),
            sa.ForeignKey("v1_knowledge_sources.source_id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("visibility_scope", sa.String(length=16), nullable=False),
        sa.Column("source_version", sa.String(length=128), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("geo_entities", json_type, nullable=False),
        sa.Column("tags", json_type, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("raw_object_uri", sa.String(length=2_048), nullable=True),
        sa.Column("parser_version", sa.String(length=64), nullable=False),
        sa.Column("chunker_version", sa.String(length=64), nullable=False),
        sa.Column("tokenizer_version", sa.String(length=64), nullable=False),
        sa.Column("corpus_revision", sa.String(length=128), nullable=False),
        sa.Column("trust_tier", sa.String(length=32), nullable=False),
        sa.Column("license_id", sa.String(length=128), nullable=False),
        sa.Column("license_url", sa.String(length=2_048), nullable=True),
        sa.Column("usage_policy", sa.Text(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("quarantine_reason", sa.String(length=512), nullable=True),
        sa.Column("injection_suspected", sa.Boolean(), nullable=False),
        sa.Column("metadata", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "scope_key",
            "source_id",
            "source_version",
            "content_hash",
            "corpus_revision",
            name="uq_v1_knowledge_documents_content_version",
        ),
        sa.CheckConstraint(
            "(visibility_scope = 'public' AND tenant_id IS NULL AND scope_key = '__public__') "
            "OR (visibility_scope = 'tenant' AND tenant_id IS NOT NULL "
            "AND scope_key = tenant_id)",
            name="ck_v1_knowledge_documents_scope_tenant",
        ),
        sa.CheckConstraint(
            "status IN ('published', 'quarantined', 'tombstoned')",
            name="ck_v1_knowledge_documents_status",
        ),
        sa.CheckConstraint(
            "valid_from IS NULL OR valid_until IS NULL OR valid_until > valid_from",
            name="ck_v1_knowledge_documents_validity",
        ),
    )
    op.create_index(
        "ix_v1_knowledge_documents_scope_revision_status",
        "v1_knowledge_documents",
        ["scope_key", "corpus_revision", "status"],
        unique=False,
    )
    op.create_index(
        "ix_v1_knowledge_documents_validity",
        "v1_knowledge_documents",
        ["valid_from", "valid_until"],
        unique=False,
    )

    op.create_table(
        "v1_knowledge_chunks",
        sa.Column("chunk_id", sa.String(length=96), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(length=96),
            sa.ForeignKey("v1_knowledge_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_id", sa.String(length=96), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=True),
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("visibility_scope", sa.String(length=16), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("token_count", sa.Integer(), nullable=False),
        sa.Column("lexical_terms", sa.Text(), nullable=False),
        sa.Column(
            "search_document",
            postgresql.TSVECTOR(),
            sa.Computed(
                "to_tsvector('simple'::regconfig, coalesce(lexical_terms, ''))",
                persisted=True,
            ),
            nullable=False,
        ),
        sa.Column("canonical_source_uri", sa.String(length=2_048), nullable=False),
        sa.Column("source_version", sa.String(length=128), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_title", sa.String(length=500), nullable=False),
        sa.Column("language", sa.String(length=32), nullable=False),
        sa.Column("geo_entities", json_type, nullable=False),
        sa.Column("tags", json_type, nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("corpus_revision", sa.String(length=128), nullable=False),
        sa.Column("tokenizer_version", sa.String(length=64), nullable=False),
        sa.Column("trust_tier", sa.String(length=32), nullable=False),
        sa.Column("license_id", sa.String(length=128), nullable=False),
        sa.Column("license_url", sa.String(length=2_048), nullable=True),
        sa.Column("usage_policy", sa.Text(), nullable=False),
        sa.Column("retention_days", sa.Integer(), nullable=True),
        sa.Column("injection_suspected", sa.Boolean(), nullable=False),
        sa.Column("content_taint", sa.String(length=32), nullable=False),
        sa.UniqueConstraint(
            "document_id",
            "ordinal",
            name="uq_v1_knowledge_chunks_document_ordinal",
        ),
        sa.CheckConstraint("ordinal >= 0", name="ck_v1_knowledge_chunks_ordinal"),
        sa.CheckConstraint(
            "token_count >= 1 AND char_length(content) BETWEEN 1 AND 8000",
            name="ck_v1_knowledge_chunks_size",
        ),
        sa.CheckConstraint(
            "content_taint = 'untrusted_evidence'",
            name="ck_v1_knowledge_chunks_taint",
        ),
        sa.CheckConstraint(
            "(visibility_scope = 'public' AND tenant_id IS NULL AND scope_key = '__public__') "
            "OR (visibility_scope = 'tenant' AND tenant_id IS NOT NULL "
            "AND scope_key = tenant_id)",
            name="ck_v1_knowledge_chunks_scope_tenant",
        ),
    )
    op.create_index(
        "ix_v1_knowledge_chunks_scope_revision",
        "v1_knowledge_chunks",
        ["scope_key", "corpus_revision"],
        unique=False,
    )
    op.create_index(
        "ix_v1_knowledge_chunks_filter",
        "v1_knowledge_chunks",
        ["visibility_scope", "tenant_id", "language", "source_type"],
        unique=False,
    )
    # Separate public/private GIN indexes avoid a shared tenant knowledge index.
    op.create_index(
        "ix_v1_knowledge_chunks_public_fts",
        "v1_knowledge_chunks",
        ["search_document"],
        unique=False,
        postgresql_using="gin",
        postgresql_where=sa.text("visibility_scope = 'public'"),
    )
    op.create_index(
        "ix_v1_knowledge_chunks_tenant_fts",
        "v1_knowledge_chunks",
        ["search_document"],
        unique=False,
        postgresql_using="gin",
        postgresql_where=sa.text("visibility_scope = 'tenant'"),
    )

    op.create_table(
        "v1_knowledge_ingestion_keys",
        sa.Column("scope_key", sa.String(length=128), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "document_id",
            sa.String(length=96),
            sa.ForeignKey("v1_knowledge_documents.document_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint(
            "scope_key",
            "idempotency_key",
            name="pk_v1_knowledge_ingestion_keys",
        ),
    )

    op.create_table(
        "v1_knowledge_retrieval_audit",
        sa.Column("audit_id", sa.String(length=96), primary_key=True),
        sa.Column("query_id", sa.String(length=96), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("actor_id", sa.String(length=128), nullable=False),
        sa.Column("query_hash", sa.String(length=64), nullable=False),
        sa.Column("corpus_revision", sa.String(length=128), nullable=False),
        sa.Column("filters", json_type, nullable=False),
        sa.Column("retrieval_mode", sa.String(length=16), nullable=False),
        sa.Column("vector_status", sa.String(length=32), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "retrieval_mode IN ('lexical', 'hybrid')",
            name="ck_v1_knowledge_audit_mode",
        ),
        sa.CheckConstraint("result_count >= 0", name="ck_v1_knowledge_audit_count"),
    )
    op.create_index(
        "ix_v1_knowledge_retrieval_audit_tenant_created",
        "v1_knowledge_retrieval_audit",
        ["tenant_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "v1_knowledge_publications",
        sa.Column("scope_key", sa.String(length=128), primary_key=True),
        sa.Column("current_revision", sa.String(length=128), nullable=False),
        sa.Column("updated_by", sa.String(length=128), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("publication_version", sa.BigInteger(), nullable=False),
        sa.CheckConstraint("publication_version >= 1", name="ck_v1_knowledge_publication_version"),
    )

    # The side table is conditional: its absence is the runtime capability flag.
    # HNSW indexes are also split by visibility and all queries still apply the
    # server-derived tenant predicate before returning candidates.
    op.execute(
        """
        DO $routepilot_vector_schema$
        BEGIN
          IF EXISTS (
            SELECT 1
              FROM pg_extension
             WHERE extname = 'vector'
               AND (
                 split_part(extversion, '.', 1)::integer > 0
                 OR (
                   split_part(extversion, '.', 1)::integer = 0
                   AND split_part(extversion, '.', 2)::integer >= 8
                 )
               )
          ) THEN
            EXECUTE $sql$
              CREATE TABLE v1_knowledge_chunk_vectors (
                chunk_id varchar(96) PRIMARY KEY
                  REFERENCES v1_knowledge_chunks(chunk_id) ON DELETE CASCADE,
                tenant_id varchar(128),
                visibility_scope varchar(16) NOT NULL
                  CHECK (visibility_scope IN ('public', 'tenant')),
                embedding vector(384) NOT NULL,
                embedding_model_id varchar(128) NOT NULL,
                embedding_model_version varchar(128) NOT NULL,
                created_at timestamptz NOT NULL,
                CHECK ((visibility_scope = 'public' AND tenant_id IS NULL) OR
                       (visibility_scope = 'tenant' AND tenant_id IS NOT NULL))
              )
            $sql$;
            EXECUTE $sql$
              CREATE INDEX ix_v1_knowledge_vectors_public_hnsw
              ON v1_knowledge_chunk_vectors
              USING hnsw (embedding vector_cosine_ops)
              WITH (m = 16, ef_construction = 64)
              WHERE visibility_scope = 'public'
            $sql$;
            EXECUTE $sql$
              CREATE INDEX ix_v1_knowledge_vectors_tenant_hnsw
              ON v1_knowledge_chunk_vectors
              USING hnsw (embedding vector_cosine_ops)
              WITH (m = 16, ef_construction = 64)
              WHERE visibility_scope = 'tenant'
            $sql$;
          ELSIF EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'vector') THEN
            RAISE WARNING
              'pgvector version is older than 0.8; RoutePilot RAG will run lexical-only';
          END IF;
        END
        $routepilot_vector_schema$;
        """
    )

    visibility_tables = (
        "v1_knowledge_sources",
        "v1_knowledge_documents",
        "v1_knowledge_chunks",
    )
    for table_name in visibility_tables:
        op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
        op.execute(
            sa.text(
                f'CREATE POLICY "{table_name}_visibility" ON "{table_name}" '
                "USING (visibility_scope = 'public' OR "
                "tenant_id = current_setting('routepilot.tenant_id', true)) "
                "WITH CHECK (visibility_scope = 'public' OR "
                "tenant_id = current_setting('routepilot.tenant_id', true))"
            )
        )

    for table_name in ("v1_knowledge_ingestion_keys", "v1_knowledge_publications"):
        op.execute(sa.text(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY'))
        op.execute(
            sa.text(
                f'CREATE POLICY "{table_name}_scope" ON "{table_name}" '
                "USING (scope_key IN ('__public__', "
                "current_setting('routepilot.tenant_id', true))) "
                "WITH CHECK (scope_key IN ('__public__', "
                "current_setting('routepilot.tenant_id', true)))"
            )
        )

    op.execute("ALTER TABLE v1_knowledge_retrieval_audit ENABLE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY v1_knowledge_retrieval_audit_tenant "
        "ON v1_knowledge_retrieval_audit "
        "USING (tenant_id = current_setting('routepilot.tenant_id', true)) "
        "WITH CHECK (tenant_id = current_setting('routepilot.tenant_id', true))"
    )
    op.execute(
        """
        DO $routepilot_vector_rls$
        BEGIN
          IF EXISTS (
            SELECT 1
              FROM pg_class c
              JOIN pg_namespace n ON n.oid = c.relnamespace
             WHERE n.nspname = 'public'
               AND c.relname = 'v1_knowledge_chunk_vectors'
               AND c.relkind = 'r'
          ) THEN
            ALTER TABLE v1_knowledge_chunk_vectors ENABLE ROW LEVEL SECURITY;
            CREATE POLICY v1_knowledge_chunk_vectors_visibility
              ON v1_knowledge_chunk_vectors
              USING (visibility_scope = 'public' OR
                     tenant_id = current_setting('routepilot.tenant_id', true))
              WITH CHECK (visibility_scope = 'public' OR
                          tenant_id = current_setting('routepilot.tenant_id', true));
          END IF;
        END
        $routepilot_vector_rls$;
        """
    )


def downgrade() -> None:
    """Drop RAG tables without removing a cluster-shared vector extension."""

    op.execute("DROP TABLE IF EXISTS v1_knowledge_chunk_vectors")
    op.drop_table("v1_knowledge_publications")
    op.drop_index(
        "ix_v1_knowledge_retrieval_audit_tenant_created",
        table_name="v1_knowledge_retrieval_audit",
    )
    op.drop_table("v1_knowledge_retrieval_audit")
    op.drop_table("v1_knowledge_ingestion_keys")
    op.drop_index("ix_v1_knowledge_chunks_tenant_fts", table_name="v1_knowledge_chunks")
    op.drop_index("ix_v1_knowledge_chunks_public_fts", table_name="v1_knowledge_chunks")
    op.drop_index("ix_v1_knowledge_chunks_filter", table_name="v1_knowledge_chunks")
    op.drop_index("ix_v1_knowledge_chunks_scope_revision", table_name="v1_knowledge_chunks")
    op.drop_table("v1_knowledge_chunks")
    op.drop_index(
        "ix_v1_knowledge_documents_validity",
        table_name="v1_knowledge_documents",
    )
    op.drop_index(
        "ix_v1_knowledge_documents_scope_revision_status",
        table_name="v1_knowledge_documents",
    )
    op.drop_table("v1_knowledge_documents")
    op.drop_index(
        "ix_v1_knowledge_sources_tenant_visibility",
        table_name="v1_knowledge_sources",
    )
    op.drop_table("v1_knowledge_sources")
