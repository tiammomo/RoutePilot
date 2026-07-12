"""PostgreSQL FTS + optional pgvector implementation of the knowledge port."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Literal, cast

from sqlalchemy import func, insert, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from .embedding import EmbeddingProvider, validate_embedding
from .models import (
    AuthorizedKnowledgeContext,
    EvidenceItem,
    EvidenceScores,
    IngestDocumentRequest,
    IngestResult,
    IngestionStatus,
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
from .pipeline import PreparedIngestion, prepare_ingestion, scope_key, sha256_text
from .ports import KnowledgeAuthorizationError, KnowledgeConflictError
from .sql_tables import (
    chunks_table,
    documents_table,
    ingestion_keys_table,
    retrieval_audit_table,
    sources_table,
)
from .text import TravelTokenizer

logger = logging.getLogger(__name__)
PGVECTOR_DIMENSION = 384
_TRUST_ORDER = {
    TrustTier.OFFICIAL.value: 5,
    TrustTier.OPERATOR.value: 4,
    TrustTier.TRUSTED_MEDIA.value: 3,
    TrustTier.COMMUNITY.value: 2,
    TrustTier.USER_PRIVATE.value: 1,
}


def normalize_async_database_url(database_url: str) -> str:
    """Normalize a PostgreSQL DSN for SQLAlchemy's psycopg async dialect."""

    normalized = str(database_url or "").strip()
    if normalized.startswith("postgres://"):
        normalized = normalized.replace("postgres://", "postgresql://", 1)
    if normalized.startswith("postgresql://"):
        normalized = normalized.replace("postgresql://", "postgresql+psycopg://", 1)
    if not normalized.startswith("postgresql+psycopg://"):
        raise ValueError("RAG storage requires a PostgreSQL psycopg DSN")
    return normalized


@dataclass(slots=True)
class _RankedRow:
    """One database candidate with component ranks and scores."""

    row: dict[str, Any]
    lexical_score: float | None = None
    vector_score: float | None = None
    lexical_rank: int | None = None
    vector_rank: int | None = None


class PostgresKnowledgeRepository:
    """Tenant-first PostgreSQL retrieval with explicit lexical degradation."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        embedding_provider: EmbeddingProvider | None = None,
        tokenizer: TravelTokenizer | None = None,
    ):
        if (
            embedding_provider is not None
            and embedding_provider.semantic_capable
            and embedding_provider.dimension != PGVECTOR_DIMENSION
        ):
            raise ValueError(
                f"V1 pgvector index requires {PGVECTOR_DIMENSION}-dimension embeddings"
            )
        self.engine = engine
        self.embedding_provider = embedding_provider
        self.tokenizer = tokenizer or TravelTokenizer()

    @classmethod
    def from_database_url(
        cls,
        database_url: str,
        *,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> "PostgresKnowledgeRepository":
        """Build a pooled repository without creating schema at runtime."""

        engine = create_async_engine(
            normalize_async_database_url(database_url),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        return cls(engine, embedding_provider=embedding_provider)

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

    @staticmethod
    async def _vector_table_available(connection: AsyncConnection) -> bool:
        value = await connection.scalar(
            text("SELECT to_regclass('public.v1_knowledge_chunk_vectors') IS NOT NULL")
        )
        return bool(value)

    @staticmethod
    async def _scope_tenant(
        connection: AsyncConnection,
        context: AuthorizedKnowledgeContext,
    ) -> None:
        """Set transaction-local RLS context so pooled connections cannot leak scope."""

        await connection.execute(
            select(func.set_config("routepilot.tenant_id", context.tenant_id, True))
        )

    async def ingest(
        self,
        context: AuthorizedKnowledgeContext,
        request: IngestDocumentRequest,
        *,
        idempotency_key: str,
    ) -> IngestResult:
        """Atomically ingest with advisory-lock protected idempotency/content dedupe."""

        self._authorize_ingest(context, request)
        if not 8 <= len(idempotency_key) <= 200:
            raise ValueError("idempotency key must contain 8-200 characters")
        prepared_probe = prepare_ingestion(
            tenant_id=context.tenant_id,
            request=request,
            tokenizer=self.tokenizer,
        )
        selected_scope = scope_key(context.tenant_id, request.visibility_scope)
        provider = self.embedding_provider
        async with self.engine.connect() as capability_connection:
            vector_table_available = await self._vector_table_available(capability_connection)

        vector_status: Literal[
            "indexed", "disabled", "unavailable", "provider_not_semantic"
        ] = "disabled"
        prepared_vectors: list[list[float]] = []
        if provider is not None and provider.semantic_capable and vector_table_available:
            prepared_vectors = await provider.embed_documents(
                [chunk.content for chunk in prepared_probe.chunks]
            )
            prepared_vectors = [
                validate_embedding(vector, expected_dimension=PGVECTOR_DIMENSION)
                for vector in prepared_vectors
            ]
            if len(prepared_vectors) != len(prepared_probe.chunks):
                raise ValueError("embedding provider returned an unexpected vector count")
            vector_status = "indexed"
        elif provider is not None and not provider.semantic_capable:
            vector_status = "provider_not_semantic"
        elif provider is not None:
            vector_status = "unavailable"

        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, context)
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {"lock_key": f"rag-idem:{selected_scope}:{idempotency_key}"},
            )
            idem_row = (
                await connection.execute(
                    select(
                        ingestion_keys_table.c.request_hash,
                        ingestion_keys_table.c.document_id,
                    ).where(
                        ingestion_keys_table.c.scope_key == selected_scope,
                        ingestion_keys_table.c.idempotency_key == idempotency_key,
                    )
                )
            ).mappings().one_or_none()
            if idem_row is not None:
                if idem_row["request_hash"] != prepared_probe.request_hash:
                    raise KnowledgeConflictError(
                        "idempotency key was already used with different content"
                    )
                return await self._existing_result(
                    connection,
                    document_id=str(idem_row["document_id"]),
                    vector_table_available=vector_table_available,
                    vector_status=vector_status,
                    idempotent_replay=True,
                )

            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
                {
                    "lock_key": (
                        f"rag-content:{selected_scope}:{request.canonical_source_uri}:"
                        f"{request.source_version}:{request.corpus_revision}:"
                        f"{prepared_probe.document.content_hash}"
                    )
                },
            )
            source_id = await self._upsert_source(
                connection,
                selected_scope=selected_scope,
                prepared=prepared_probe,
            )
            existing_document_id = await connection.scalar(
                select(documents_table.c.document_id).where(
                    documents_table.c.scope_key == selected_scope,
                    documents_table.c.source_id == source_id,
                    documents_table.c.source_version == request.source_version,
                    documents_table.c.content_hash == prepared_probe.document.content_hash,
                    documents_table.c.corpus_revision == request.corpus_revision,
                )
            )
            if existing_document_id is not None:
                await self._insert_idempotency(
                    connection,
                    selected_scope=selected_scope,
                    idempotency_key=idempotency_key,
                    request_hash=prepared_probe.request_hash,
                    document_id=str(existing_document_id),
                )
                return await self._existing_result(
                    connection,
                    document_id=str(existing_document_id),
                    vector_table_available=vector_table_available,
                    vector_status=vector_status,
                    idempotent_replay=True,
                )

            prepared = prepare_ingestion(
                tenant_id=context.tenant_id,
                request=request,
                source_id=source_id,
                document_id=prepared_probe.document.document_id,
                tokenizer=self.tokenizer,
            )
            # Chunk contents/order are deterministic, so vectors prepared before
            # opening the transaction remain aligned with these new chunk IDs.
            await connection.execute(
                insert(documents_table).values(**self._document_values(prepared, selected_scope))
            )
            await connection.execute(
                insert(chunks_table),
                [self._chunk_values(chunk, selected_scope) for chunk in prepared.chunks],
            )
            if prepared_vectors:
                for chunk, vector in zip(prepared.chunks, prepared_vectors):
                    await connection.execute(
                        text(
                            "INSERT INTO v1_knowledge_chunk_vectors "
                            "(chunk_id, tenant_id, visibility_scope, embedding, "
                            "embedding_model_id, embedding_model_version, created_at) "
                            "VALUES (:chunk_id, :tenant_id, :visibility_scope, "
                            "CAST(:embedding AS vector), :model_id, :model_version, :created_at)"
                        ),
                        {
                            "chunk_id": chunk.chunk_id,
                            "tenant_id": chunk.tenant_id,
                            "visibility_scope": chunk.visibility_scope.value,
                            "embedding": json.dumps(vector, separators=(",", ":")),
                            "model_id": provider.model_id if provider else "",
                            "model_version": provider.model_version if provider else "",
                            "created_at": utc_now(),
                        },
                    )
            await self._insert_idempotency(
                connection,
                selected_scope=selected_scope,
                idempotency_key=idempotency_key,
                request_hash=prepared.request_hash,
                document_id=prepared.document.document_id,
            )
            return IngestResult(
                source_id=source_id,
                document_id=prepared.document.document_id,
                content_hash=prepared.document.content_hash,
                chunk_count=len(prepared.chunks),
                status=prepared.document.status,
                vector_indexed=bool(prepared_vectors),
                vector_status=vector_status,
            )

    @staticmethod
    async def _upsert_source(
        connection: AsyncConnection,
        *,
        selected_scope: str,
        prepared: PreparedIngestion,
    ) -> str:
        source = prepared.source
        statement = (
            pg_insert(sources_table)
            .values(
                source_id=source.source_id,
                tenant_id=source.tenant_id,
                scope_key=selected_scope,
                visibility_scope=source.visibility_scope.value,
                canonical_source_uri=source.canonical_source_uri,
                source_type=source.source_type,
                trust_tier=source.trust_tier.value,
                license_id=source.license.license_id,
                license_url=source.license.license_url,
                usage_policy=source.license.usage_policy,
                retention_days=source.license.retention_days,
                created_at=source.created_at,
                updated_at=source.updated_at,
            )
            .on_conflict_do_update(
                constraint="uq_v1_knowledge_sources_scope_uri",
                set_={
                    "source_type": source.source_type,
                    "trust_tier": source.trust_tier.value,
                    "license_id": source.license.license_id,
                    "license_url": source.license.license_url,
                    "usage_policy": source.license.usage_policy,
                    "retention_days": source.license.retention_days,
                    "updated_at": utc_now(),
                },
            )
            .returning(sources_table.c.source_id)
        )
        return str((await connection.execute(statement)).scalar_one())

    @staticmethod
    def _document_values(prepared: PreparedIngestion, selected_scope: str) -> dict[str, Any]:
        document = prepared.document
        return {
            "document_id": document.document_id,
            "source_id": document.source_id,
            "tenant_id": document.tenant_id,
            "scope_key": selected_scope,
            "visibility_scope": document.visibility_scope.value,
            "source_version": document.source_version,
            "title": document.title,
            "language": document.language,
            "geo_entities": document.geo_entities,
            "tags": document.tags,
            "published_at": document.published_at,
            "observed_at": document.observed_at,
            "valid_from": document.valid_from,
            "valid_until": document.valid_until,
            "content_hash": document.content_hash,
            "parser_version": document.parser_version,
            "chunker_version": document.chunker_version,
            "tokenizer_version": document.tokenizer_version,
            "corpus_revision": document.corpus_revision,
            "trust_tier": document.trust_tier.value,
            "license_id": document.license.license_id,
            "license_url": document.license.license_url,
            "usage_policy": document.license.usage_policy,
            "retention_days": document.license.retention_days,
            "status": document.status.value,
            "quarantine_reason": document.quarantine_reason,
            "injection_suspected": document.injection_suspected,
            "metadata": document.metadata,
            "created_at": document.created_at,
            "updated_at": document.updated_at,
        }

    @staticmethod
    def _chunk_values(chunk: Any, selected_scope: str) -> dict[str, Any]:
        return {
            "chunk_id": chunk.chunk_id,
            "document_id": chunk.document_id,
            "source_id": chunk.source_id,
            "tenant_id": chunk.tenant_id,
            "scope_key": selected_scope,
            "visibility_scope": chunk.visibility_scope.value,
            "ordinal": chunk.ordinal,
            "content": chunk.content,
            "content_hash": chunk.content_hash,
            "token_count": chunk.token_count,
            "lexical_terms": chunk.lexical_terms,
            "canonical_source_uri": chunk.canonical_source_uri,
            "source_version": chunk.source_version,
            "source_type": chunk.source_type,
            "source_title": chunk.source_title,
            "language": chunk.language,
            "geo_entities": chunk.geo_entities,
            "tags": chunk.tags,
            "published_at": chunk.published_at,
            "observed_at": chunk.observed_at,
            "valid_from": chunk.valid_from,
            "valid_until": chunk.valid_until,
            "corpus_revision": chunk.corpus_revision,
            "tokenizer_version": chunk.tokenizer_version,
            "trust_tier": chunk.trust_tier.value,
            "license_id": chunk.license.license_id,
            "license_url": chunk.license.license_url,
            "usage_policy": chunk.license.usage_policy,
            "retention_days": chunk.license.retention_days,
            "injection_suspected": chunk.injection_suspected,
            "content_taint": chunk.content_taint,
        }

    @staticmethod
    async def _insert_idempotency(
        connection: AsyncConnection,
        *,
        selected_scope: str,
        idempotency_key: str,
        request_hash: str,
        document_id: str,
    ) -> None:
        await connection.execute(
            insert(ingestion_keys_table).values(
                scope_key=selected_scope,
                idempotency_key=idempotency_key,
                request_hash=request_hash,
                document_id=document_id,
                created_at=utc_now(),
            )
        )

    @staticmethod
    async def _existing_result(
        connection: AsyncConnection,
        *,
        document_id: str,
        vector_table_available: bool,
        vector_status: Literal[
            "indexed", "disabled", "unavailable", "provider_not_semantic"
        ],
        idempotent_replay: bool,
    ) -> IngestResult:
        row = (
            await connection.execute(
                select(
                    documents_table.c.source_id,
                    documents_table.c.content_hash,
                    documents_table.c.status,
                    func.count(chunks_table.c.chunk_id).label("chunk_count"),
                )
                .join(chunks_table, chunks_table.c.document_id == documents_table.c.document_id)
                .where(documents_table.c.document_id == document_id)
                .group_by(
                    documents_table.c.source_id,
                    documents_table.c.content_hash,
                    documents_table.c.status,
                )
            )
        ).mappings().one()
        vector_count = 0
        if vector_table_available:
            vector_count = int(
                await connection.scalar(
                    text(
                        "SELECT count(*) FROM v1_knowledge_chunk_vectors v "
                        "JOIN v1_knowledge_chunks c ON c.chunk_id = v.chunk_id "
                        "WHERE c.document_id = :document_id"
                    ),
                    {"document_id": document_id},
                )
                or 0
            )
        replay_status = "indexed" if vector_count else vector_status
        return IngestResult(
            source_id=str(row["source_id"]),
            document_id=document_id,
            content_hash=str(row["content_hash"]),
            chunk_count=int(row["chunk_count"]),
            status=IngestionStatus(str(row["status"])),
            idempotent_replay=idempotent_replay,
            vector_indexed=vector_count > 0,
            vector_status=cast(Any, replay_status),
        )

    async def retrieve(
        self,
        context: AuthorizedKnowledgeContext,
        query: ResearchQuery,
    ) -> RetrievalResult:
        """Retrieve lexical candidates and add real vector ranks only when available."""

        query_id = new_knowledge_id("qry")
        query_hash = sha256_text(query.query)
        tokens = self.tokenizer.tokenize(query.query)
        limit = min(80, max(40, query.top_k * 4))
        conditions, params = self._filter_sql(context, query)
        params["limit"] = limit
        lexical_rows: list[dict[str, Any]] = []
        if tokens:
            lexical_query = " OR ".join(tokens)
            lexical_sql = text(
                f"""
                SELECT c.*,
                       ts_rank_cd(c.search_document,
                           websearch_to_tsquery('simple', :lexical_query)) AS lexical_score
                  FROM v1_knowledge_chunks c
                  JOIN v1_knowledge_documents d ON d.document_id = c.document_id
                 WHERE {conditions}
                   AND d.status = 'published'
                   AND c.search_document @@ websearch_to_tsquery('simple', :lexical_query)
                 ORDER BY lexical_score DESC, c.chunk_id
                 LIMIT :limit
                """
            )
            async with self.engine.connect() as connection:
                await self._scope_tenant(connection, context)
                result = await connection.execute(
                    lexical_sql,
                    {**params, "lexical_query": lexical_query},
                )
                lexical_rows = [dict(row) for row in result.mappings().all()]

        provider = self.embedding_provider
        vector_rows: list[dict[str, Any]] = []
        vector_status: Literal["used", "disabled", "unavailable", "provider_not_semantic"]
        vector_status = "disabled"
        vector_capable = False
        async with self.engine.connect() as connection:
            vector_capable = await self._vector_table_available(connection)
        if provider is not None and not provider.semantic_capable:
            vector_status = "provider_not_semantic"
        elif provider is not None and not vector_capable:
            vector_status = "unavailable"
        elif provider is not None:
            query_vector = validate_embedding(
                await provider.embed_query(query.query),
                expected_dimension=PGVECTOR_DIMENSION,
            )
            vector_sql = text(
                f"""
                SELECT c.*,
                       GREATEST(0.0, LEAST(1.0,
                           1.0 - (v.embedding <=> CAST(:embedding AS vector)))) AS vector_score
                  FROM v1_knowledge_chunk_vectors v
                  JOIN v1_knowledge_chunks c ON c.chunk_id = v.chunk_id
                  JOIN v1_knowledge_documents d ON d.document_id = c.document_id
                 WHERE {conditions}
                   AND d.status = 'published'
                   AND (v.visibility_scope = 'public' OR
                       (v.visibility_scope = 'tenant' AND v.tenant_id = :tenant_id))
                   AND v.embedding_model_id = :embedding_model_id
                   AND v.embedding_model_version = :embedding_model_version
                   AND 1.0 - (v.embedding <=> CAST(:embedding AS vector)) > 0.0
                 ORDER BY v.embedding <=> CAST(:embedding AS vector), c.chunk_id
                 LIMIT :limit
                """
            )
            try:
                async with self.engine.connect() as connection:
                    await self._scope_tenant(connection, context)
                    await connection.execute(text("SET LOCAL hnsw.ef_search = 100"))
                    await connection.execute(text("SET LOCAL hnsw.iterative_scan = 'relaxed_order'"))
                    result = await connection.execute(
                        vector_sql,
                        {
                            **params,
                            "embedding": json.dumps(query_vector, separators=(",", ":")),
                            "embedding_model_id": provider.model_id,
                            "embedding_model_version": provider.model_version,
                        },
                    )
                    vector_rows = [dict(row) for row in result.mappings().all()]
                vector_status = "used"
            except SQLAlchemyError:
                # SQLAlchemy exception strings can include bound query text and
                # tenant-private search terms.  Keep the operational signal but
                # never attach the raw exception to application logs.
                logger.warning("pgvector retrieval failed; degrading to lexical")
                vector_status = "unavailable"
                vector_rows = []

        ranked = self._fuse_rows(lexical_rows, vector_rows)
        items: list[EvidenceItem] = []
        seen_hashes: set[str] = set()
        for candidate, fused in ranked:
            content_hash = str(candidate.row["content_hash"])
            component_score = max(candidate.lexical_score or 0.0, candidate.vector_score or 0.0)
            if (
                fused < query.score_threshold
                or component_score < query.score_threshold
                or content_hash in seen_hashes
            ):
                continue
            seen_hashes.add(content_hash)
            items.append(self._row_to_evidence(candidate, query=query, fused=fused))
            if len(items) >= query.top_k:
                break

        retrieval_mode: Literal["lexical", "hybrid"] = (
            "hybrid" if vector_status == "used" else "lexical"
        )
        degraded_reason = None
        if vector_status == "provider_not_semantic":
            degraded_reason = "configured embedding provider is explicitly non-semantic"
        elif vector_status == "unavailable":
            degraded_reason = "pgvector or semantic vectors unavailable; lexical results only"
        elif vector_status == "disabled":
            degraded_reason = "no semantic embedding provider is configured"
        trace = RetrievalTrace(
            query_id=query_id,
            query_hash=query_hash,
            corpus_revision=query.corpus_revision,
            tokenizer_version=self.tokenizer.version,
            embedding_model_version=provider.model_version if provider else None,
            retrieval_mode=retrieval_mode,
            vector_status=vector_status,
            degraded_reason=degraded_reason,
            lexical_candidates=len(lexical_rows),
            vector_candidates=len(vector_rows),
            returned_items=len(items),
        )
        bundle = RetrievalResult(
            query_id=query_id,
            corpus_revision=query.corpus_revision,
            items=items,
            trace=trace,
        )
        await self._write_audit(context, query, bundle)
        return bundle

    def _filter_sql(
        self,
        context: AuthorizedKnowledgeContext,
        query: ResearchQuery,
    ) -> tuple[str, dict[str, Any]]:
        conditions = [
            "(c.visibility_scope = 'public' OR "
            "(c.visibility_scope = 'tenant' AND c.tenant_id = :tenant_id))",
            "c.corpus_revision = :corpus_revision",
            "c.tokenizer_version = :tokenizer_version",
        ]
        params: dict[str, Any] = {
            "tenant_id": context.tenant_id,
            "corpus_revision": query.corpus_revision,
            "tokenizer_version": self.tokenizer.version,
            "valid_at": query.filters.valid_at,
        }
        if not query.filters.include_stale:
            conditions.extend(
                [
                    "(c.valid_from IS NULL OR c.valid_from <= :valid_at)",
                    "(c.valid_until IS NULL OR c.valid_until >= :valid_at)",
                ]
            )
        if query.filters.languages:
            conditions.append("c.language = ANY(CAST(:languages AS text[]))")
            params["languages"] = query.filters.languages
        if query.filters.source_types:
            conditions.append("c.source_type = ANY(CAST(:source_types AS text[]))")
            params["source_types"] = query.filters.source_types
        if query.filters.trust_tiers:
            conditions.append("c.trust_tier = ANY(CAST(:trust_tiers AS text[]))")
            params["trust_tiers"] = [tier.value for tier in query.filters.trust_tiers]
        if query.filters.geo_entities:
            conditions.append(
                "EXISTS (SELECT 1 FROM jsonb_array_elements_text(c.geo_entities) AS geo(value) "
                "WHERE geo.value = ANY(CAST(:geo_entities AS text[])))"
            )
            params["geo_entities"] = query.filters.geo_entities
        if query.filters.tags:
            conditions.append(
                "EXISTS (SELECT 1 FROM jsonb_array_elements_text(c.tags) AS tag(value) "
                "WHERE tag.value = ANY(CAST(:tags AS text[])))"
            )
            params["tags"] = query.filters.tags
        return " AND ".join(conditions), params

    @staticmethod
    def _fuse_rows(
        lexical_rows: list[dict[str, Any]],
        vector_rows: list[dict[str, Any]],
    ) -> list[tuple[_RankedRow, float]]:
        by_id: dict[str, _RankedRow] = {}
        max_lexical = max((float(row["lexical_score"] or 0.0) for row in lexical_rows), default=1.0)
        for rank, row in enumerate(lexical_rows, start=1):
            score = min(1.0, float(row["lexical_score"] or 0.0) / max(max_lexical, 1e-9))
            by_id[str(row["chunk_id"])] = _RankedRow(
                row=row,
                lexical_score=score,
                lexical_rank=rank,
            )
        for rank, row in enumerate(vector_rows, start=1):
            chunk_id = str(row["chunk_id"])
            previous = by_id.get(chunk_id)
            by_id[chunk_id] = _RankedRow(
                row=previous.row if previous else row,
                lexical_score=previous.lexical_score if previous else None,
                vector_score=max(0.0, min(1.0, float(row["vector_score"] or 0.0))),
                lexical_rank=previous.lexical_rank if previous else None,
                vector_rank=rank,
            )
        maximum = (
            RRF_LEXICAL_WEIGHT + (RRF_VECTOR_WEIGHT if vector_rows else 0.0)
        ) / 61.0
        fused: list[tuple[_RankedRow, float]] = []
        for candidate in by_id.values():
            raw = 0.0
            if candidate.lexical_rank is not None:
                raw += RRF_LEXICAL_WEIGHT / (60 + candidate.lexical_rank)
            if candidate.vector_rank is not None:
                raw += RRF_VECTOR_WEIGHT / (60 + candidate.vector_rank)
            fused.append((candidate, min(1.0, raw / maximum) if maximum else 0.0))
        fused.sort(
            key=lambda item: (
                item[1],
                _TRUST_ORDER.get(str(item[0].row["trust_tier"]), 0),
                str(item[0].row["chunk_id"]),
            ),
            reverse=True,
        )
        return fused

    @staticmethod
    def _row_to_evidence(
        candidate: _RankedRow,
        *,
        query: ResearchQuery,
        fused: float,
    ) -> EvidenceItem:
        row = candidate.row
        matched_by: list[Literal["lexical", "vector"]] = []
        if candidate.lexical_rank is not None:
            matched_by.append("lexical")
        if candidate.vector_rank is not None:
            matched_by.append("vector")
        return EvidenceItem(
            evidence_id=new_knowledge_id("ev"),
            chunk_id=str(row["chunk_id"]),
            document_id=str(row["document_id"]),
            source_id=str(row["source_id"]),
            content_hash=str(row["content_hash"]),
            claim_scope=query.claim_scope,
            snippet=str(row["content"])[:2_000],
            source_uri=str(row["canonical_source_uri"]),
            source_title=str(row["source_title"]),
            source_type=str(row["source_type"]),
            source_version=str(row["source_version"]),
            published_at=row["published_at"],
            observed_at=row["observed_at"],
            retrieved_at=utc_now(),
            valid_until=row["valid_until"],
            freshness_status=freshness_status(
                valid_from=row["valid_from"],
                valid_until=row["valid_until"],
                at=query.filters.valid_at,
            ),
            trust_tier=TrustTier(str(row["trust_tier"])),
            license_id=str(row["license_id"]),
            visibility_scope=VisibilityScope(str(row["visibility_scope"])),
            corpus_revision=str(row["corpus_revision"]),
            scores=EvidenceScores(
                lexical=candidate.lexical_score,
                vector=candidate.vector_score,
                fused=fused,
            ),
            matched_by=matched_by,
            injection_suspected=bool(row["injection_suspected"]),
        )

    async def _write_audit(
        self,
        context: AuthorizedKnowledgeContext,
        query: ResearchQuery,
        bundle: RetrievalResult,
    ) -> None:
        try:
            async with self.engine.begin() as connection:
                await self._scope_tenant(connection, context)
                await connection.execute(
                    insert(retrieval_audit_table).values(
                        audit_id=new_knowledge_id("audit"),
                        query_id=bundle.query_id,
                        tenant_id=context.tenant_id,
                        actor_id=context.actor_id,
                        query_hash=bundle.trace.query_hash,
                        corpus_revision=query.corpus_revision,
                        filters=query.filters.model_dump(mode="json"),
                        retrieval_mode=bundle.trace.retrieval_mode,
                        vector_status=bundle.trace.vector_status,
                        result_count=len(bundle.items),
                        created_at=utc_now(),
                    )
                )
        except SQLAlchemyError:
            # Audit persistence errors may contain driver parameters.  The
            # caller already receives the retrieval result, so log only the
            # stable failure category and correlate through restricted DB
            # telemetry rather than leaking query contents here.
            logger.warning("failed to persist retrieval audit")

    async def close(self) -> None:
        """Dispose the owned connection pool."""

        await self.engine.dispose()
        close = getattr(self.embedding_provider, "close", None)
        if close is not None:
            await close()


__all__ = [
    "PGVECTOR_DIMENSION",
    "PostgresKnowledgeRepository",
    "normalize_async_database_url",
]
