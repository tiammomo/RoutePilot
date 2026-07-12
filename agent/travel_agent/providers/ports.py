"""Narrow typed provider ports consumed by deterministic domain services."""

from __future__ import annotations

import asyncio
import math
import time
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from .models import (
    GeocodeRequest,
    GeocodeResult,
    OpeningHoursRequest,
    OpeningHoursResult,
    PlaceSearchRequest,
    PlaceSearchResult,
    ProviderDescriptor,
    RouteMatrixRequest,
    RouteMatrixResult,
    WeatherRequest,
    WeatherResult,
)


class CacheScope(StrEnum):
    """Controls whether a successful lookup can be reused."""

    PUBLIC = "public"
    TENANT = "tenant"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class ProviderCallContext:
    """Server-derived execution context; never authored by a model."""

    tenant_id: str
    actor_id: str
    operation_id: str
    idempotency_key: str | None = None
    deadline_monotonic: float | None = None
    cache_scope: CacheScope = CacheScope.TENANT
    cancellation_event: asyncio.Event | None = None

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.actor_id or not self.operation_id:
            raise ValueError("tenant_id, actor_id and operation_id are required")
        if len(self.tenant_id) > 128 or len(self.actor_id) > 128:
            raise ValueError("tenant_id and actor_id must not exceed 128 characters")
        if len(self.operation_id) > 200:
            raise ValueError("operation_id must not exceed 200 characters")
        if self.idempotency_key is not None and len(self.idempotency_key) < 8:
            raise ValueError("idempotency_key must contain at least eight characters")
        if self.idempotency_key is not None and len(self.idempotency_key) > 200:
            raise ValueError("idempotency_key must not exceed 200 characters")
        if self.deadline_monotonic is not None and (
            not math.isfinite(self.deadline_monotonic) or self.deadline_monotonic <= 0
        ):
            raise ValueError("deadline_monotonic must be a finite positive value")
        if not isinstance(self.cache_scope, CacheScope):
            raise ValueError("cache_scope must be a CacheScope")

    @classmethod
    def with_timeout(
        cls,
        *,
        tenant_id: str,
        actor_id: str,
        operation_id: str,
        timeout_seconds: float,
        idempotency_key: str | None = None,
        cache_scope: CacheScope = CacheScope.TENANT,
        cancellation_event: asyncio.Event | None = None,
    ) -> "ProviderCallContext":
        """Build a context with a monotonic absolute deadline."""

        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        return cls(
            tenant_id=tenant_id,
            actor_id=actor_id,
            operation_id=operation_id,
            idempotency_key=idempotency_key,
            deadline_monotonic=time.monotonic() + timeout_seconds,
            cache_scope=cache_scope,
            cancellation_event=cancellation_event,
        )


class ProviderPort(Protocol):
    """Common metadata exposed by every adapter."""

    descriptor: ProviderDescriptor

    async def close(self) -> None:
        """Release reusable network clients and other resources."""


@runtime_checkable
class PlaceSearchPort(ProviderPort, Protocol):
    async def search_places(
        self, request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult: ...


@runtime_checkable
class GeocodePort(ProviderPort, Protocol):
    async def geocode(
        self, request: GeocodeRequest, context: ProviderCallContext
    ) -> GeocodeResult: ...


@runtime_checkable
class RouteMatrixPort(ProviderPort, Protocol):
    async def route_matrix(
        self, request: RouteMatrixRequest, context: ProviderCallContext
    ) -> RouteMatrixResult: ...


@runtime_checkable
class OpeningHoursPort(ProviderPort, Protocol):
    async def opening_hours(
        self, request: OpeningHoursRequest, context: ProviderCallContext
    ) -> OpeningHoursResult: ...


@runtime_checkable
class WeatherPort(ProviderPort, Protocol):
    async def weather(
        self, request: WeatherRequest, context: ProviderCallContext
    ) -> WeatherResult: ...


__all__ = [
    "CacheScope",
    "GeocodePort",
    "OpeningHoursPort",
    "PlaceSearchPort",
    "ProviderCallContext",
    "ProviderPort",
    "RouteMatrixPort",
    "WeatherPort",
]
