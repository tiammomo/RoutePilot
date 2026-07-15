"""Quality gates for checksum-bound curated knowledge releases."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from agent.travel_agent.rag import (
    AuthorizedKnowledgeContext,
    InMemoryKnowledgeRepository,
    KnowledgeBundleError,
    ResearchQuery,
    RetrievalFilters,
    VisibilityScope,
    ingestion_idempotency_key,
    load_knowledge_bundle,
)
from agent.travel_agent.runtime_v2.a2a_executors import DEFAULT_RAG_CORPUS_REVISION
from scripts.v1_knowledge_base import apply_bundle, bundle_plan, verify_bundle

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
BUNDLE_ROOT = (
    REPOSITORY_ROOT
    / "agent/travel_agent/rag/curated/routepilot-travel-basics-zh"
)
MANIFEST = BUNDLE_ROOT / "manifest.json"


def test_builtin_bundle_is_checksum_bound_reviewed_and_replay_stable() -> None:
    bundle = load_knowledge_bundle(MANIFEST)

    assert bundle.manifest.bundle_id == "routepilot-travel-basics-zh"
    assert bundle.manifest.corpus_revision == DEFAULT_RAG_CORPUS_REVISION
    assert bundle.manifest.default_visibility_scope is VisibilityScope.PUBLIC
    assert len(bundle.documents) == 18
    assert len(bundle.manifest.smoke_queries) == 36
    assert len(bundle.release_digest) == 64
    assert len(
        {ingestion_idempotency_key(bundle, document.document_key) for document in bundle.documents}
    ) == len(bundle.documents)
    assert all(document.request.license.license_id == "MIT" for document in bundle.documents)
    assert all(document.request.metadata["review"]["status"] == "approved" for document in bundle.documents)
    regional = [
        document
        for document in bundle.documents
        if document.request.metadata.get("fact_class") == "regional_guide"
    ]
    assert len(regional) == 12
    assert all(len(document.request.metadata["upstream_sources"]) >= 1 for document in regional)
    assert bundle_plan(bundle)["document_count"] == 18


def test_bundle_rejects_unreviewed_content_drift(tmp_path: Path) -> None:
    copied = tmp_path / "bundle"
    shutil.copytree(BUNDLE_ROOT, copied)
    content = copied / "documents/accommodation-choice.md"
    content.write_text(content.read_text(encoding="utf-8") + "\n未经复核的变化。\n", encoding="utf-8")

    with pytest.raises(KnowledgeBundleError, match="checksum mismatch"):
        load_knowledge_bundle(copied / "manifest.json")


def test_bundle_rejects_regional_guide_without_upstream_provenance(tmp_path: Path) -> None:
    copied = tmp_path / "bundle"
    shutil.copytree(BUNDLE_ROOT, copied)
    manifest_path = copied / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    regional = next(
        document
        for document in manifest["documents"]
        if document["document_key"] == "region-beijing"
    )
    regional["upstream_sources"] = []
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(KnowledgeBundleError, match="upstream source"):
        load_knowledge_bundle(manifest_path)


@pytest.mark.asyncio
async def test_builtin_bundle_fixed_queries_recall_the_reviewed_document() -> None:
    bundle = load_knowledge_bundle(MANIFEST)
    repository = InMemoryKnowledgeRepository()
    admin = AuthorizedKnowledgeContext(
        tenant_id="knowledge-quality",
        actor_id="knowledge-admin",
        roles=frozenset({"admin"}),
    )
    for document in bundle.documents:
        result = await repository.ingest(
            admin,
            document.request,
            idempotency_key=ingestion_idempotency_key(bundle, document.document_key),
        )
        assert result.status.value == "published"
        assert result.chunk_count > 0

    failures: dict[str, list[str]] = {}
    for smoke_query in bundle.manifest.smoke_queries:
        expected = bundle.document(smoke_query.expected_document_key)
        result = await repository.retrieve(
            admin,
            ResearchQuery(
                query=smoke_query.query,
                claim_scope=smoke_query.claim_scope,
                corpus_revision=bundle.manifest.corpus_revision,
                filters=RetrievalFilters(languages=[expected.request.language]),
                top_k=10,
                score_threshold=0.05,
            ),
        )
        returned = [item.source_uri for item in result.items]
        if expected.request.canonical_source_uri not in returned:
            failures[smoke_query.query] = returned
        assert all(item.license_id == "MIT" for item in result.items)
        assert all(item.content_taint == "untrusted_evidence" for item in result.items)

    assert failures == {}
    await repository.close()


def test_bundle_tool_applies_without_logging_content_and_verifies_queries() -> None:
    bundle = load_knowledge_bundle(MANIFEST, visibility_scope=VisibilityScope.TENANT)
    calls: list[dict] = []

    def fake_request(**kwargs):
        calls.append(kwargs)
        if kwargs["url"].endswith("documents:ingest"):
            return {
                "document_id": f"doc-{len(calls)}",
                "status": "published",
                "chunk_count": 1,
                "vector_status": "disabled",
                "idempotent_replay": False,
                "content_hash": "0" * 64,
                "source_id": "source-test",
                "vector_indexed": False,
            }
        query = kwargs["payload"]["query"]
        smoke = next(item for item in bundle.manifest.smoke_queries if item.query == query)
        expected = bundle.document(smoke.expected_document_key)
        return {
            "items": [{"source_uri": expected.request.canonical_source_uri}],
            "trace": {"retrieval_mode": "lexical"},
        }

    applied = apply_bundle(
        bundle,
        api_url="http://127.0.0.1:38083/api/v1",
        token="restricted-test-token",
        request_json=fake_request,
    )
    verified = verify_bundle(
        bundle,
        api_url="http://127.0.0.1:38083/api/v1",
        token="restricted-test-token",
        request_json=fake_request,
    )

    assert len(applied["documents"]) == 18
    assert verified["passed"] is True
    assert verified["passed_queries"] == 36
    ingest_calls = [call for call in calls if call["url"].endswith("documents:ingest")]
    assert all(call["headers"]["Idempotency-Key"].startswith("knowledge-bundle-") for call in ingest_calls)
    safe_output = json.dumps(applied, ensure_ascii=False)
    assert "旅行回答的首要目标" not in safe_output
