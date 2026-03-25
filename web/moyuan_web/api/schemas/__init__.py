"""Shared request and response schemas for HTTP route handlers."""

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
    "ChatRequest",
    "CityAttractionsResponse",
    "CityDetail",
    "CityListResponse",
    "CitySummary",
    "HealthResponse",
    "LLMHealthResponse",
    "ReadinessCheckResponse",
    "ReadinessResponse",
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
    "UpdateNameRequest",
]
