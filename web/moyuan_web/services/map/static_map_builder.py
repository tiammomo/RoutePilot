"""Static map URL builders for route preview responses."""

from __future__ import annotations

from urllib.parse import quote

from .types import RoutePoint


class AmapStaticMapBuilder:
    """Build Amap static map URLs for resolved route points."""

    def build(self, *, points: list[RoutePoint], amap_key: str) -> str:
        """Build the static map URL for the provided route points."""
        markers: list[str] = []
        for idx, point in enumerate(points):
            label = chr(ord("A") + (idx % 26))
            markers.append(f"mid,0x2563EB,{label}:{point.lng},{point.lat}")

        path = ";".join(f"{point.lng},{point.lat}" for point in points)
        markers_param = "|".join(markers)
        return (
            "https://restapi.amap.com/v3/staticmap"
            f"?size=900*420&markers={quote(markers_param)}&paths=8,0x1D4ED8,0.9,,{quote(path)}&key={quote(amap_key)}"
        )
