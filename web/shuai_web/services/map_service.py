"""Amap integration service for geocoding and route preview."""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import quote

import httpx


@dataclass
class RoutePoint:
    name: str
    lat: float
    lng: float


@dataclass
class RoutePreview:
    provider: str
    points: list[RoutePoint]
    distance_m: float
    duration_s: float
    static_map_url: str
    route_polyline: list[tuple[float, float]]


class MapService:
    """Use Amap APIs only to build route preview payloads."""

    def __init__(self) -> None:
        """Initialize map service with provider config and validation checks.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Returns:
            None: Result value produced by this method.
        """
        self._amap_key = os.getenv("AMAP_KEY", "").strip()

    def _validate_config(self) -> None:
        """Validate map provider config and required keys before requests.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Returns:
            None: Result value produced by this method.
        """
        if not self._amap_key:
            raise ValueError("AMAP_KEY is not configured")

    async def route_preview(
        self,
        *,
        spots: list[str],
        city: str | None = None,
        provider: str | None = None,
    ) -> RoutePreview:
        """Return route preview payload including geometry summary and static-map URL.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            spots: Input `spots` consumed by this method.
            city: Target city name/code used by city or map operations.
            provider: Provider identifier used in fallback selection logic.
        
        Returns:
            RoutePreview: Result value produced by this method.
        """
        _ = provider  # Keep request compatibility; only Amap is supported now.
        self._validate_config()

        cleaned_spots = [spot.strip() for spot in spots if spot and spot.strip()]
        if len(cleaned_spots) < 2:
            raise ValueError("At least two valid spots are required")

        headers = {"User-Agent": "ShuaiTravelAgent/1.0"}
        timeout = httpx.Timeout(15.0, read=20.0)
        points: list[RoutePoint] = []
        distance_m = 0.0
        duration_s = 0.0

        async with httpx.AsyncClient(headers=headers, timeout=timeout) as client:
            for spot in cleaned_spots:
                geocode_resp = await client.get(
                    "https://restapi.amap.com/v3/geocode/geo",
                    params={
                        "key": self._amap_key,
                        "address": spot,
                        "city": city or "",
                    },
                )
                geocode_resp.raise_for_status()
                geocode_data = geocode_resp.json()
                geocodes = geocode_data.get("geocodes") or []
                if not geocodes:
                    continue
                location = str(geocodes[0].get("location", ""))
                if "," not in location:
                    continue
                lng_str, lat_str = location.split(",", maxsplit=1)
                points.append(RoutePoint(name=spot, lng=float(lng_str), lat=float(lat_str)))

            if len(points) < 2:
                raise ValueError("Unable to geocode enough spots for route preview")

            for idx in range(len(points) - 1):
                origin = points[idx]
                destination = points[idx + 1]
                route_resp = await client.get(
                    "https://restapi.amap.com/v5/direction/driving",
                    params={
                        "key": self._amap_key,
                        "origin": f"{origin.lng},{origin.lat}",
                        "destination": f"{destination.lng},{destination.lat}",
                        "strategy": "0",
                    },
                )
                route_resp.raise_for_status()
                route_data = route_resp.json()
                paths = (route_data.get("route") or {}).get("paths") or []
                if not paths:
                    continue
                best = paths[0]
                distance_m += float(best.get("distance") or 0.0)
                duration_s += float(best.get("cost", {}).get("duration") or best.get("duration") or 0.0)

        return RoutePreview(
            provider="amap",
            points=points,
            distance_m=distance_m,
            duration_s=duration_s,
            static_map_url=self._build_amap_static_map(points=points),
            route_polyline=[(point.lng, point.lat) for point in points],
        )

    def _build_amap_static_map(self, *, points: list[RoutePoint]) -> str:
        """Build amap static map for downstream processing.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            points: Input `points` consumed by this method.
        
        Returns:
            str: Result value produced by this method.
        """
        markers = []
        for idx, point in enumerate(points):
            label = chr(ord("A") + (idx % 26))
            markers.append(f"mid,0x2563EB,{label}:{point.lng},{point.lat}")

        path = ";".join([f"{point.lng},{point.lat}" for point in points])
        markers_param = "|".join(markers)
        return (
            "https://restapi.amap.com/v3/staticmap"
            f"?size=900*420&markers={quote(markers_param)}&paths=8,0x1D4ED8,0.9,,{quote(path)}&key={quote(self._amap_key)}"
        )
