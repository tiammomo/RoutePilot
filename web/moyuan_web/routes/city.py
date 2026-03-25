"""City recommendation and lookup routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..api.schemas.city import (
    CityAttractionsResponse,
    CityDetail,
    CityListResponse,
    CitySummary,
    RegionListResponse,
    TagListResponse,
)
from .errors import raise_api_error
from .service_resolver import get_city_service

router = APIRouter()


def _find_city_or_404(city_id: str) -> dict[str, object]:
    """Resolve city by ID or raise a standard not-found API error."""
    city = get_city_service().find_city(city_id)
    if city is None:
        raise_api_error(status_code=404, message="City not found", code="CITY_NOT_FOUND")
    return city


@router.get("/cities", response_model=CityListResponse)
async def list_cities(
    region: str | None = Query(default=None, description="Filter by region"),
    tags: str | None = Query(default=None, description="Filter by comma-separated tags"),
):
    """List cities with optional region and tag filters."""
    result = get_city_service().list_cities(region=region, tags=tags)
    return CityListResponse(cities=[CitySummary.model_validate(item) for item in result])


@router.get("/cities/{city_id}", response_model=CityDetail)
async def get_city(city_id: str):
    """Get full city detail by city identifier."""
    city = _find_city_or_404(city_id)
    return CityDetail.model_validate(get_city_service().build_city_detail(city))


@router.get("/cities/{city_id}/attractions", response_model=CityAttractionsResponse)
async def get_city_attractions(city_id: str):
    """Get recommended attractions for the selected city."""
    city = _find_city_or_404(city_id)
    city_name = str(city["name"])
    return CityAttractionsResponse(city=city_name, attractions=get_city_service().build_attractions(city_name))


@router.get("/regions", response_model=RegionListResponse)
async def list_regions():
    """List supported region filters."""
    return RegionListResponse(regions=get_city_service().list_regions())


@router.get("/tags", response_model=TagListResponse)
async def list_tags():
    """List supported city tags for filtering."""
    return TagListResponse(tags=get_city_service().list_tags())
