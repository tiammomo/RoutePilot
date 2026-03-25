"""Mapping helpers for city API payloads."""

from __future__ import annotations

from .types import AttractionPayload, CityPayload

_SUMMARY_FIELDS = (
    "id",
    "name",
    "region",
    "tags",
    "description",
    "avg_budget_per_day",
    "best_seasons",
    "trip_duration",
    "walk_intensity",
    "rain_friendly",
    "family_friendly",
    "food_friendly",
    "style_label",
    "editorial_note",
    "data_source",
)


def to_city_summary(city: CityPayload) -> CityPayload:
    """Project a full city payload into list-friendly summary fields."""
    return {field: city[field] for field in _SUMMARY_FIELDS}


def to_city_detail(city: CityPayload | None, *, fallback: CityPayload) -> CityPayload:
    """Return a detail payload while keeping callers insulated from shared state."""
    return dict(city) if city is not None else dict(fallback)


def to_city_attractions(city: CityPayload | None) -> list[AttractionPayload]:
    """Return a copy of the city's attractions list."""
    return list((city or {}).get("attractions") or [])
