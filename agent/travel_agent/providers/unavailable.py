"""Explicit unavailable adapters for capabilities without a production source."""

from __future__ import annotations

from .errors import ProviderUnavailableError
from .models import (
    GeocodeRequest,
    GeocodeResult,
    OpeningHoursRequest,
    OpeningHoursResult,
    PlaceSearchRequest,
    PlaceSearchResult,
    ProviderCapability,
    ProviderDescriptor,
    RouteMatrixRequest,
    RouteMatrixResult,
    WeatherRequest,
    WeatherResult,
)
from .ports import ProviderCallContext


class UnavailableProvider:
    """Fail closed instead of substituting mock facts for missing providers."""

    def __init__(
        self,
        *,
        provider_id: str,
        display_name: str,
        capabilities: frozenset[ProviderCapability],
    ) -> None:
        self.descriptor = ProviderDescriptor(
            provider_id=provider_id,
            display_name=display_name,
            api_family="not-configured",
            api_version="unavailable",
            capabilities=capabilities,
            configured=False,
        )

    async def close(self) -> None:
        return None

    def _unavailable(self) -> ProviderUnavailableError:
        return ProviderUnavailableError(provider_id=self.descriptor.provider_id)

    async def search_places(
        self, request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        raise self._unavailable()

    async def geocode(
        self, request: GeocodeRequest, context: ProviderCallContext
    ) -> GeocodeResult:
        raise self._unavailable()

    async def route_matrix(
        self, request: RouteMatrixRequest, context: ProviderCallContext
    ) -> RouteMatrixResult:
        raise self._unavailable()

    async def opening_hours(
        self, request: OpeningHoursRequest, context: ProviderCallContext
    ) -> OpeningHoursResult:
        raise self._unavailable()

    async def weather(
        self, request: WeatherRequest, context: ProviderCallContext
    ) -> WeatherResult:
        raise self._unavailable()


__all__ = ["UnavailableProvider"]
