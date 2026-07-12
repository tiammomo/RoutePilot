"""Fixed-corpus quality gate for hybrid retrieval and citation provenance."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta

import pytest

from agent.travel_agent.rag import (
    AuthorizedKnowledgeContext,
    InMemoryKnowledgeRepository,
    IngestDocumentRequest,
    ResearchQuery,
    TrustTier,
    VisibilityScope,
)
from agent.travel_agent.rag.models import LicenseMetadata, utc_now


CORPUS_REVISION = "rag-quality-golden-2026-07"
GOLDEN: tuple[tuple[str, str, str], ...] = (
    (
        "紫禁城哪天不开放",
        "https://knowledge.routepilot.test/beijing/forbidden-city-hours",
        "故宫博物院每周一闭馆；法定节假日安排以官方公告为准。",
    ),
    (
        "轮椅游览皇家园林怎么走",
        "https://knowledge.routepilot.test/beijing/summer-palace-accessibility",
        "颐和园东宫门设有无障碍入口，轮椅游客可优先选择平缓的昆明湖东岸路线。",
    ),
    (
        "去长城坐哪趟火车",
        "https://knowledge.routepilot.test/beijing/badaling-rail",
        "前往八达岭长城可从北京北站乘坐市郊铁路 S2 线，班次以铁路公告为准。",
    ),
    (
        "下雨天适合看文物的室内地点",
        "https://knowledge.routepilot.test/beijing/rainy-museum",
        "首都博物馆是室内文博场馆，雨天可安排常设展览并提前预约。",
    ),
    (
        "老人想少走路看天坛",
        "https://knowledge.routepilot.test/beijing/temple-of-heaven-senior",
        "天坛公园为老人提供轮椅租借，少走路可从东门进入并缩短中轴游览范围。",
    ),
)


class GoldenSemanticEmbedding:
    """Stable semantic fixture; production provider conformance is tested separately."""

    model_id = "routepilot-rag-quality-fixture"
    model_version = "golden@2026-07"
    dimension = 384
    semantic_capable = True
    concepts = (
        ("紫禁城", "故宫", "闭馆", "不开放"),
        ("轮椅游览", "皇家园林", "颐和园", "无障碍入口", "昆明湖"),
        ("长城", "火车", "八达岭", "市郊铁路", "s2"),
        ("下雨天", "文物", "室内地点", "博物馆", "文博场馆"),
        ("老人", "少走路", "天坛", "轮椅租借"),
    )

    def _one(self, text: str) -> list[float]:
        normalized = text.casefold()
        vector = [0.0] * self.dimension
        for index, words in enumerate(self.concepts):
            if any(word in normalized for word in words):
                vector[index] = 1.0
        return vector

    async def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._one(text)


@pytest.mark.asyncio
async def test_hybrid_retrieval_meets_fixed_recall_and_citation_precision_gate() -> None:
    repository = InMemoryKnowledgeRepository(
        embedding_provider=GoldenSemanticEmbedding(),
    )
    admin = AuthorizedKnowledgeContext(
        tenant_id="quality-tenant",
        actor_id="quality-admin",
        roles=frozenset({"tenant_admin"}),
    )
    license_metadata = LicenseMetadata(
        license_id="quality-fixture-license",
        license_url="https://knowledge.routepilot.test/license",
        usage_policy="Fixed synthetic quality fixture; may index and cite.",
    )
    now = utc_now()
    for index, (_query, uri, content) in enumerate(GOLDEN):
        await repository.ingest(
            admin,
            IngestDocumentRequest(
                canonical_source_uri=uri,
                source_type="official_guide",
                source_version="2026-07-12",
                title=f"北京旅行知识 {index + 1}",
                content=content,
                visibility_scope=VisibilityScope.TENANT,
                geo_entities=["北京"],
                observed_at=now,
                valid_until=now + timedelta(days=30),
                corpus_revision=CORPUS_REVISION,
                trust_tier=TrustTier.OFFICIAL,
                license=license_metadata,
            ),
            idempotency_key=f"quality-document-{index + 1}",
        )

    recall_hits = 0
    citation_hits = 0
    rankings: dict[str, list[str]] = {}
    for query_text, expected_uri, _content in GOLDEN:
        result = await repository.retrieve(
            admin,
            ResearchQuery(
                query=query_text,
                corpus_revision=CORPUS_REVISION,
                top_k=10,
                score_threshold=0.05,
            ),
        )
        returned_uris = [item.source_uri for item in result.items]
        rankings[query_text] = returned_uris
        recall_hits += expected_uri in returned_uris
        citation_hits += bool(result.items) and result.items[0].source_uri == expected_uri
        assert result.trace.retrieval_mode == "hybrid"
        assert result.trace.vector_status == "used"
        assert all(item.license_id and item.content_hash for item in result.items)
        assert all(item.content_taint == "untrusted_evidence" for item in result.items)

    recall_at_10 = recall_hits / len(GOLDEN)
    citation_precision_at_1 = citation_hits / len(GOLDEN)
    assert recall_at_10 >= 0.90, rankings
    assert citation_precision_at_1 >= 0.85, rankings
    await repository.close()
