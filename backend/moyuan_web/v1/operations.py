"""Dependency readiness and low-cardinality operational metrics for V1."""

from __future__ import annotations

import asyncio
import math
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from time import monotonic

from redis.asyncio import Redis
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from .postgres_store import normalize_async_database_url

Probe = Callable[[], Awaitable[bool]]


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    """Safe dependency state; raw connection failures never cross this boundary."""

    postgresql: str
    redis: str

    @property
    def ready(self) -> bool:
        return self.postgresql == "available" and self.redis == "available"

    def public_payload(self) -> dict[str, object]:
        return {
            "status": "ready" if self.ready else "not_ready",
            "components": {
                "postgresql": self.postgresql,
                "redis": self.redis,
            },
        }


class DependencyReadiness:
    """Bounded, cached PostgreSQL/Redis probes suitable for a traffic gate."""

    def __init__(
        self,
        *,
        database_url: str,
        redis_url: str,
        timeout_seconds: float = 2.0,
        cache_seconds: float = 1.0,
        postgresql_probe: Probe | None = None,
        redis_probe: Probe | None = None,
    ) -> None:
        self.database_url = database_url.strip()
        self.redis_url = redis_url.strip()
        self.timeout_seconds = timeout_seconds
        self.cache_seconds = cache_seconds
        self._engine: AsyncEngine | None = None
        self._redis: Redis | None = None
        self._postgresql_probe = postgresql_probe
        self._redis_probe = redis_probe
        self._cached: tuple[float, ReadinessReport] | None = None
        self._lock = asyncio.Lock()

    def _database_engine(self) -> AsyncEngine:
        if self._engine is None:
            self._engine = create_async_engine(
                normalize_async_database_url(self.database_url),
                pool_pre_ping=True,
                pool_size=2,
                max_overflow=0,
                pool_timeout=self.timeout_seconds,
            )
        return self._engine

    def _redis_client(self) -> Redis:
        if self._redis is None:
            self._redis = Redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=self.timeout_seconds,
                socket_timeout=self.timeout_seconds,
            )
        return self._redis

    async def _check_postgresql(self) -> bool:
        if self._postgresql_probe is not None:
            return await self._postgresql_probe()
        async with self._database_engine().connect() as connection:
            return int(await connection.scalar(text("SELECT 1")) or 0) == 1

    async def _check_redis(self) -> bool:
        if self._redis_probe is not None:
            return await self._redis_probe()
        return bool(await self._redis_client().ping())

    async def _bounded(self, configured: bool, probe: Probe) -> str:
        if not configured:
            return "not_configured"
        try:
            healthy = await asyncio.wait_for(probe(), timeout=self.timeout_seconds)
        except Exception:
            return "unavailable"
        return "available" if healthy else "unavailable"

    async def check(self) -> ReadinessReport:
        """Probe once per cache window and coalesce concurrent requests."""

        now = monotonic()
        cached = self._cached
        if cached is not None and now - cached[0] <= self.cache_seconds:
            return cached[1]
        async with self._lock:
            now = monotonic()
            cached = self._cached
            if cached is not None and now - cached[0] <= self.cache_seconds:
                return cached[1]
            postgresql, redis = await asyncio.gather(
                self._bounded(bool(self.database_url), self._check_postgresql),
                self._bounded(bool(self.redis_url), self._check_redis),
            )
            report = ReadinessReport(postgresql=postgresql, redis=redis)
            self._cached = (monotonic(), report)
            return report

    async def close(self) -> None:
        """Release lazily-created pools."""

        if self._engine is not None:
            await self._engine.dispose()
        if self._redis is not None:
            await self._redis.aclose()


class OperationalMetrics:
    """Small Prometheus renderer with bounded route/status labels only."""

    BUCKETS = (0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)

    def __init__(self, *, version: str) -> None:
        self.version = version
        self._request_counts: dict[tuple[str, str, str], int] = defaultdict(int)
        self._duration_counts: dict[tuple[str, str], int] = defaultdict(int)
        self._duration_sums: dict[tuple[str, str], float] = defaultdict(float)
        self._duration_buckets: dict[tuple[str, str, float], int] = defaultdict(int)
        self._dependencies = {"postgresql": 0, "redis": 0}

    @staticmethod
    def _label(value: str) -> str:
        return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')

    def observe_http(
        self,
        *,
        method: str,
        route: str,
        status_code: int,
        duration_seconds: float,
    ) -> None:
        """Record one request without user, tenant, resource, or raw-path labels."""

        method_label = method.upper()[:16]
        route_label = route if route.startswith("/") else "unmatched"
        status_label = f"{max(1, min(5, status_code // 100))}xx"
        self._request_counts[(method_label, route_label, status_label)] += 1
        duration_key = (method_label, route_label)
        self._duration_counts[duration_key] += 1
        self._duration_sums[duration_key] += max(0.0, duration_seconds)
        for bucket in self.BUCKETS:
            if duration_seconds <= bucket:
                self._duration_buckets[(method_label, route_label, bucket)] += 1

    def update_readiness(self, report: ReadinessReport) -> None:
        self._dependencies["postgresql"] = int(report.postgresql == "available")
        self._dependencies["redis"] = int(report.redis == "available")

    def render(self) -> str:
        """Render deterministic Prometheus text exposition."""

        lines = [
            "# HELP routepilot_build_info RoutePilot API build information.",
            "# TYPE routepilot_build_info gauge",
            f'routepilot_build_info{{version="{self._label(self.version)}"}} 1',
            "# HELP routepilot_dependency_ready Whether a required dependency is ready.",
            "# TYPE routepilot_dependency_ready gauge",
        ]
        for dependency, value in sorted(self._dependencies.items()):
            lines.append(f'routepilot_dependency_ready{{dependency="{dependency}"}} {value}')
        lines.extend(
            [
                "# HELP routepilot_http_requests_total HTTP requests by template and status class.",
                "# TYPE routepilot_http_requests_total counter",
            ]
        )
        for (method, route, status_class), value in sorted(self._request_counts.items()):
            labels = (
                f'method="{self._label(method)}",route="{self._label(route)}",'
                f'status_class="{status_class}"'
            )
            lines.append(f"routepilot_http_requests_total{{{labels}}} {value}")
        lines.extend(
            [
                "# HELP routepilot_http_request_duration_seconds HTTP request duration.",
                "# TYPE routepilot_http_request_duration_seconds histogram",
            ]
        )
        for method, route in sorted(self._duration_counts):
            labels = f'method="{self._label(method)}",route="{self._label(route)}"'
            for bucket in self.BUCKETS:
                value = self._duration_buckets[(method, route, bucket)]
                lines.append(
                    "routepilot_http_request_duration_seconds_bucket"
                    f'{{{labels},le="{bucket:g}"}} {value}'
                )
            count = self._duration_counts[(method, route)]
            lines.append(
                "routepilot_http_request_duration_seconds_bucket"
                f'{{{labels},le="+Inf"}} {count}'
            )
            duration_sum = self._duration_sums[(method, route)]
            safe_sum = duration_sum if math.isfinite(duration_sum) else 0.0
            lines.append(f"routepilot_http_request_duration_seconds_sum{{{labels}}} {safe_sum:.9g}")
            lines.append(f"routepilot_http_request_duration_seconds_count{{{labels}}} {count}")
        return "\n".join(lines) + "\n"


__all__ = ["DependencyReadiness", "OperationalMetrics", "ReadinessReport"]
