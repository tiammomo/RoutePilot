"""Ports used by ResearchAgent and knowledge administration."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import (
    AuthorizedKnowledgeContext,
    IngestDocumentRequest,
    IngestResult,
    ResearchQuery,
    RetrievalResult,
)


class KnowledgeError(RuntimeError):
    """Base error intentionally safe to map to a public API response."""


class KnowledgeAuthorizationError(KnowledgeError):
    """The authenticated actor is not allowed to perform the operation."""


class KnowledgeConflictError(KnowledgeError):
    """An idempotency key was reused with a different request."""


class KnowledgeUnavailableError(KnowledgeError):
    """No production knowledge repository is configured."""


@runtime_checkable
class ResearchAgentRetrievalPort(Protocol):
    """Narrow, tenant-authorized port consumed by ResearchAgent."""

    async def retrieve(
        self,
        context: AuthorizedKnowledgeContext,
        query: ResearchQuery,
    ) -> RetrievalResult:
        """Return citation-ready evidence for one authorized tenant."""


@runtime_checkable
class KnowledgeRepositoryPort(ResearchAgentRetrievalPort, Protocol):
    """Persistence boundary used by the API and ingestion worker."""

    async def ingest(
        self,
        context: AuthorizedKnowledgeContext,
        request: IngestDocumentRequest,
        *,
        idempotency_key: str,
    ) -> IngestResult:
        """Idempotently index one already-supplied document."""

    async def close(self) -> None:
        """Release repository resources."""


__all__ = [
    "KnowledgeAuthorizationError",
    "KnowledgeConflictError",
    "KnowledgeError",
    "KnowledgeRepositoryPort",
    "KnowledgeUnavailableError",
    "ResearchAgentRetrievalPort",
]
