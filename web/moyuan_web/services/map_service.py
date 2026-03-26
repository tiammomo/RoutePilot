"""Compatibility facade for map route preview workflows."""

from __future__ import annotations

import os

from .map import AmapRoutePreviewService, RoutePoint, RoutePreview


class MapService:
    """Expose the existing map service API while delegating to smaller collaborators."""

    def __init__(self, route_preview_service: AmapRoutePreviewService | None = None) -> None:
        """Create the facade with an Amap-backed route preview service by default."""
        self._route_preview_service = route_preview_service or AmapRoutePreviewService(
            amap_key=os.getenv("AMAP_KEY", "").strip(),
        )

    async def route_preview(
        self,
        *,
        spots: list[str],
        city: str | None = None,
        provider: str | None = None,
    ) -> RoutePreview:
        """Return route preview payload including geometry summary and static-map URL."""
        return await self._route_preview_service.route_preview(
            spots=spots,
            city=city,
            provider=provider,
        )


__all__ = ["MapService", "RoutePoint", "RoutePreview"]
