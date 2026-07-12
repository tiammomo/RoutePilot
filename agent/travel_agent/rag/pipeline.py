"""Shared deterministic preparation for in-memory and PostgreSQL ingestion."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from .models import (
    IngestDocumentRequest,
    IngestionStatus,
    KnowledgeChunk,
    KnowledgeDocument,
    KnowledgeSource,
    VisibilityScope,
    new_knowledge_id,
    utc_now,
)
from .text import (
    EvidenceTextSanitizer,
    ParagraphWindowChunker,
    TravelTokenizer,
    count_tokens_approximately,
)


@dataclass(frozen=True, slots=True)
class PreparedIngestion:
    """Fully normalized objects ready for one atomic repository transaction."""

    source: KnowledgeSource
    document: KnowledgeDocument
    chunks: list[KnowledgeChunk]
    request_hash: str


def sha256_text(value: str) -> str:
    """Return a lowercase SHA-256 digest."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def scope_key(tenant_id: str, visibility: VisibilityScope) -> str:
    """Return the non-null key used by idempotency and source uniqueness."""

    return "__public__" if visibility is VisibilityScope.PUBLIC else tenant_id


def prepare_ingestion(
    *,
    tenant_id: str,
    request: IngestDocumentRequest,
    source_id: str | None = None,
    document_id: str | None = None,
    tokenizer: TravelTokenizer | None = None,
    sanitizer: EvidenceTextSanitizer | None = None,
    chunker: ParagraphWindowChunker | None = None,
) -> PreparedIngestion:
    """Sanitize, fingerprint, and chunk one input document."""

    selected_tokenizer = tokenizer or TravelTokenizer()
    selected_sanitizer = sanitizer or EvidenceTextSanitizer()
    selected_chunker = chunker or ParagraphWindowChunker()
    if request.parser_version != "plain-text@1":
        raise ValueError("V1 direct ingestion supports only parser_version=plain-text@1")
    if request.chunker_version != selected_chunker.version:
        raise ValueError(
            f"chunker version mismatch: requested {request.chunker_version}, "
            f"runtime {selected_chunker.version}"
        )
    sanitized = selected_sanitizer.sanitize(request.content)
    content_hash = sha256_text(sanitized.content)
    request_payload = request.model_dump(mode="json", exclude={"content"})
    request_payload["content_hash"] = content_hash
    request_hash = sha256_text(
        json.dumps(request_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    )
    now = utc_now()
    persisted_tenant = tenant_id if request.visibility_scope is VisibilityScope.TENANT else None
    resolved_source_id = source_id or new_knowledge_id("src")
    resolved_document_id = document_id or new_knowledge_id("doc")
    source = KnowledgeSource(
        source_id=resolved_source_id,
        tenant_id=persisted_tenant,
        visibility_scope=request.visibility_scope,
        canonical_source_uri=request.canonical_source_uri,
        source_type=request.source_type,
        trust_tier=request.trust_tier,
        license=request.license,
        created_at=now,
        updated_at=now,
    )
    document = KnowledgeDocument(
        document_id=resolved_document_id,
        source_id=resolved_source_id,
        tenant_id=persisted_tenant,
        visibility_scope=request.visibility_scope,
        source_version=request.source_version,
        title=request.title,
        language=request.language,
        geo_entities=request.geo_entities,
        tags=request.tags,
        published_at=request.published_at,
        observed_at=request.observed_at,
        valid_from=request.valid_from,
        valid_until=request.valid_until,
        content_hash=content_hash,
        parser_version=request.parser_version,
        chunker_version=selected_chunker.version,
        tokenizer_version=selected_tokenizer.version,
        corpus_revision=request.corpus_revision,
        trust_tier=request.trust_tier,
        license=request.license,
        status=IngestionStatus.PUBLISHED,
        injection_suspected=sanitized.injection_suspected,
        metadata=request.metadata,
        created_at=now,
        updated_at=now,
    )
    chunks: list[KnowledgeChunk] = []
    for ordinal, content in enumerate(selected_chunker.split(sanitized.content)):
        terms = selected_tokenizer.tokenize(content)
        chunks.append(
            KnowledgeChunk(
                chunk_id=new_knowledge_id("chk"),
                document_id=resolved_document_id,
                source_id=resolved_source_id,
                tenant_id=persisted_tenant,
                visibility_scope=request.visibility_scope,
                ordinal=ordinal,
                content=content,
                content_hash=sha256_text(content),
                token_count=count_tokens_approximately(terms),
                lexical_terms=" ".join(terms),
                canonical_source_uri=request.canonical_source_uri,
                source_version=request.source_version,
                source_type=request.source_type,
                source_title=request.title,
                language=request.language,
                geo_entities=request.geo_entities,
                tags=request.tags,
                published_at=request.published_at,
                observed_at=request.observed_at,
                valid_from=request.valid_from,
                valid_until=request.valid_until,
                corpus_revision=request.corpus_revision,
                tokenizer_version=selected_tokenizer.version,
                trust_tier=request.trust_tier,
                license=request.license,
                injection_suspected=sanitized.injection_suspected,
            )
        )
    return PreparedIngestion(
        source=source,
        document=document,
        chunks=chunks,
        request_hash=request_hash,
    )


__all__ = ["PreparedIngestion", "prepare_ingestion", "scope_key", "sha256_text"]
