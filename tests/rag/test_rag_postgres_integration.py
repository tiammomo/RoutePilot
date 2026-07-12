"""Optional real-PostgreSQL verification for lexical-only degradation."""

from __future__ import annotations

import os
import secrets
from collections.abc import Sequence

import pytest

from agent.travel_agent.rag import (
    AuthorizedKnowledgeContext,
    IngestDocumentRequest,
    PostgresKnowledgeRepository,
    ResearchQuery,
    TrustTier,
)
from agent.travel_agent.rag.models import LicenseMetadata


class IntegrationSemanticProvider:
    """Deterministic fixture that explicitly models one semantic concept."""

    model_id = "integration-semantic"
    model_version = "integration@1"
    dimension = 384
    semantic_capable = True

    @staticmethod
    def _embed(text: str) -> list[float]:
        vector = [0.0] * 384
        vector[0 if "博物馆" in text or "imperial-art" in text else 1] = 1.0
        return vector

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed(text)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_ingest_retrieve_and_cross_tenant_filter():
    dsn = os.getenv("ROUTEPILOT_RAG_TEST_DSN", "").strip()
    if not dsn:
        pytest.skip("ROUTEPILOT_RAG_TEST_DSN is not configured")
    repository = PostgresKnowledgeRepository.from_database_url(dsn)
    token = secrets.token_hex(6)
    admin = AuthorizedKnowledgeContext(
        tenant_id=f"tenant-a-{token}",
        actor_id="admin",
        roles=frozenset({"tenant_admin"}),
    )
    request = IngestDocumentRequest(
        canonical_source_uri=f"https://travel.example.com/integration/{token}",
        source_type="official_policy",
        source_version="v1",
        title="集成测试故宫政策",
        content=f"故宫预约集成测试证据 {token}",
        corpus_revision=f"revision-{token}",
        trust_tier=TrustTier.OFFICIAL,
        license=LicenseMetadata(
            license_id="integration-test",
            usage_policy="Test-only indexing.",
        ),
    )
    try:
        ingested = await repository.ingest(
            admin,
            request,
            idempotency_key=f"integration-{token}",
        )
        query = ResearchQuery(
            query=f"故宫 预约 {token}",
            corpus_revision=f"revision-{token}",
        )
        own = await repository.retrieve(
            AuthorizedKnowledgeContext(
                tenant_id=admin.tenant_id,
                actor_id="viewer-a",
                roles=frozenset({"viewer"}),
            ),
            query,
        )
        other = await repository.retrieve(
            AuthorizedKnowledgeContext(
                tenant_id=f"tenant-b-{token}",
                actor_id="viewer-b",
                roles=frozenset({"viewer"}),
            ),
            query,
        )
    finally:
        await repository.close()

    assert ingested.vector_status == "disabled"
    assert ingested.vector_indexed is False
    assert len(own.items) == 1
    assert own.items[0].source_uri == request.canonical_source_uri
    assert own.trace.retrieval_mode == "lexical"
    assert own.trace.vector_status == "disabled"
    assert other.items == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_pgvector_hybrid_retrieval_when_extension_is_available():
    dsn = os.getenv("ROUTEPILOT_RAG_TEST_DSN", "").strip()
    if not dsn:
        pytest.skip("ROUTEPILOT_RAG_TEST_DSN is not configured")
    repository = PostgresKnowledgeRepository.from_database_url(
        dsn,
        embedding_provider=IntegrationSemanticProvider(),
    )
    token = secrets.token_hex(6)
    admin = AuthorizedKnowledgeContext(
        tenant_id=f"vector-tenant-{token}",
        actor_id="admin",
        roles=frozenset({"tenant_admin"}),
    )
    request = IngestDocumentRequest(
        canonical_source_uri=f"https://travel.example.com/vector/{token}",
        source_type="museum_guide",
        source_version="v1",
        title="皇家文化场馆",
        content="这是一座重要的皇家博物馆。",
        corpus_revision=f"vector-revision-{token}",
        trust_tier=TrustTier.OFFICIAL,
        license=LicenseMetadata(
            license_id="integration-test",
            usage_policy="Test-only indexing.",
        ),
    )
    try:
        ingested = await repository.ingest(
            admin,
            request,
            idempotency_key=f"vector-integration-{token}",
        )
        if ingested.vector_status == "unavailable":
            pytest.skip("pgvector side table is unavailable")
        result = await repository.retrieve(
            AuthorizedKnowledgeContext(
                tenant_id=admin.tenant_id,
                actor_id="research-agent",
                roles=frozenset({"research_agent"}),
            ),
            ResearchQuery(
                query="imperial-art",
                corpus_revision=f"vector-revision-{token}",
            ),
        )
        hidden = await repository.retrieve(
            AuthorizedKnowledgeContext(
                tenant_id=f"other-vector-tenant-{token}",
                actor_id="research-agent",
                roles=frozenset({"research_agent"}),
            ),
            ResearchQuery(
                query="imperial-art",
                corpus_revision=f"vector-revision-{token}",
            ),
        )
    finally:
        await repository.close()

    assert ingested.vector_indexed is True
    assert ingested.vector_status == "indexed"
    assert result.trace.retrieval_mode == "hybrid"
    assert result.trace.vector_status == "used"
    assert len(result.items) == 1
    assert result.items[0].matched_by == ["vector"]
    assert hidden.items == []
