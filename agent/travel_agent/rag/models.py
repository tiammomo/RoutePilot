"""Strict contracts for RoutePilot knowledge ingestion and retrieval.

The models in this module deliberately keep authorization context separate from
model-authored search input.  In particular, a language model can never choose
the tenant used by a retrieval operation.
"""

from __future__ import annotations

import ipaddress
import json
import secrets
import time
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Literal
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_DOCUMENT_CHARS = 262_144
MAX_QUERY_CHARS = 2_000
MAX_CHUNK_CHARS = 8_000
MAX_SNIPPET_CHARS = 2_000
MAX_TOP_K = 20
RRF_LEXICAL_WEIGHT = 0.45
RRF_VECTOR_WEIGHT = 0.55


class StrictModel(BaseModel):
    """Reject unknown data at every RAG boundary."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""

    return datetime.now(UTC)


def new_knowledge_id(prefix: str) -> str:
    """Create a non-sequential public identifier."""

    millis = int(time.time() * 1000)
    return f"{prefix}_{millis:013x}_{secrets.token_hex(10)}"


def canonicalize_source_uri(value: str) -> str:
    """Validate and normalize a citation URI without dereferencing it.

    Ingestion never fetches this URI.  A future connector must perform its own
    DNS/IP revalidation and SSRF policy before network access.
    """

    raw = value.strip()
    parsed = urlsplit(raw)
    if parsed.scheme.lower() not in {"http", "https"}:
        raise ValueError("source URI must use http or https")
    if not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("source URI must contain a host and no userinfo")
    host = parsed.hostname.lower().rstrip(".")
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        address = None
    if address is not None and (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    ):
        raise ValueError("source URI must not reference a non-public IP address")
    netloc = host
    if parsed.port is not None:
        netloc = f"{host}:{parsed.port}"
    path = parsed.path or "/"
    return urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ""))


class VisibilityScope(StrEnum):
    """Knowledge visibility enforced before ranking."""

    PUBLIC = "public"
    TENANT = "tenant"


class TrustTier(StrEnum):
    """Source quality tier used by evidence policy."""

    OFFICIAL = "official"
    OPERATOR = "operator"
    TRUSTED_MEDIA = "trusted_media"
    COMMUNITY = "community"
    USER_PRIVATE = "user_private"


class IngestionStatus(StrEnum):
    """Publication state for a knowledge document."""

    PUBLISHED = "published"
    QUARANTINED = "quarantined"
    TOMBSTONED = "tombstoned"


class FreshnessStatus(StrEnum):
    """Evidence validity relative to retrieval time."""

    FRESH = "fresh"
    STALE = "stale"
    NOT_YET_VALID = "not_yet_valid"
    UNKNOWN = "unknown"


class LicenseMetadata(StrictModel):
    """Indexing and citation rights captured at ingestion time."""

    license_id: str = Field(min_length=1, max_length=128)
    license_url: str | None = Field(default=None, max_length=2_048)
    usage_policy: str = Field(min_length=1, max_length=2_000)
    indexing_allowed: bool = True
    retention_days: int | None = Field(default=None, ge=1, le=36_500)

    @field_validator("license_url")
    @classmethod
    def validate_license_url(cls, value: str | None) -> str | None:
        """Apply the same safe citation-URL rules to a license URL."""

        return canonicalize_source_uri(value) if value else None


class AuthorizedKnowledgeContext(StrictModel):
    """Server-derived identity and authorization for a knowledge operation."""

    tenant_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=128)
    roles: frozenset[str] = Field(default_factory=frozenset)
    authorization_epoch: int = Field(default=0, ge=0)

    @property
    def can_manage_tenant_knowledge(self) -> bool:
        """Return whether this actor may ingest tenant knowledge."""

        return bool(self.roles.intersection({"admin", "tenant_admin"}))

    @property
    def can_manage_public_knowledge(self) -> bool:
        """Only global administrators may publish shared knowledge."""

        return "admin" in self.roles


class IngestDocumentRequest(StrictModel):
    """A sanitized, caller-supplied document; no remote fetch is performed."""

    canonical_source_uri: str = Field(min_length=8, max_length=2_048)
    source_type: str = Field(min_length=1, max_length=64)
    source_version: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    content: str = Field(min_length=1, max_length=MAX_DOCUMENT_CHARS)
    visibility_scope: VisibilityScope = VisibilityScope.TENANT
    language: str = Field(default="zh-CN", min_length=2, max_length=32)
    geo_entities: list[str] = Field(default_factory=list, max_length=64)
    tags: list[str] = Field(default_factory=list, max_length=64)
    published_at: datetime | None = None
    observed_at: datetime = Field(default_factory=utc_now)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    corpus_revision: str = Field(min_length=1, max_length=128)
    trust_tier: TrustTier
    license: LicenseMetadata
    parser_version: str = Field(default="plain-text@1", min_length=1, max_length=64)
    chunker_version: str = Field(default="paragraph-window@1", min_length=1, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("canonical_source_uri")
    @classmethod
    def validate_source_uri(cls, value: str) -> str:
        """Normalize the canonical citation URL."""

        return canonicalize_source_uri(value)

    @field_validator("geo_entities", "tags")
    @classmethod
    def normalize_bounded_values(cls, values: list[str]) -> list[str]:
        """Normalize, bound, and de-duplicate filter metadata."""

        result: list[str] = []
        for raw in values:
            value = str(raw).strip()
            if not value or len(value) > 128:
                raise ValueError("metadata values must contain 1-128 characters")
            if value not in result:
                result.append(value)
        return result

    @field_validator("published_at", "observed_at", "valid_from", "valid_until")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        """Normalize all source/freshness instants to UTC and reject naive time."""

        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("knowledge timestamps must include a timezone")
        return value.astimezone(UTC)

    @field_validator("metadata")
    @classmethod
    def validate_metadata_size(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Keep untrusted metadata JSON serializable and strictly bounded."""

        try:
            serialized = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise ValueError("metadata must be JSON serializable") from exc
        if len(serialized.encode("utf-8")) > 32_768:
            raise ValueError("metadata exceeds 32768 UTF-8 bytes")
        if any(not key or len(key) > 128 for key in value):
            raise ValueError("metadata keys must contain 1-128 characters")
        return value

    @model_validator(mode="after")
    def validate_validity_and_license(self) -> "IngestDocumentRequest":
        """Reject invalid freshness windows and unlicensed publication."""

        if self.valid_from and self.valid_until and self.valid_until <= self.valid_from:
            raise ValueError("valid_until must be later than valid_from")
        if not self.license.indexing_allowed:
            raise ValueError("license does not permit indexing")
        return self


class KnowledgeSource(StrictModel):
    """Canonical source with immutable visibility and license provenance."""

    source_id: str
    tenant_id: str | None
    visibility_scope: VisibilityScope
    canonical_source_uri: str
    source_type: str
    trust_tier: TrustTier
    license: LicenseMetadata
    created_at: datetime
    updated_at: datetime


class KnowledgeDocument(StrictModel):
    """Versioned document metadata retained independently from raw content."""

    document_id: str
    source_id: str
    tenant_id: str | None
    visibility_scope: VisibilityScope
    source_version: str
    title: str
    language: str
    geo_entities: list[str]
    tags: list[str]
    published_at: datetime | None
    observed_at: datetime
    valid_from: datetime | None
    valid_until: datetime | None
    content_hash: str
    parser_version: str
    chunker_version: str
    tokenizer_version: str
    corpus_revision: str
    trust_tier: TrustTier
    license: LicenseMetadata
    status: IngestionStatus
    quarantine_reason: str | None = None
    injection_suspected: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int = Field(default=1, ge=1)
    created_at: datetime
    updated_at: datetime


class KnowledgeDocumentAdminView(KnowledgeDocument):
    """Content-free document metadata returned to knowledge administrators."""

    chunk_count: int = Field(ge=0)


class KnowledgeDocumentPage(StrictModel):
    """Cursor page for a tenant-fenced knowledge inventory."""

    items: list[KnowledgeDocumentAdminView] = Field(max_length=100)
    next_cursor: str | None = None


class KnowledgeDocumentStatusCommand(StrictModel):
    """CAS-protected publication transition for one document."""

    target_status: IngestionStatus
    expected_version: int = Field(ge=1)
    reason: str | None = Field(default=None, min_length=3, max_length=512)

    @model_validator(mode="after")
    def require_non_publication_reason(self) -> "KnowledgeDocumentStatusCommand":
        if self.target_status is not IngestionStatus.PUBLISHED and not self.reason:
            raise ValueError("reason is required when quarantining or tombstoning a document")
        return self


class KnowledgeDocumentStatusResult(StrictModel):
    """Idempotent status transition result."""

    document: KnowledgeDocumentAdminView
    idempotent_replay: bool = False


class KnowledgeChunk(StrictModel):
    """Citation-ready chunk with its own provenance snapshot."""

    chunk_id: str
    document_id: str
    source_id: str
    tenant_id: str | None
    visibility_scope: VisibilityScope
    ordinal: int = Field(ge=0)
    content: str = Field(min_length=1, max_length=MAX_CHUNK_CHARS)
    content_hash: str
    token_count: int = Field(ge=1)
    lexical_terms: str
    canonical_source_uri: str
    source_version: str
    source_type: str
    source_title: str
    language: str
    geo_entities: list[str]
    tags: list[str]
    published_at: datetime | None
    observed_at: datetime
    valid_from: datetime | None
    valid_until: datetime | None
    corpus_revision: str
    tokenizer_version: str
    trust_tier: TrustTier
    license: LicenseMetadata
    injection_suspected: bool
    content_taint: Literal["untrusted_evidence"] = "untrusted_evidence"


class IngestResult(StrictModel):
    """Idempotent ingestion outcome."""

    source_id: str
    document_id: str
    content_hash: str
    chunk_count: int = Field(ge=0)
    status: IngestionStatus
    idempotent_replay: bool = False
    vector_indexed: bool = False
    vector_status: Literal["indexed", "disabled", "unavailable", "provider_not_semantic"]


class RetrievalFilters(StrictModel):
    """Authorized metadata filters applied before ranking."""

    languages: list[str] = Field(default_factory=list, max_length=16)
    source_types: list[str] = Field(default_factory=list, max_length=16)
    trust_tiers: list[TrustTier] = Field(default_factory=list, max_length=8)
    geo_entities: list[str] = Field(default_factory=list, max_length=32)
    tags: list[str] = Field(default_factory=list, max_length=32)
    valid_at: datetime = Field(default_factory=utc_now)
    include_stale: bool = False

    @field_validator("languages", "source_types", "geo_entities", "tags")
    @classmethod
    def normalize_filters(cls, values: list[str]) -> list[str]:
        """Reject oversized filter values and remove duplicates."""

        result: list[str] = []
        for raw in values:
            value = str(raw).strip()
            if not value or len(value) > 128:
                raise ValueError("filter values must contain 1-128 characters")
            if value not in result:
                result.append(value)
        return result

    @field_validator("valid_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        """Reject ambiguous validity comparisons and normalize to UTC."""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("valid_at must include a timezone")
        return value.astimezone(UTC)


class ResearchQuery(StrictModel):
    """Model-safe query input without any tenant selector."""

    query: str = Field(min_length=1, max_length=MAX_QUERY_CHARS)
    claim_scope: str = Field(default="travel.general", min_length=1, max_length=128)
    corpus_revision: str = Field(min_length=1, max_length=128)
    filters: RetrievalFilters = Field(default_factory=RetrievalFilters)
    top_k: int = Field(default=10, ge=1, le=MAX_TOP_K)
    score_threshold: float = Field(default=0.05, ge=0.0, le=1.0)


class EvidenceScores(StrictModel):
    """Transparent component and fused retrieval scores."""

    lexical: float | None = Field(default=None, ge=0.0, le=1.0)
    vector: float | None = Field(default=None, ge=0.0, le=1.0)
    fused: float = Field(ge=0.0, le=1.0)


class EvidenceItem(StrictModel):
    """Evidence content that agents may quote but must never execute."""

    evidence_id: str = Field(min_length=3, max_length=128, pattern=r"^[a-z][a-z0-9_:-]+$")
    chunk_id: str = Field(min_length=3, max_length=128, pattern=r"^[a-z][a-z0-9_:-]+$")
    document_id: str = Field(min_length=3, max_length=128, pattern=r"^[a-z][a-z0-9_:-]+$")
    source_id: str = Field(min_length=3, max_length=128, pattern=r"^[a-z][a-z0-9_:-]+$")
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    claim_scope: str = Field(min_length=1, max_length=128)
    snippet: str = Field(min_length=1, max_length=MAX_SNIPPET_CHARS)
    source_uri: str = Field(min_length=8, max_length=2_048)
    source_title: str = Field(min_length=1, max_length=256)
    source_type: str = Field(min_length=1, max_length=64)
    source_version: str = Field(min_length=1, max_length=128)
    published_at: datetime | None
    observed_at: datetime
    retrieved_at: datetime
    valid_until: datetime | None
    freshness_status: FreshnessStatus
    trust_tier: TrustTier
    license_id: str
    visibility_scope: VisibilityScope
    corpus_revision: str
    scores: EvidenceScores
    matched_by: list[Literal["lexical", "vector"]] = Field(min_length=1, max_length=2)
    injection_suspected: bool
    content_taint: Literal["untrusted_evidence"] = "untrusted_evidence"
    instruction_policy: Literal["evidence_only_never_instructions"] = (
        "evidence_only_never_instructions"
    )


class RetrievalTrace(StrictModel):
    """Safe retrieval telemetry without raw private queries."""

    query_id: str
    query_hash: str
    corpus_revision: str
    tokenizer_version: str
    embedding_model_version: str | None
    retrieval_mode: Literal["lexical", "hybrid"]
    vector_status: Literal["used", "disabled", "unavailable", "provider_not_semantic"]
    degraded_reason: str | None = None
    lexical_candidates: int = Field(ge=0)
    vector_candidates: int = Field(ge=0)
    returned_items: int = Field(ge=0)


class RetrievalResult(StrictModel):
    """Citation-ready input from which ResearchAgent builds EvidenceBundle@1."""

    result_type: Literal["knowledge_retrieval"] = "knowledge_retrieval"
    schema_version: Literal[1] = 1
    query_id: str
    corpus_revision: str
    items: list[EvidenceItem] = Field(max_length=MAX_TOP_K)
    conflicts: list[dict[str, Any]] = Field(default_factory=list, max_length=100)
    trace: RetrievalTrace


def freshness_status(
    *,
    valid_from: datetime | None,
    valid_until: datetime | None,
    at: datetime,
) -> FreshnessStatus:
    """Classify an evidence validity window at a requested instant."""

    if valid_from is not None and at < valid_from:
        return FreshnessStatus.NOT_YET_VALID
    if valid_until is not None and at > valid_until:
        return FreshnessStatus.STALE
    if valid_from is None and valid_until is None:
        return FreshnessStatus.UNKNOWN
    return FreshnessStatus.FRESH


__all__ = [
    "AuthorizedKnowledgeContext",
    "EvidenceItem",
    "EvidenceScores",
    "FreshnessStatus",
    "IngestDocumentRequest",
    "IngestResult",
    "IngestionStatus",
    "KnowledgeChunk",
    "KnowledgeDocument",
    "KnowledgeDocumentAdminView",
    "KnowledgeDocumentPage",
    "KnowledgeDocumentStatusCommand",
    "KnowledgeDocumentStatusResult",
    "KnowledgeSource",
    "LicenseMetadata",
    "MAX_CHUNK_CHARS",
    "MAX_DOCUMENT_CHARS",
    "MAX_QUERY_CHARS",
    "MAX_SNIPPET_CHARS",
    "MAX_TOP_K",
    "ResearchQuery",
    "RetrievalResult",
    "RetrievalFilters",
    "RetrievalTrace",
    "TrustTier",
    "VisibilityScope",
    "canonicalize_source_uri",
    "freshness_status",
    "new_knowledge_id",
    "utc_now",
]
