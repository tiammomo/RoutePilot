"""Map endpoint schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class RoutePreviewRequest(BaseModel):
    """Request payload for route preview."""

    spots: list[str] = Field(min_length=2, max_length=10)
    city: str | None = None
    provider: str | None = "amap"


class RoutePointItem(BaseModel):
    """Response point item."""

    name: str
    lat: float
    lng: float


class RoutePreviewResponse(BaseModel):
    """Response payload for route preview."""

    success: bool = True
    provider: str
    points: list[RoutePointItem]
    distance_m: float
    duration_s: float
    static_map_url: str
    route_polyline: list[tuple[float, float]]
