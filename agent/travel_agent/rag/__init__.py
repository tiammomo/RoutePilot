"""RoutePilot V1 provenance-aware retrieval infrastructure."""

from .embedding import (
    DeterministicHashEmbeddingProvider,
    EmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
    build_embedding_provider_from_env,
)
from .memory import InMemoryKnowledgeRepository
from .models import (
    AuthorizedKnowledgeContext,
    EvidenceItem,
    IngestDocumentRequest,
    IngestResult,
    IngestionStatus,
    KnowledgeDocumentAdminView,
    KnowledgeDocumentPage,
    KnowledgeDocumentStatusCommand,
    KnowledgeDocumentStatusResult,
    ResearchQuery,
    RetrievalResult,
    RetrievalFilters,
    TrustTier,
    VisibilityScope,
)
from .ports import (
    KnowledgeAuthorizationError,
    KnowledgeConflictError,
    KnowledgeError,
    KnowledgeNotFoundError,
    KnowledgeRepositoryPort,
    ResearchAgentRetrievalPort,
    KnowledgeVersionConflictError,
)
from .postgres import PostgresKnowledgeRepository
from .service import KnowledgeService, TenantBoundResearchRetriever, build_safe_agent_context

__all__ = [
    "AuthorizedKnowledgeContext",
    "DeterministicHashEmbeddingProvider",
    "EmbeddingProvider",
    "OpenAICompatibleEmbeddingProvider",
    "EvidenceItem",
    "InMemoryKnowledgeRepository",
    "IngestDocumentRequest",
    "IngestResult",
    "IngestionStatus",
    "KnowledgeDocumentAdminView",
    "KnowledgeDocumentPage",
    "KnowledgeDocumentStatusCommand",
    "KnowledgeDocumentStatusResult",
    "KnowledgeAuthorizationError",
    "KnowledgeConflictError",
    "KnowledgeError",
    "KnowledgeNotFoundError",
    "KnowledgeRepositoryPort",
    "KnowledgeService",
    "KnowledgeVersionConflictError",
    "PostgresKnowledgeRepository",
    "ResearchAgentRetrievalPort",
    "ResearchQuery",
    "RetrievalResult",
    "RetrievalFilters",
    "TenantBoundResearchRetriever",
    "TrustTier",
    "VisibilityScope",
    "build_safe_agent_context",
    "build_embedding_provider_from_env",
]
