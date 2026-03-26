"""Catalog access helpers for curated city data."""

from __future__ import annotations

from .catalog_data import build_curated_cities
from .types import CityPayload


class CuratedCityCatalog:
    """Provide indexed access to the curated city catalog."""

    def __init__(self, cities: list[CityPayload] | None = None) -> None:
        """Build stable city indexes from curated catalog payloads."""
        self._cities = list(cities) if cities is not None else build_curated_cities()
        self._city_by_id = {str(item["id"]): item for item in self._cities}
        self._city_by_name = {str(item["name"]): item for item in self._cities}

    def all(self) -> list[CityPayload]:
        """Return the catalog in insertion order."""
        return list(self._cities)

    def find_by_id(self, city_id: str) -> CityPayload | None:
        """Look up one city by stable identifier."""
        return self._city_by_id.get(city_id)

    def find_by_name(self, city_name: str) -> CityPayload | None:
        """Look up one city by display name."""
        return self._city_by_name.get(city_name)

    def list_regions(self) -> list[str]:
        """Return sorted unique region names."""
        return sorted({str(item["region"]) for item in self._cities})

    def list_tags(self) -> list[str]:
        """Return sorted unique city tags."""
        tags: set[str] = set()
        for city in self._cities:
            tags.update(city.get("tags") or [])
        return sorted(tags)
