"""City recommendation and lookup routes."""

from __future__ import annotations

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..services.city_service import CityService
from .errors import raise_api_error

router = APIRouter()
_city_service = CityService()


class Attraction(BaseModel):
    name: str
    type: str
    duration: str
    ticket: int


class CitySummary(BaseModel):
    id: str
    name: str
    region: str
    tags: list[str]


class CityDetail(CitySummary):
    description: str
    attractions: list[Attraction]
    avg_budget_per_day: int
    best_seasons: list[str]


class CityListResponse(BaseModel):
    cities: list[CitySummary]


class RegionListResponse(BaseModel):
    regions: list[str]


class TagListResponse(BaseModel):
    tags: list[str]


class CityAttractionsResponse(BaseModel):
    city: str
    attractions: list[Attraction]


def _find_city_or_404(city_id: str) -> dict[str, object]:
    city = _city_service.find_city(city_id)
    if city is None:
        raise_api_error(status_code=404, message="City not found", code="CITY_NOT_FOUND")
    return city


@router.get("/cities", response_model=CityListResponse)
async def list_cities(
    region: str | None = Query(default=None, description="按地区筛选"),
    tags: str | None = Query(default=None, description="按标签筛选，逗号分隔"),
):
    result = _city_service.list_cities(region=region, tags=tags)
    return CityListResponse(cities=[CitySummary.model_validate(item) for item in result])


@router.get("/cities/{city_id}", response_model=CityDetail)
async def get_city(city_id: str):
    city = _find_city_or_404(city_id)
    return CityDetail.model_validate(_city_service.build_city_detail(city))


@router.get("/cities/{city_id}/attractions", response_model=CityAttractionsResponse)
async def get_city_attractions(city_id: str):
    city = _find_city_or_404(city_id)
    city_name = str(city["name"])
    return CityAttractionsResponse(city=city_name, attractions=_city_service.build_attractions(city_name))


@router.get("/regions", response_model=RegionListResponse)
async def list_regions():
    return RegionListResponse(regions=_city_service.list_regions())


@router.get("/tags", response_model=TagListResponse)
async def list_tags():
    return TagListResponse(tags=_city_service.list_tags())
