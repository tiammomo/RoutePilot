"""Map route preview endpoints (Amap only)."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from ..services.map_service import MapService, RoutePreview
from .errors import raise_api_error

router = APIRouter()
_map_service = MapService()


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


def _to_response(payload: RoutePreview) -> RoutePreviewResponse:
    """Execute to response in backend support workflow.
    
    Purpose:
        Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
    
    Args:
        payload: Structured payload used by API/service boundary.
    
    Returns:
        RoutePreviewResponse: Result value produced by this method.
    """
    return RoutePreviewResponse(
        success=True,
        provider=payload.provider,
        points=[RoutePointItem(name=point.name, lat=point.lat, lng=point.lng) for point in payload.points],
        distance_m=payload.distance_m,
        duration_s=payload.duration_s,
        static_map_url=payload.static_map_url,
        route_polyline=payload.route_polyline,
    )


@router.post("/map/route-preview", response_model=RoutePreviewResponse)
async def route_preview(request: RoutePreviewRequest):
    """Resolve place names to real map points and return route distance preview."""
    try:
        result = await _map_service.route_preview(
            spots=request.spots,
            city=request.city,
            provider=request.provider,
        )
    except ValueError as exc:
        raise_api_error(status_code=422, message=str(exc), code="MAP_ROUTE_INVALID")
    except Exception as exc:
        raise_api_error(status_code=502, message=f"Failed to fetch route preview: {exc}", code="MAP_ROUTE_ERROR")
    return _to_response(result)
