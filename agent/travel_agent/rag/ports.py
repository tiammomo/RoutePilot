"""Ports used by ResearchAgent and knowledge administration."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from .models import (
    AuthorizedKnowledgeContext,
    IngestDocumentRequest,
    IngestResult,
    IngestionStatus,
    KnowledgeDocumentAdminView,
    KnowledgeDocumentPage,
    KnowledgeDocumentStatusCommand,
    KnowledgeDocumentStatusResult,
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


class KnowledgeNotFoundError(KnowledgeError):
    """The requested document is absent from the authorized scope."""


class KnowledgeVersionConflictError(KnowledgeConflictError):
    """A document status command targeted a stale version."""

    def __init__(self, message: str, *, current_version: int):
        super().__init__(message)
        self.current_version = current_version


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

    async def list_documents(
        self,
        context: AuthorizedKnowledgeContext,
        *,
        status: IngestionStatus | None,
        limit: int,
        cursor: str | None,
    ) -> KnowledgeDocumentPage:
        """List content-free metadata visible to one knowledge administrator."""

    async def get_document(
        self,
        context: AuthorizedKnowledgeContext,
        document_id: str,
    ) -> KnowledgeDocumentAdminView:
        """Read one content-free document metadata record."""

    async def change_document_status(
        self,
        context: AuthorizedKnowledgeContext,
        document_id: str,
        command: KnowledgeDocumentStatusCommand,
        *,
        idempotency_key: str,
    ) -> KnowledgeDocumentStatusResult:
        """Idempotently transition status with optimistic concurrency."""

    async def close(self) -> None:
        """Release repository resources."""


__all__ = [
    "KnowledgeAuthorizationError",
    "KnowledgeConflictError",
    "KnowledgeError",
    "KnowledgeNotFoundError",
    "KnowledgeRepositoryPort",
    "KnowledgeUnavailableError",
    "KnowledgeVersionConflictError",
    "ResearchAgentRetrievalPort",
]
