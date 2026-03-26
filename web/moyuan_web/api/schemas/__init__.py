"""Shared request and response schemas for HTTP route handlers."""

from .artifact import (
    ArtifactHistoryEntry,
    ArtifactHistoryResponse,
    ArtifactPatch,
    BudgetReportArtifact,
    ItineraryDraftArtifact,
    LatestArtifactResponse,
    ResearchDossierArtifact,
    ResearchEvidenceArtifact,
    TripIntentArtifact,
    TripPlanArtifact,
    VerificationReportArtifact,
    normalize_artifact_patch,
    normalize_trip_plan_artifact,
)
from .chat import ChatRequest
from .city import (
    Attraction,
    CityAttractionsResponse,
    CityDetail,
    CityListResponse,
    CitySummary,
    RegionListResponse,
    TagListResponse,
)
from .health import (
    HealthResponse,
    LLMHealthResponse,
    ReadinessCheckResponse,
    ReadinessResponse,
    SimpleStatusResponse,
    ToolHealthResponse,
    ToolIntentHealthResponse,
)
from .map import RoutePointItem, RoutePreviewRequest, RoutePreviewResponse
from .session import SetModelRequest, UpdateNameRequest
from .share import ShareCreateRequest, ShareCreateResponse, ShareDetailResponse

__all__ = [
    "Attraction",
    "ArtifactHistoryEntry",
    "ArtifactHistoryResponse",
    "ArtifactPatch",
    "BudgetReportArtifact",
    "ChatRequest",
    "CityAttractionsResponse",
    "CityDetail",
    "CityListResponse",
    "CitySummary",
    "HealthResponse",
    "ItineraryDraftArtifact",
    "LLMHealthResponse",
    "LatestArtifactResponse",
    "ReadinessCheckResponse",
    "ReadinessResponse",
    "ResearchDossierArtifact",
    "ResearchEvidenceArtifact",
    "RegionListResponse",
    "RoutePointItem",
    "RoutePreviewRequest",
    "RoutePreviewResponse",
    "SetModelRequest",
    "ShareCreateRequest",
    "ShareCreateResponse",
    "ShareDetailResponse",
    "SimpleStatusResponse",
    "TagListResponse",
    "ToolHealthResponse",
    "ToolIntentHealthResponse",
    "TripIntentArtifact",
    "TripPlanArtifact",
    "UpdateNameRequest",
    "VerificationReportArtifact",
    "normalize_artifact_patch",
    "normalize_trip_plan_artifact",
]
