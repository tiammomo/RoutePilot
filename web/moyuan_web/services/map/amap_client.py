"""HTTP client helpers for Amap geocoding and route summary APIs."""

from __future__ import annotations

import httpx

from .types import RoutePoint


class AmapHttpClient:
    """Wrap Amap HTTP calls used by route preview workflows."""

    def __init__(self, amap_key: str) -> None:
        self._amap_key = amap_key
        self._headers = {"User-Agent": "moyuan-travel-agent/1.0"}
        self._timeout = httpx.Timeout(15.0, read=20.0)

    async def geocode_spots(self, *, spots: list[str], city: str | None = None) -> list[RoutePoint]:
        """Resolve spot names into route points using the Amap geocoding API."""
        points: list[RoutePoint] = []
        async with httpx.AsyncClient(headers=self._headers, timeout=self._timeout) as client:
            for spot in spots:
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
        return points

    async def summarize_route(self, *, points: list[RoutePoint]) -> tuple[float, float]:
        """Aggregate driving distance and duration across sequential route legs."""
        distance_m = 0.0
        duration_s = 0.0
        async with httpx.AsyncClient(headers=self._headers, timeout=self._timeout) as client:
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
        return distance_m, duration_s
