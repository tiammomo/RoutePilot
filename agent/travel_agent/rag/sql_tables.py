"""SQLAlchemy Core metadata for the PostgreSQL knowledge store.

The optional pgvector table is created conditionally by Alembic and accessed
through parameterized SQL, so importing this module does not require the
``pgvector`` Python package or PostgreSQL extension.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    Computed,
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
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.types import JSON

metadata = MetaData()
json_type = JSON().with_variant(JSONB(astext_type=Text()), "postgresql")

sources_table = Table(
    "v1_knowledge_sources",
    metadata,
    Column("source_id", String(96), primary_key=True),
    Column("tenant_id", String(128), nullable=True),
    Column("scope_key", String(128), nullable=False),
    Column("visibility_scope", String(16), nullable=False),
    Column("canonical_source_uri", String(2_048), nullable=False),
    Column("source_type", String(64), nullable=False),
    Column("trust_tier", String(32), nullable=False),
    Column("license_id", String(128), nullable=False),
    Column("license_url", String(2_048), nullable=True),
    Column("usage_policy", Text, nullable=False),
    Column("retention_days", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "scope_key",
        "canonical_source_uri",
        name="uq_v1_knowledge_sources_scope_uri",
    ),
)

Index(
    "ix_v1_knowledge_sources_tenant_visibility",
    sources_table.c.tenant_id,
    sources_table.c.visibility_scope,
)

documents_table = Table(
    "v1_knowledge_documents",
    metadata,
    Column("document_id", String(96), primary_key=True),
    Column(
        "source_id",
        String(96),
        ForeignKey("v1_knowledge_sources.source_id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("tenant_id", String(128), nullable=True),
    Column("scope_key", String(128), nullable=False),
    Column("visibility_scope", String(16), nullable=False),
    Column("source_version", String(128), nullable=False),
    Column("title", String(500), nullable=False),
    Column("language", String(32), nullable=False),
    Column("geo_entities", json_type, nullable=False),
    Column("tags", json_type, nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=True),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("valid_from", DateTime(timezone=True), nullable=True),
    Column("valid_until", DateTime(timezone=True), nullable=True),
    Column("content_hash", String(64), nullable=False),
    Column("raw_object_uri", String(2_048), nullable=True),
    Column("parser_version", String(64), nullable=False),
    Column("chunker_version", String(64), nullable=False),
    Column("tokenizer_version", String(64), nullable=False),
    Column("corpus_revision", String(128), nullable=False),
    Column("trust_tier", String(32), nullable=False),
    Column("license_id", String(128), nullable=False),
    Column("license_url", String(2_048), nullable=True),
    Column("usage_policy", Text, nullable=False),
    Column("retention_days", Integer, nullable=True),
    Column("status", String(32), nullable=False),
    Column("quarantine_reason", String(512), nullable=True),
    Column("injection_suspected", Boolean, nullable=False),
    Column("metadata", json_type, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    UniqueConstraint(
        "scope_key",
        "source_id",
        "source_version",
        "content_hash",
        "corpus_revision",
        name="uq_v1_knowledge_documents_content_version",
    ),
)

Index(
    "ix_v1_knowledge_documents_scope_revision_status",
    documents_table.c.scope_key,
    documents_table.c.corpus_revision,
    documents_table.c.status,
)
Index("ix_v1_knowledge_documents_validity", documents_table.c.valid_from, documents_table.c.valid_until)

chunks_table = Table(
    "v1_knowledge_chunks",
    metadata,
    Column("chunk_id", String(96), primary_key=True),
    Column(
        "document_id",
        String(96),
        ForeignKey("v1_knowledge_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("source_id", String(96), nullable=False),
    Column("tenant_id", String(128), nullable=True),
    Column("scope_key", String(128), nullable=False),
    Column("visibility_scope", String(16), nullable=False),
    Column("ordinal", Integer, nullable=False),
    Column("content", Text, nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("token_count", Integer, nullable=False),
    Column("lexical_terms", Text, nullable=False),
    Column(
        "search_document",
        TSVECTOR,
        Computed(
            "to_tsvector('simple'::regconfig, coalesce(lexical_terms, ''))",
            persisted=True,
        ),
        nullable=False,
    ),
    Column("canonical_source_uri", String(2_048), nullable=False),
    Column("source_version", String(128), nullable=False),
    Column("source_type", String(64), nullable=False),
    Column("source_title", String(500), nullable=False),
    Column("language", String(32), nullable=False),
    Column("geo_entities", json_type, nullable=False),
    Column("tags", json_type, nullable=False),
    Column("published_at", DateTime(timezone=True), nullable=True),
    Column("observed_at", DateTime(timezone=True), nullable=False),
    Column("valid_from", DateTime(timezone=True), nullable=True),
    Column("valid_until", DateTime(timezone=True), nullable=True),
    Column("corpus_revision", String(128), nullable=False),
    Column("tokenizer_version", String(64), nullable=False),
    Column("trust_tier", String(32), nullable=False),
    Column("license_id", String(128), nullable=False),
    Column("license_url", String(2_048), nullable=True),
    Column("usage_policy", Text, nullable=False),
    Column("retention_days", Integer, nullable=True),
    Column("injection_suspected", Boolean, nullable=False),
    Column("content_taint", String(32), nullable=False),
    UniqueConstraint("document_id", "ordinal", name="uq_v1_knowledge_chunks_document_ordinal"),
)

Index(
    "ix_v1_knowledge_chunks_scope_revision",
    chunks_table.c.scope_key,
    chunks_table.c.corpus_revision,
)
Index(
    "ix_v1_knowledge_chunks_filter",
    chunks_table.c.visibility_scope,
    chunks_table.c.tenant_id,
    chunks_table.c.language,
    chunks_table.c.source_type,
)

ingestion_keys_table = Table(
    "v1_knowledge_ingestion_keys",
    metadata,
    Column("scope_key", String(128), nullable=False),
    Column("idempotency_key", String(200), nullable=False),
    Column("request_hash", String(64), nullable=False),
    Column(
        "document_id",
        String(96),
        ForeignKey("v1_knowledge_documents.document_id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column("created_at", DateTime(timezone=True), nullable=False),
    PrimaryKeyConstraint(
        "scope_key",
        "idempotency_key",
        name="pk_v1_knowledge_ingestion_keys",
    ),
)

retrieval_audit_table = Table(
    "v1_knowledge_retrieval_audit",
    metadata,
    Column("audit_id", String(96), primary_key=True),
    Column("query_id", String(96), nullable=False),
    Column("tenant_id", String(128), nullable=False),
    Column("actor_id", String(128), nullable=False),
    Column("query_hash", String(64), nullable=False),
    Column("corpus_revision", String(128), nullable=False),
    Column("filters", json_type, nullable=False),
    Column("retrieval_mode", String(16), nullable=False),
    Column("vector_status", String(32), nullable=False),
    Column("result_count", Integer, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

Index(
    "ix_v1_knowledge_retrieval_audit_tenant_created",
    retrieval_audit_table.c.tenant_id,
    retrieval_audit_table.c.created_at,
)

corpus_publications_table = Table(
    "v1_knowledge_publications",
    metadata,
    Column("scope_key", String(128), primary_key=True),
    Column("current_revision", String(128), nullable=False),
    Column("updated_by", String(128), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
    Column("publication_version", BigInteger, nullable=False),
)

__all__ = [
    "chunks_table",
    "corpus_publications_table",
    "documents_table",
    "ingestion_keys_table",
    "metadata",
    "retrieval_audit_table",
    "sources_table",
]
