"""Route preview orchestration helpers for map services."""

from __future__ import annotations

from typing import Protocol

from .amap_client import AmapHttpClient
from .static_map_builder import AmapStaticMapBuilder
from .types import RoutePoint, RoutePreview


class _RoutePreviewClient(Protocol):
    """Protocol for route-preview clients used by the service coordinator."""

    async def geocode_spots(self, *, spots: list[str], city: str | None = None) -> list[RoutePoint]:
        """Resolve named spots into map coordinates."""

    async def summarize_route(self, *, points: list[RoutePoint]) -> tuple[float, float]:
        """Return aggregate distance and duration for resolved route points."""


class _StaticMapBuilder(Protocol):
    """Protocol for static map URL builders."""

    def build(self, *, points: list[RoutePoint], amap_key: str) -> str:
        """Build a static map URL for the provided route points."""


class AmapRoutePreviewService:
    """Coordinate Amap config validation, geocoding, routing, and URL building."""

    def __init__(
        self,
        *,
        amap_key: str,
        client: _RoutePreviewClient | None = None,
        static_map_builder: _StaticMapBuilder | None = None,
    ) -> None:
        """Store Amap credentials plus pluggable HTTP and static-map collaborators."""
        self._amap_key = amap_key.strip()
        self._client = client or AmapHttpClient(self._amap_key)
        self._static_map_builder = static_map_builder or AmapStaticMapBuilder()

    async def route_preview(
        self,
        *,
        spots: list[str],
        city: str | None = None,
        provider: str | None = None,
    ) -> RoutePreview:
        """Return route preview payload including geometry summary and static-map URL."""
        _ = provider  # Compatibility placeholder; only Amap is supported right now.
        self._validate_config()

        cleaned_spots = [spot.strip() for spot in spots if spot and spot.strip()]
        if len(cleaned_spots) < 2:
            raise ValueError("At least two valid spots are required")

        points = await self._client.geocode_spots(spots=cleaned_spots, city=city)
        if len(points) < 2:
            raise ValueError("Unable to geocode enough spots for route preview")

        distance_m, duration_s = await self._client.summarize_route(points=points)
        return RoutePreview(
            provider="amap",
            points=points,
            distance_m=distance_m,
            duration_s=duration_s,
            static_map_url=self._static_map_builder.build(points=points, amap_key=self._amap_key),
            route_polyline=[(point.lng, point.lat) for point in points],
        )

    def _validate_config(self) -> None:
        """Validate map provider config and required keys before requests."""
        if not self._amap_key:
            raise ValueError("AMAP_KEY is not configured")
