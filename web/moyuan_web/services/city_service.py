"""Compatibility facade for curated city lookup and filtering."""

from __future__ import annotations

from .city import CityQueryService, CuratedCityCatalog


class CityService:
    """Expose the existing city service API while delegating to smaller collaborators."""

    def __init__(self, catalog: CuratedCityCatalog | None = None) -> None:
        self._catalog = catalog or CuratedCityCatalog()
        self._queries = CityQueryService(self._catalog)

    def list_cities(self, region: str | None = None, tags: str | None = None) -> list[dict[str, object]]:
        """Return filtered city summaries for the city list endpoint."""
        return self._queries.list_cities(region=region, tags=tags)

    def find_city(self, city_id: str) -> dict[str, object] | None:
        """Find one curated city by id."""
        return self._queries.find_city(city_id)

    def build_city_detail(self, city: dict[str, object]) -> dict[str, object]:
        """Build the detail payload for one city."""
        return self._queries.build_city_detail(city)

    def build_attractions(self, city_name: str) -> list[dict[str, object]]:
        """Build attractions payloads for the selected city."""
        return self._queries.build_attractions(city_name)

    def list_regions(self) -> list[str]:
        """List supported region filters."""
        return self._queries.list_regions()

    def list_tags(self) -> list[str]:
        """List supported city tags."""
        return self._queries.list_tags()
