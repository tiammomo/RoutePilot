"""Query and filtering helpers for city endpoints."""

from __future__ import annotations

from .catalog import CuratedCityCatalog
from .mapper import to_city_attractions, to_city_detail, to_city_summary
from .types import CityPayload


class CityQueryService:
    """Coordinate catalog lookup, filtering, and response shaping."""

    def __init__(self, catalog: CuratedCityCatalog) -> None:
        """Store the curated catalog used by city query operations."""
        self._catalog = catalog

    def list_cities(self, region: str | None = None, tags: str | None = None) -> list[CityPayload]:
        """Return filtered city summaries for list endpoints."""
        result = self._catalog.all()

        if region:
            region_value = region.strip()
            result = [item for item in result if item.get("region") == region_value]

        tag_set = self._parse_tags(tags)
        if tag_set:
            result = [item for item in result if any(tag in tag_set for tag in (item.get("tags") or []))]

        return [to_city_summary(item) for item in result]

    def find_city(self, city_id: str) -> CityPayload | None:
        """Return one city by id, copied for safe downstream use."""
        city = self._catalog.find_by_id(city_id)
        return dict(city) if city is not None else None

    def build_city_detail(self, city: CityPayload) -> CityPayload:
        """Return the canonical detail payload for one city."""
        detail = self._catalog.find_by_id(str(city["id"]))
        return to_city_detail(detail, fallback=city)

    def build_attractions(self, city_name: str) -> list[dict[str, object]]:
        """Return attractions for the requested city name."""
        return to_city_attractions(self._catalog.find_by_name(city_name))

    def list_regions(self) -> list[str]:
        """Return sorted region filters."""
        return self._catalog.list_regions()

    def list_tags(self) -> list[str]:
        """Return sorted tag filters."""
        return self._catalog.list_tags()

    @staticmethod
    def _parse_tags(tags: str | None) -> set[str]:
        """Parse comma-separated tags into a normalized filter set."""
        if not tags:
            return set()
        return {item.strip() for item in tags.split(",") if item.strip()}
