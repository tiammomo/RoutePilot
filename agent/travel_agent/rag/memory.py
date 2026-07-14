"""Concurrency-safe in-memory RAG repository for unit tests and local demos."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Literal

from .embedding import EmbeddingProvider, cosine_similarity, validate_embedding
from .models import (
    AuthorizedKnowledgeContext,
    EvidenceItem,
    EvidenceScores,
    FreshnessStatus,
    IngestDocumentRequest,
    IngestResult,
    IngestionStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeDocumentAdminView,
    KnowledgeDocumentPage,
    KnowledgeDocumentStatusCommand,
    KnowledgeDocumentStatusResult,
    RRF_LEXICAL_WEIGHT,
    RRF_VECTOR_WEIGHT,
    ResearchQuery,
    RetrievalResult,
    RetrievalTrace,
    TrustTier,
    VisibilityScope,
    freshness_status,
    new_knowledge_id,
    utc_now,
)
from .pipeline import prepare_ingestion, scope_key, sha256_text
from .ports import (
    KnowledgeAuthorizationError,
    KnowledgeConflictError,
    KnowledgeNotFoundError,
    KnowledgeVersionConflictError,
)
from .text import TravelTokenizer

_TRUST_ORDER = {
    TrustTier.OFFICIAL: 5,
    TrustTier.OPERATOR: 4,
    TrustTier.TRUSTED_MEDIA: 3,
    TrustTier.COMMUNITY: 2,
    TrustTier.USER_PRIVATE: 1,
}


@dataclass(frozen=True, slots=True)
class _IdempotencyRecord:
    request_hash: str
    result: IngestResult


@dataclass(frozen=True, slots=True)
class _Candidate:
    chunk: KnowledgeChunk
    lexical: float | None = None
    vector: float | None = None
    lexical_rank: int | None = None
    vector_rank: int | None = None


@dataclass(frozen=True, slots=True)
class _StatusIdempotencyRecord:
    request_hash: str
    result: KnowledgeDocumentStatusResult


class InMemoryKnowledgeRepository:
    """Reference behavior for isolation, idempotency, fusion, and citations."""

    def __init__(
        self,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        tokenizer: TravelTokenizer | None = None,
    ):
        self.embedding_provider = embedding_provider
        self.tokenizer = tokenizer or TravelTokenizer()
        self._lock = asyncio.Lock()
        self._sources_by_scope_uri: dict[tuple[str, str], str] = {}
        self._documents: dict[str, KnowledgeDocument] = {}
        self._chunks: dict[str, KnowledgeChunk] = {}
        self._vectors: dict[str, list[float]] = {}
        self._idempotency: dict[tuple[str, str], _IdempotencyRecord] = {}
        self._content_results: dict[tuple[str, str, str, str, str], IngestResult] = {}
        self._status_idempotency: dict[tuple[str, str], _StatusIdempotencyRecord] = {}

    @staticmethod
    def _authorize_ingest(
        context: AuthorizedKnowledgeContext,
        request: IngestDocumentRequest,
    ) -> None:
        if not context.can_manage_tenant_knowledge:
            raise KnowledgeAuthorizationError("knowledge administration role is required")
        if (
            request.visibility_scope is VisibilityScope.PUBLIC
            and not context.can_manage_public_knowledge
        ):
            raise KnowledgeAuthorizationError("global admin role is required for public knowledge")

    async def ingest(
        self,
        context: AuthorizedKnowledgeContext,
        request: IngestDocumentRequest,
        *,
        idempotency_key: str,
    ) -> IngestResult:
        """Ingest atomically and replay an identical idempotency request."""

        self._authorize_ingest(context, request)
        if not 8 <= len(idempotency_key) <= 200:
            raise ValueError("idempotency key must contain 8-200 characters")
        selected_scope = scope_key(context.tenant_id, request.visibility_scope)
        prepared_probe = prepare_ingestion(
            tenant_id=context.tenant_id,
            request=request,
            tokenizer=self.tokenizer,
        )
        key = (selected_scope, idempotency_key)
        async with self._lock:
            existing = self._idempotency.get(key)
            if existing is not None:
                if existing.request_hash != prepared_probe.request_hash:
                    raise KnowledgeConflictError(
                        "idempotency key was already used with different content"
                    )
                return existing.result.model_copy(update={"idempotent_replay": True})

            content_key = (
                selected_scope,
                request.canonical_source_uri,
                request.source_version,
                request.corpus_revision,
                prepared_probe.document.content_hash,
            )
            content_result = self._content_results.get(content_key)
            if content_result is not None:
                self._idempotency[key] = _IdempotencyRecord(
                    request_hash=prepared_probe.request_hash,
                    result=content_result,
                )
                return content_result.model_copy(update={"idempotent_replay": True})

            source_key = (selected_scope, request.canonical_source_uri)
            source_id = self._sources_by_scope_uri.get(source_key)
            prepared = prepare_ingestion(
                tenant_id=context.tenant_id,
                request=request,
                source_id=source_id,
                tokenizer=self.tokenizer,
            )
            vector_status: Literal[
                "indexed", "disabled", "unavailable", "provider_not_semantic"
            ] = "disabled"
            vectors: list[list[float]] = []
            provider = self.embedding_provider
            if provider is not None and provider.semantic_capable:
                vectors = await provider.embed_documents([chunk.content for chunk in prepared.chunks])
                vectors = [
                    validate_embedding(vector, expected_dimension=provider.dimension)
                    for vector in vectors
                ]
                if len(vectors) != len(prepared.chunks):
                    raise ValueError("embedding provider returned an unexpected vector count")
                vector_status = "indexed"
            elif provider is not None:
                vector_status = "provider_not_semantic"

            self._sources_by_scope_uri[source_key] = prepared.source.source_id
            self._documents[prepared.document.document_id] = prepared.document
            for chunk, vector in zip(prepared.chunks, vectors):
                self._chunks[chunk.chunk_id] = chunk
                self._vectors[chunk.chunk_id] = vector
            if not vectors:
                self._chunks.update({chunk.chunk_id: chunk for chunk in prepared.chunks})
            result = IngestResult(
                source_id=prepared.source.source_id,
                document_id=prepared.document.document_id,
                content_hash=prepared.document.content_hash,
                chunk_count=len(prepared.chunks),
                status=prepared.document.status,
                vector_indexed=bool(vectors),
                vector_status=vector_status,
            )
            self._idempotency[key] = _IdempotencyRecord(
                request_hash=prepared.request_hash,
                result=result,
            )
            self._content_results[content_key] = result
            return result

    @staticmethod
    def _authorize_management(context: AuthorizedKnowledgeContext) -> None:
        if not context.can_manage_tenant_knowledge:
            raise KnowledgeAuthorizationError("knowledge administration role is required")

    @staticmethod
    def _document_visible(
        context: AuthorizedKnowledgeContext,
        document: KnowledgeDocument,
    ) -> bool:
        return (
            document.visibility_scope is VisibilityScope.PUBLIC
            or document.tenant_id == context.tenant_id
        )

    def _admin_view(self, document: KnowledgeDocument) -> KnowledgeDocumentAdminView:
        return KnowledgeDocumentAdminView.model_validate(
            {
                **document.model_dump(),
                "chunk_count": sum(
                    chunk.document_id == document.document_id
                    for chunk in self._chunks.values()
                ),
            }
        )

    async def list_documents(
        self,
        context: AuthorizedKnowledgeContext,
        *,
        status: IngestionStatus | None,
        limit: int,
        cursor: str | None,
    ) -> KnowledgeDocumentPage:
        """List stable document IDs without returning stored chunk content."""

        self._authorize_management(context)
        if not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        async with self._lock:
            documents = sorted(self._documents.values(), key=lambda item: item.document_id)
            visible = [
                document
                for document in documents
                if self._document_visible(context, document)
                and (status is None or document.status is status)
                and (cursor is None or document.document_id > cursor)
            ]
            selected = visible[: limit + 1]
            items = [self._admin_view(document) for document in selected[:limit]]
        next_cursor = items[-1].document_id if len(selected) > limit and items else None
        return KnowledgeDocumentPage(items=items, next_cursor=next_cursor)

    async def get_document(
        self,
        context: AuthorizedKnowledgeContext,
        document_id: str,
    ) -> KnowledgeDocumentAdminView:
        self._authorize_management(context)
        async with self._lock:
            document = self._documents.get(document_id)
            if document is None or not self._document_visible(context, document):
                raise KnowledgeNotFoundError("knowledge document not found")
            return self._admin_view(document)

    async def change_document_status(
        self,
        context: AuthorizedKnowledgeContext,
        document_id: str,
        command: KnowledgeDocumentStatusCommand,
        *,
        idempotency_key: str,
    ) -> KnowledgeDocumentStatusResult:
        """Apply a replay-safe CAS status transition."""

        self._authorize_management(context)
        if not 8 <= len(idempotency_key) <= 200:
            raise ValueError("idempotency key must contain 8-200 characters")
        request_hash = sha256_text(command.model_dump_json())
        async with self._lock:
            document = self._documents.get(document_id)
            if document is None or not self._document_visible(context, document):
                raise KnowledgeNotFoundError("knowledge document not found")
            if (
                document.visibility_scope is VisibilityScope.PUBLIC
                and not context.can_manage_public_knowledge
            ):
                raise KnowledgeAuthorizationError(
                    "global admin role is required for public knowledge"
                )
            selected_scope = scope_key(context.tenant_id, document.visibility_scope)
            key = (selected_scope, idempotency_key)
            existing = self._status_idempotency.get(key)
            if existing is not None:
                if existing.request_hash != request_hash:
                    raise KnowledgeConflictError(
                        "idempotency key was already used with a different command"
                    )
                return existing.result.model_copy(update={"idempotent_replay": True})
            if document.version != command.expected_version:
                raise KnowledgeVersionConflictError(
                    "knowledge document version changed; refresh and retry",
                    current_version=document.version,
                )
            updated = document
            if document.status is not command.target_status:
                updated = document.model_copy(
                    update={
                        "status": command.target_status,
                        "quarantine_reason": (
                            None
                            if command.target_status is IngestionStatus.PUBLISHED
                            else command.reason
                        ),
                        "version": document.version + 1,
                        "updated_at": utc_now(),
                    }
                )
                self._documents[document_id] = updated
            result = KnowledgeDocumentStatusResult(document=self._admin_view(updated))
            self._status_idempotency[key] = _StatusIdempotencyRecord(
                request_hash=request_hash,
                result=result,
            )
            return result

    async def retrieve(
        self,
        context: AuthorizedKnowledgeContext,
        query: ResearchQuery,
    ) -> RetrievalResult:
        """Filter before ranking, fuse lexical/vector ranks, and de-duplicate."""

        query_id = new_knowledge_id("qry")
        query_hash = sha256_text(query.query)
        query_terms = set(self.tokenizer.tokenize(query.query))
        async with self._lock:
            eligible = [
                chunk
                for chunk in self._chunks.values()
                if self._documents[chunk.document_id].status is IngestionStatus.PUBLISHED
                and self._eligible(chunk, context=context, query=query)
            ]
            vectors = dict(self._vectors)

        lexical_scored: list[tuple[KnowledgeChunk, float]] = []
        if query_terms:
            for chunk in eligible:
                chunk_terms = set(chunk.lexical_terms.split())
                overlap = len(query_terms.intersection(chunk_terms))
                if overlap:
                    score = min(1.0, overlap / max(1, len(query_terms)))
                    lexical_scored.append((chunk, score))
        lexical_scored.sort(
            key=lambda item: (item[1], _TRUST_ORDER[item[0].trust_tier], item[0].chunk_id),
            reverse=True,
        )

        vector_status: Literal["used", "disabled", "unavailable", "provider_not_semantic"]
        vector_status = "disabled"
        vector_scored: list[tuple[KnowledgeChunk, float]] = []
        provider = self.embedding_provider
        if provider is not None and provider.semantic_capable and vectors:
            query_vector = validate_embedding(
                await provider.embed_query(query.query),
                expected_dimension=provider.dimension,
            )
            for chunk in eligible:
                vector = vectors.get(chunk.chunk_id)
                if vector is not None:
                    similarity = max(0.0, cosine_similarity(query_vector, vector))
                    if similarity > 0.0:
                        vector_scored.append((chunk, similarity))
            vector_scored.sort(key=lambda item: (item[1], item[0].chunk_id), reverse=True)
            vector_status = "used"
        elif provider is not None and not provider.semantic_capable:
            vector_status = "provider_not_semantic"
        elif provider is not None:
            vector_status = "unavailable"

        candidates = self._fuse(lexical_scored, vector_scored)
        evidence: list[EvidenceItem] = []
        seen_hashes: set[str] = set()
        for candidate, fused in candidates:
            component_score = max(candidate.lexical or 0.0, candidate.vector or 0.0)
            if (
                fused < query.score_threshold
                or component_score < query.score_threshold
                or candidate.chunk.content_hash in seen_hashes
            ):
                continue
            seen_hashes.add(candidate.chunk.content_hash)
            evidence.append(self._to_evidence(candidate, query=query, fused=fused))
            if len(evidence) >= query.top_k:
                break

        retrieval_mode: Literal["lexical", "hybrid"] = (
            "hybrid" if vector_status == "used" else "lexical"
        )
        degraded_reason = None
        if vector_status == "provider_not_semantic":
            degraded_reason = "configured embedding provider is explicitly non-semantic"
        elif vector_status == "unavailable":
            degraded_reason = "semantic vectors are unavailable; lexical results only"
        elif vector_status == "disabled":
            degraded_reason = "no semantic embedding provider is configured"
        trace = RetrievalTrace(
            query_id=query_id,
            query_hash=query_hash,
            corpus_revision=query.corpus_revision,
            tokenizer_version=self.tokenizer.version,
            embedding_model_version=(provider.model_version if provider else None),
            retrieval_mode=retrieval_mode,
            vector_status=vector_status,
            degraded_reason=degraded_reason,
            lexical_candidates=len(lexical_scored),
            vector_candidates=len(vector_scored),
            returned_items=len(evidence),
        )
        return RetrievalResult(
            query_id=query_id,
            corpus_revision=query.corpus_revision,
            items=evidence,
            trace=trace,
        )

    def _eligible(
        self,
        chunk: KnowledgeChunk,
        *,
        context: AuthorizedKnowledgeContext,
        query: ResearchQuery,
    ) -> bool:
        if chunk.visibility_scope is VisibilityScope.TENANT and chunk.tenant_id != context.tenant_id:
            return False
        if chunk.corpus_revision != query.corpus_revision:
            return False
        if chunk.tokenizer_version != self.tokenizer.version:
            return False
        filters = query.filters
        if filters.languages and chunk.language not in filters.languages:
            return False
        if filters.source_types and chunk.source_type not in filters.source_types:
            return False
        if filters.trust_tiers and chunk.trust_tier not in filters.trust_tiers:
            return False
        if filters.geo_entities and not set(filters.geo_entities).intersection(chunk.geo_entities):
            return False
        if filters.tags and not set(filters.tags).intersection(chunk.tags):
            return False
        fresh = freshness_status(
            valid_from=chunk.valid_from,
            valid_until=chunk.valid_until,
            at=filters.valid_at,
        )
        return filters.include_stale or fresh not in {
            FreshnessStatus.STALE,
            FreshnessStatus.NOT_YET_VALID,
        }

    @staticmethod
    def _fuse(
        lexical: list[tuple[KnowledgeChunk, float]],
        vector: list[tuple[KnowledgeChunk, float]],
    ) -> list[tuple[_Candidate, float]]:
        """Fuse rankings using normalized weighted Reciprocal Rank Fusion."""

        by_id: dict[str, _Candidate] = {}
        for rank, (chunk, score) in enumerate(lexical, start=1):
            by_id[chunk.chunk_id] = _Candidate(
                chunk=chunk,
                lexical=score,
                lexical_rank=rank,
            )
        for rank, (chunk, score) in enumerate(vector, start=1):
            previous = by_id.get(chunk.chunk_id)
            by_id[chunk.chunk_id] = _Candidate(
                chunk=chunk,
                lexical=previous.lexical if previous else None,
                vector=score,
                lexical_rank=previous.lexical_rank if previous else None,
                vector_rank=rank,
            )
        maximum = (
            RRF_LEXICAL_WEIGHT + (RRF_VECTOR_WEIGHT if vector else 0.0)
        ) / 61.0
        fused: list[tuple[_Candidate, float]] = []
        for candidate in by_id.values():
            raw = 0.0
            if candidate.lexical_rank is not None:
                raw += RRF_LEXICAL_WEIGHT / (60 + candidate.lexical_rank)
            if candidate.vector_rank is not None:
                raw += RRF_VECTOR_WEIGHT / (60 + candidate.vector_rank)
            normalized = min(1.0, raw / maximum) if maximum else 0.0
            fused.append((candidate, normalized))
        fused.sort(
            key=lambda item: (
                item[1],
                _TRUST_ORDER[item[0].chunk.trust_tier],
                item[0].chunk.chunk_id,
            ),
            reverse=True,
        )
        return fused

    @staticmethod
    def _to_evidence(
        candidate: _Candidate,
        *,
        query: ResearchQuery,
        fused: float,
    ) -> EvidenceItem:
        chunk = candidate.chunk
        matched_by: list[Literal["lexical", "vector"]] = []
        if candidate.lexical_rank is not None:
            matched_by.append("lexical")
        if candidate.vector_rank is not None:
            matched_by.append("vector")
        return EvidenceItem(
            evidence_id=new_knowledge_id("ev"),
            chunk_id=chunk.chunk_id,
            document_id=chunk.document_id,
            source_id=chunk.source_id,
            content_hash=chunk.content_hash,
            claim_scope=query.claim_scope,
            snippet=chunk.content[:2_000],
            source_uri=chunk.canonical_source_uri,
            source_title=chunk.source_title,
            source_type=chunk.source_type,
            source_version=chunk.source_version,
            published_at=chunk.published_at,
            observed_at=chunk.observed_at,
            retrieved_at=utc_now(),
            valid_until=chunk.valid_until,
            freshness_status=freshness_status(
                valid_from=chunk.valid_from,
                valid_until=chunk.valid_until,
                at=query.filters.valid_at,
            ),
            trust_tier=chunk.trust_tier,
            license_id=chunk.license.license_id,
            visibility_scope=chunk.visibility_scope,
            corpus_revision=chunk.corpus_revision,
            scores=EvidenceScores(
                lexical=candidate.lexical,
                vector=candidate.vector,
                fused=fused,
            ),
            matched_by=matched_by,
            injection_suspected=chunk.injection_suspected,
        )

    async def close(self) -> None:
        """Release an optional embedding client used by this repository."""

        close = getattr(self.embedding_provider, "close", None)
        if close is not None:
            await close()

    async def unsafe_chunk_count_for_test(self, *, tenant_id: str) -> int:
        """Expose only a scoped count for white-box isolation tests."""

        async with self._lock:
            return sum(
                1
                for chunk in self._chunks.values()
                if chunk.tenant_id == tenant_id or chunk.visibility_scope is VisibilityScope.PUBLIC
            )


__all__ = ["InMemoryKnowledgeRepository"]
