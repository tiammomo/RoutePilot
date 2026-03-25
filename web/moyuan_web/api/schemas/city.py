"""City endpoint schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class Attraction(BaseModel):
    """Simplified attraction payload exposed by city endpoints."""

    name: str
    type: str
    duration: str
    ticket: int
    district: str | None = None
    note: str | None = None


class CitySummary(BaseModel):
    """Compact city card used in list responses."""

    id: str
    name: str
    region: str
    tags: list[str]
    description: str
    avg_budget_per_day: int
    best_seasons: list[str]
    trip_duration: str
    walk_intensity: Literal["low", "medium", "high"]
    rain_friendly: bool
    family_friendly: bool
    food_friendly: bool
    style_label: str
    editorial_note: str
    data_source: Literal["curated"]


class CityDetail(CitySummary):
    """Expanded city detail payload with recommendation metadata."""

    attractions: list[Attraction]


class CityListResponse(BaseModel):
    """Response schema for city list endpoint."""

    cities: list[CitySummary]


class RegionListResponse(BaseModel):
    """Response schema for supported region names."""

    regions: list[str]


class TagListResponse(BaseModel):
    """Response schema for supported city tags."""

    tags: list[str]


class CityAttractionsResponse(BaseModel):
    """Response schema for a city's attraction recommendations."""

    city: str
    attractions: list[Attraction]
