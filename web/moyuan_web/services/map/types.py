"""Shared data structures for map route preview services."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RoutePoint:
    """Single named coordinate point in a planned route."""

    name: str
    lat: float
    lng: float


@dataclass
class RoutePreview:
    """Aggregated route preview payload returned to API clients."""

    provider: str
    points: list[RoutePoint]
    distance_m: float
    duration_s: float
    static_map_url: str
    route_polyline: list[tuple[float, float]]
