"""Shared request and response schemas for HTTP route handlers."""

from .artifact import (
    ArtifactPatch,
    BudgetReportArtifact,
    ItineraryDraftArtifact,
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
