"""Versioned, checksum-bound knowledge bundles for reviewed RAG content."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator, model_validator

from .models import (
    IngestDocumentRequest,
    LicenseMetadata,
    StrictModel,
    TrustTier,
    VisibilityScope,
    canonicalize_source_uri,
)

_SAFE_IDENTIFIER = re.compile(r"^[a-z0-9][a-z0-9._-]{2,127}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class KnowledgeBundleError(ValueError):
    """A bundle is malformed, unreviewed, or no longer checksum-bound."""


class BundleReview(StrictModel):
    """Human review evidence carried into document metadata."""

    reviewer: str = Field(min_length=2, max_length=128)
    reviewed_at: datetime
    next_review_at: datetime
    status: Literal["approved"] = "approved"
    notes: str = Field(min_length=3, max_length=1_000)

    @field_validator("reviewed_at", "next_review_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("bundle review timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def require_future_review(self) -> "BundleReview":
        if self.next_review_at <= self.reviewed_at:
            raise ValueError("next_review_at must be later than reviewed_at")
        return self


class BundleSmokeQuery(StrictModel):
    """A fixed retrieval assertion for one reviewed document."""

    query: str = Field(min_length=2, max_length=500)
    expected_document_key: str = Field(min_length=3, max_length=128)
    claim_scope: str = Field(default="travel.general", min_length=1, max_length=128)


class BundleUpstreamSource(StrictModel):
    """An authoritative source used to review a RoutePilot-authored guide."""

    canonical_source_uri: str = Field(min_length=8, max_length=2_048)
    publisher: str = Field(min_length=2, max_length=256)
    source_version: str = Field(min_length=1, max_length=128)
    observed_at: datetime
    usage_scope: Literal["reference_only"] = "reference_only"
    notes: str = Field(min_length=3, max_length=1_000)

    @field_validator("canonical_source_uri")
    @classmethod
    def validate_source_uri(cls, value: str) -> str:
        return canonicalize_source_uri(value)

    @field_validator("observed_at")
    @classmethod
    def require_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("upstream source timestamps must include a timezone")
        return value.astimezone(UTC)


class BundleDocument(StrictModel):
    """Manifest metadata for a single local reviewed document."""

    document_key: str = Field(min_length=3, max_length=128)
    content_path: str = Field(min_length=1, max_length=512)
    content_sha256: str = Field(min_length=64, max_length=64)
    canonical_source_uri: str = Field(min_length=8, max_length=2_048)
    source_type: str = Field(min_length=1, max_length=64)
    source_version: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=256)
    language: str = Field(default="zh-CN", min_length=2, max_length=32)
    geo_entities: list[str] = Field(default_factory=list, max_length=64)
    tags: list[str] = Field(default_factory=list, min_length=1, max_length=64)
    published_at: datetime
    observed_at: datetime
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    trust_tier: TrustTier = TrustTier.OPERATOR
    upstream_sources: list[BundleUpstreamSource] = Field(default_factory=list, max_length=16)
    review: BundleReview
    metadata: dict[str, object] = Field(default_factory=dict)

    @field_validator("document_key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        if not _SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError("document_key must be a lowercase stable identifier")
        return value

    @field_validator("content_sha256")
    @classmethod
    def validate_digest(cls, value: str) -> str:
        if not _SHA256.fullmatch(value):
            raise ValueError("content_sha256 must be a lowercase SHA-256 digest")
        return value

    @field_validator("content_path")
    @classmethod
    def validate_content_path(cls, value: str) -> str:
        path = Path(value)
        if path.is_absolute() or ".." in path.parts or value.startswith(("/", "\\")):
            raise ValueError("content_path must stay inside the bundle directory")
        return path.as_posix()

    @field_validator("published_at", "observed_at", "valid_from", "valid_until")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("bundle document timestamps must include a timezone")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_upstream_sources(self) -> "BundleDocument":
        source_uris = [source.canonical_source_uri for source in self.upstream_sources]
        if len(source_uris) != len(set(source_uris)):
            raise ValueError("upstream source URIs must be unique within a document")
        if self.metadata.get("fact_class") == "regional_guide" and not source_uris:
            raise ValueError("regional guides must declare at least one upstream source")
        return self


class KnowledgeBundleManifest(StrictModel):
    """Top-level immutable knowledge release manifest."""

    schema_version: Literal[1] = 1
    bundle_id: str = Field(min_length=3, max_length=128)
    corpus_revision: str = Field(min_length=3, max_length=128)
    publisher: str = Field(min_length=2, max_length=128)
    owner: str = Field(min_length=2, max_length=128)
    default_visibility_scope: VisibilityScope = VisibilityScope.TENANT
    license: LicenseMetadata
    documents: list[BundleDocument] = Field(min_length=1, max_length=500)
    smoke_queries: list[BundleSmokeQuery] = Field(min_length=1, max_length=1_000)

    @field_validator("bundle_id")
    @classmethod
    def validate_bundle_id(cls, value: str) -> str:
        if not _SAFE_IDENTIFIER.fullmatch(value):
            raise ValueError("bundle_id must be a lowercase stable identifier")
        return value

    @model_validator(mode="after")
    def validate_inventory(self) -> "KnowledgeBundleManifest":
        keys = [document.document_key for document in self.documents]
        if len(keys) != len(set(keys)):
            raise ValueError("bundle document_key values must be unique")
        uris = [document.canonical_source_uri for document in self.documents]
        if len(uris) != len(set(uris)):
            raise ValueError("bundle canonical_source_uri values must be unique")
        unknown = sorted(
            {query.expected_document_key for query in self.smoke_queries}.difference(keys)
        )
        if unknown:
            raise ValueError(f"smoke queries reference unknown documents: {', '.join(unknown)}")
        uncovered = sorted(set(keys).difference(query.expected_document_key for query in self.smoke_queries))
        if uncovered:
            raise ValueError(f"documents have no smoke query coverage: {', '.join(uncovered)}")
        return self


@dataclass(frozen=True, slots=True)
class LoadedBundleDocument:
    """A checksum-verified document and its validated ingestion request."""

    document_key: str
    content_path: Path
    content_sha256: str
    request: IngestDocumentRequest


@dataclass(frozen=True, slots=True)
class LoadedKnowledgeBundle:
    """A fully validated bundle ready for planning, ingestion, or verification."""

    manifest_path: Path
    manifest: KnowledgeBundleManifest
    documents: tuple[LoadedBundleDocument, ...]
    release_digest: str

    def document(self, key: str) -> LoadedBundleDocument:
        for document in self.documents:
            if document.document_key == key:
                return document
        raise KeyError(key)


def _sha256_text(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def ingestion_idempotency_key(bundle: LoadedKnowledgeBundle, document_key: str) -> str:
    """Return a deterministic replay-safe key without leaking document content."""

    document = bundle.document(document_key)
    seed = ":".join(
        (
            bundle.manifest.bundle_id,
            bundle.manifest.corpus_revision,
            document.document_key,
            document.content_sha256,
        )
    )
    return f"knowledge-bundle-{hashlib.sha256(seed.encode('utf-8')).hexdigest()[:40]}"


def load_knowledge_bundle(
    manifest_path: Path,
    *,
    visibility_scope: VisibilityScope | None = None,
) -> LoadedKnowledgeBundle:
    """Load a local manifest and reject content drift before any network call."""

    resolved_manifest = manifest_path.expanduser().resolve()
    if not resolved_manifest.is_file():
        raise KnowledgeBundleError(f"knowledge bundle manifest not found: {manifest_path}")
    try:
        raw_manifest = json.loads(resolved_manifest.read_text(encoding="utf-8"))
        manifest = KnowledgeBundleManifest.model_validate(raw_manifest)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise KnowledgeBundleError(f"invalid knowledge bundle manifest: {exc}") from exc

    bundle_root = resolved_manifest.parent.resolve()
    selected_visibility = visibility_scope or manifest.default_visibility_scope
    loaded: list[LoadedBundleDocument] = []
    for specification in manifest.documents:
        candidate_path = bundle_root / specification.content_path
        content_path = candidate_path.resolve()
        if not content_path.is_relative_to(bundle_root):
            raise KnowledgeBundleError(
                f"document escapes bundle directory: {specification.document_key}"
            )
        if candidate_path.is_symlink() or not content_path.is_file():
            raise KnowledgeBundleError(
                f"document content must be a regular local file: {specification.document_key}"
            )
        try:
            content = content_path.read_text(encoding="utf-8")
        except OSError as exc:
            raise KnowledgeBundleError(
                f"document content is unreadable: {specification.document_key}"
            ) from exc
        if not content.strip():
            raise KnowledgeBundleError(
                f"document content is empty: {specification.document_key}"
            )
        actual_digest = _sha256_text(content)
        if actual_digest != specification.content_sha256:
            raise KnowledgeBundleError(
                "content checksum mismatch for "
                f"{specification.document_key}: expected {specification.content_sha256}, "
                f"got {actual_digest}; update source_version and review evidence before release"
            )
        metadata = {
            **specification.metadata,
            "knowledge_bundle_id": manifest.bundle_id,
            "knowledge_document_key": specification.document_key,
            "knowledge_owner": manifest.owner,
            "knowledge_publisher": manifest.publisher,
            "review": specification.review.model_dump(mode="json"),
            "upstream_sources": [
                source.model_dump(mode="json") for source in specification.upstream_sources
            ],
        }
        try:
            request = IngestDocumentRequest(
                canonical_source_uri=specification.canonical_source_uri,
                source_type=specification.source_type,
                source_version=specification.source_version,
                title=specification.title,
                content=content,
                visibility_scope=selected_visibility,
                language=specification.language,
                geo_entities=specification.geo_entities,
                tags=specification.tags,
                published_at=specification.published_at,
                observed_at=specification.observed_at,
                valid_from=specification.valid_from,
                valid_until=specification.valid_until,
                corpus_revision=manifest.corpus_revision,
                trust_tier=specification.trust_tier,
                license=manifest.license,
                metadata=metadata,
            )
        except ValueError as exc:
            raise KnowledgeBundleError(
                f"invalid ingestion request for {specification.document_key}: {exc}"
            ) from exc
        loaded.append(
            LoadedBundleDocument(
                document_key=specification.document_key,
                content_path=content_path,
                content_sha256=actual_digest,
                request=request,
            )
        )

    digest_material = json.dumps(
        {
            "manifest": manifest.model_dump(mode="json"),
            "content_sha256": [document.content_sha256 for document in loaded],
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return LoadedKnowledgeBundle(
        manifest_path=resolved_manifest,
        manifest=manifest,
        documents=tuple(loaded),
        release_digest=_sha256_text(digest_material),
    )


__all__ = [
    "BundleDocument",
    "BundleReview",
    "BundleSmokeQuery",
    "BundleUpstreamSource",
    "KnowledgeBundleError",
    "KnowledgeBundleManifest",
    "LoadedBundleDocument",
    "LoadedKnowledgeBundle",
    "ingestion_idempotency_key",
    "load_knowledge_bundle",
]
