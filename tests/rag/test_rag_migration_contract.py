"""Static migration contract tests for lexical/vector capability fallback."""

from __future__ import annotations

from pathlib import Path


MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "deploy/migrations/versions/20260712_0006_routepilot_rag.py"
)
LIFECYCLE_MIGRATION = (
    Path(__file__).resolve().parents[2]
    / "deploy/migrations/versions/20260713_0011_knowledge_document_lifecycle.py"
)


def test_rag_migration_declares_chain_and_optional_vector_capability():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260712_0006"' in source
    assert 'down_revision = "20260712_0005"' in source
    assert "CREATE EXTENSION IF NOT EXISTS vector" in source
    assert "pgvector unavailable" in source
    assert "feature_not_supported" in source
    assert "extversion" in source
    assert "older than 0.8" in source
    assert "to_regclass" not in source  # runtime, not migration, owns capability checks


def test_rag_migration_has_provenance_gin_hnsw_and_visibility_indexes():
    source = MIGRATION.read_text(encoding="utf-8")
    for table in (
        "v1_knowledge_sources",
        "v1_knowledge_documents",
        "v1_knowledge_chunks",
        "v1_knowledge_ingestion_keys",
        "v1_knowledge_retrieval_audit",
        "v1_knowledge_publications",
    ):
        assert table in source
    assert 'postgresql_using="gin"' in source
    assert "USING hnsw" in source
    assert "vector_cosine_ops" in source
    assert "visibility_scope = 'public'" in source
    assert "visibility_scope = 'tenant'" in source
    assert "content_taint = 'untrusted_evidence'" in source


def test_rag_lifecycle_migration_adds_cas_idempotency_audit_and_rls():
    source = LIFECYCLE_MIGRATION.read_text(encoding="utf-8")
    assert 'revision = "20260713_0011"' in source
    assert 'down_revision = "20260712_0010"' in source
    assert '"version"' in source
    assert '"v1_knowledge_document_commands"' in source
    assert '"idempotency_key"' in source
    assert '"actor_id"' in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "current_setting('routepilot.tenant_id', true)" in source
