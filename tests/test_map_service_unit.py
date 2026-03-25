"""Unit tests for the refactored map service facade."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from moyuan_web.services.map.route_preview_service import AmapRoutePreviewService  # noqa: E402
from moyuan_web.services.map.static_map_builder import AmapStaticMapBuilder  # noqa: E402
from moyuan_web.services.map.types import RoutePoint, RoutePreview  # noqa: E402
from moyuan_web.services.map_service import MapService  # noqa: E402


class _FakeRouteClient:
    async def geocode_spots(self, *, spots: list[str], city: str | None = None) -> list[RoutePoint]:
        _ = city
        return [
            RoutePoint(name=spots[0], lng=121.4737, lat=31.2304),
            RoutePoint(name=spots[1], lng=121.4998, lat=31.2397),
        ]

    async def summarize_route(self, *, points: list[RoutePoint]) -> tuple[float, float]:
        _ = points
        return 3210.0, 875.0


class _FakeStaticMapBuilder:
    def __init__(self) -> None:
        self.calls: list[tuple[list[RoutePoint], str]] = []

    def build(self, *, points: list[RoutePoint], amap_key: str) -> str:
        self.calls.append((list(points), amap_key))
        return "https://example.com/static-map"


def test_amap_route_preview_service_builds_preview():
    builder = _FakeStaticMapBuilder()
    service = AmapRoutePreviewService(
        amap_key="demo-key",
        client=_FakeRouteClient(),
        static_map_builder=builder,
    )

    preview = asyncio.run(
        service.route_preview(
            spots=[" 外滩 ", "", "豫园"],
            city="上海",
            provider="amap",
        )
    )

    assert preview.provider == "amap"
    assert [point.name for point in preview.points] == ["外滩", "豫园"]
    assert preview.distance_m == 3210.0
    assert preview.duration_s == 875.0
    assert preview.static_map_url == "https://example.com/static-map"
    assert preview.route_polyline == [(121.4737, 31.2304), (121.4998, 31.2397)]
    assert builder.calls[0][1] == "demo-key"


def test_amap_route_preview_service_requires_configured_key():
    service = AmapRoutePreviewService(
        amap_key="",
        client=_FakeRouteClient(),
        static_map_builder=_FakeStaticMapBuilder(),
    )

    with pytest.raises(ValueError, match="AMAP_KEY is not configured"):
        asyncio.run(service.route_preview(spots=["A", "B"]))


def test_map_service_facade_delegates_route_preview():
    class _FakePreviewService:
        def __init__(self) -> None:
            self.calls: list[dict[str, object]] = []

        async def route_preview(self, *, spots: list[str], city: str | None = None, provider: str | None = None) -> RoutePreview:
            self.calls.append({"spots": spots, "city": city, "provider": provider})
            return RoutePreview(
                provider="amap",
                points=[RoutePoint(name="外滩", lng=121.4737, lat=31.2304)],
                distance_m=0.0,
                duration_s=0.0,
                static_map_url="https://example.com/facade",
                route_polyline=[(121.4737, 31.2304)],
            )

    fake_service = _FakePreviewService()
    service = MapService(route_preview_service=fake_service)

    preview = asyncio.run(
        service.route_preview(
            spots=["外滩", "豫园"],
            city="上海",
            provider="amap",
        )
    )

    assert preview.static_map_url == "https://example.com/facade"
    assert fake_service.calls == [{"spots": ["外滩", "豫园"], "city": "上海", "provider": "amap"}]


def test_static_map_builder_labels_points():
    builder = AmapStaticMapBuilder()

    url = builder.build(
        points=[
            RoutePoint(name="A", lng=121.1, lat=31.1),
            RoutePoint(name="B", lng=121.2, lat=31.2),
        ],
        amap_key="demo-key",
    )

    assert "staticmap" in url
    assert "demo-key" in url
    assert "121.1%2C31.1%3B121.2%2C31.2" in url
