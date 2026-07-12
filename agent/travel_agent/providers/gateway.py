"""Resilient, allowlisted control plane for live-data provider calls."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import random
import time
from collections import defaultdict, deque
from collections.abc import Awaitable, Callable, Iterable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, cast

from pydantic import BaseModel, ValidationError

from .amap import AMapProvider
from .errors import (
    ProviderCancelledError,
    ProviderCircuitOpenError,
    ProviderError,
    ProviderIdempotencyConflictError,
    ProviderInputError,
    ProviderNotAllowedError,
    ProviderRateLimitedError,
    ProviderResponseError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from .models import (
    GeocodeRequest,
    GeocodeResult,
    FreshnessStatus,
    OpeningHoursRequest,
    OpeningHoursResult,
    PlaceSearchRequest,
    PlaceSearchResult,
    ProviderCapability,
    ProviderDescriptor,
    ProviderHealth,
    RouteMatrixRequest,
    RouteMatrixResult,
    WeatherRequest,
    WeatherResult,
)
from .ports import CacheScope, ProviderCallContext, ProviderPort
from .settings import ProviderSettings
from .unavailable import UnavailableProvider

ProviderResult = (
    PlaceSearchResult | GeocodeResult | RouteMatrixResult | OpeningHoursResult | WeatherResult
)
@dataclass(frozen=True, slots=True)
class GatewayPolicy:
    """Bounded resilience policy; values are validated at construction."""

    default_deadline_seconds: float = 4.0
    maximum_deadline_seconds: float = 15.0
    max_retries: int = 1
    backoff_seconds: float = 0.05
    jitter_seconds: float = 0.05
    rate_limit_requests: int = 60
    rate_limit_window_seconds: float = 60.0
    circuit_failure_threshold: int = 3
    circuit_open_seconds: float = 30.0
    max_concurrency_per_provider: int = 8
    max_cache_entries: int = 2_048
    max_idempotency_entries: int = 10_000
    idempotency_ttl_seconds: float = 3_600.0

    def __post_init__(self) -> None:
        if not 0.1 <= self.default_deadline_seconds <= 30:
            raise ValueError("default_deadline_seconds must be between 0.1 and 30")
        if not self.default_deadline_seconds <= self.maximum_deadline_seconds <= 30:
            raise ValueError("maximum_deadline_seconds must be between default and 30")
        if not 0 <= self.max_retries <= 2:
            raise ValueError("max_retries must be between 0 and 2")
        if not 0 <= self.backoff_seconds <= 1 or not 0 <= self.jitter_seconds <= 1:
            raise ValueError("backoff and jitter must be between 0 and 1")
        if not 1 <= self.rate_limit_requests <= 100_000:
            raise ValueError("rate_limit_requests is out of range")
        if not 0.1 <= self.rate_limit_window_seconds <= 3_600:
            raise ValueError("rate_limit_window_seconds is out of range")
        if not 1 <= self.circuit_failure_threshold <= 100:
            raise ValueError("circuit_failure_threshold is out of range")
        if not 0.1 <= self.circuit_open_seconds <= 3_600:
            raise ValueError("circuit_open_seconds is out of range")
        if not 1 <= self.max_concurrency_per_provider <= 1_000:
            raise ValueError("max_concurrency_per_provider is out of range")
        if not 1 <= self.max_cache_entries <= 100_000:
            raise ValueError("max_cache_entries is out of range")
        if not 1 <= self.max_idempotency_entries <= 1_000_000:
            raise ValueError("max_idempotency_entries is out of range")


@dataclass(slots=True)
class _Circuit:
    failures: int = 0
    opened_at: float | None = None
    half_open_inflight: bool = False


@dataclass(slots=True)
class _CacheEntry:
    result: ProviderResult
    fresh_expires_at: float
    stale_expires_at: float
    inserted_at: float


@dataclass(slots=True)
class _IdempotencyEntry:
    request_hash: str
    result: ProviderResult
    expires_at: float


class ProviderGateway:
    """Allowlist, deadline, retry, quota, circuit, bulkhead and cache boundary."""

    DEFAULT_CACHE_TTLS = {
        ProviderCapability.PLACE_SEARCH: 900.0,
        ProviderCapability.GEOCODE: 86_400.0,
        ProviderCapability.ROUTE_MATRIX: 180.0,
        ProviderCapability.OPENING_HOURS: 300.0,
        ProviderCapability.WEATHER: 300.0,
    }
    DEFAULT_STALE_IF_ERROR = {
        ProviderCapability.PLACE_SEARCH: 3_600.0,
        ProviderCapability.GEOCODE: 604_800.0,
        ProviderCapability.ROUTE_MATRIX: 0.0,
        ProviderCapability.OPENING_HOURS: 300.0,
        ProviderCapability.WEATHER: 600.0,
    }

    def __init__(
        self,
        providers: Iterable[ProviderPort],
        *,
        allowlist: frozenset[str],
        policy: GatewayPolicy | None = None,
        cache_ttls: dict[ProviderCapability, float] | None = None,
        stale_if_error: dict[ProviderCapability, float] | None = None,
        monotonic: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        random_source: random.Random | None = None,
    ) -> None:
        self.policy = policy or GatewayPolicy()
        self._allowlist = allowlist
        self._clock = monotonic
        self._sleep = sleep
        self._random = random_source or random.SystemRandom()
        self._cache_ttls = {**self.DEFAULT_CACHE_TTLS, **(cache_ttls or {})}
        self._stale_if_error = {
            **self.DEFAULT_STALE_IF_ERROR,
            **(stale_if_error or {}),
        }
        if any(value < 0 or value > 604_800 for value in self._cache_ttls.values()):
            raise ValueError("cache TTL must be between 0 and seven days")
        if any(value < 0 or value > 604_800 for value in self._stale_if_error.values()):
            raise ValueError("stale-if-error must be between 0 and seven days")

        self._providers_by_capability: dict[ProviderCapability, list[ProviderPort]] = defaultdict(list)
        self._all_providers: dict[str, ProviderPort] = {}
        for provider in providers:
            descriptor = provider.descriptor
            if descriptor.provider_id in self._all_providers:
                raise ValueError(f"duplicate provider id: {descriptor.provider_id}")
            self._all_providers[descriptor.provider_id] = provider
            for capability in descriptor.capabilities:
                self._providers_by_capability[capability].append(provider)

        self._circuits = {provider_id: _Circuit() for provider_id in self._all_providers}
        self._bulkheads = {
            provider_id: asyncio.Semaphore(self.policy.max_concurrency_per_provider)
            for provider_id in self._all_providers
        }
        self._rate_windows: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._cache: dict[str, _CacheEntry] = {}
        self._idempotency: dict[tuple[str, str, str], _IdempotencyEntry] = {}
        self._idempotency_locks: dict[tuple[str, str, str], asyncio.Lock] = {}
        self._state_lock = asyncio.Lock()

    def descriptors(self) -> tuple[ProviderDescriptor, ...]:
        """Return non-secret registered capability metadata."""

        return tuple(
            provider.descriptor.model_copy(deep=True)
            for provider in sorted(
                self._all_providers.values(), key=lambda item: item.descriptor.provider_id
            )
        )

    def health(self) -> tuple[ProviderHealth, ...]:
        """Return metadata-only health; no probe can leak provider errors."""

        now = self._clock()
        rows: list[ProviderHealth] = []
        for provider_id, provider in sorted(self._all_providers.items()):
            circuit = self._circuits[provider_id]
            if circuit.opened_at is None:
                state: Literal["closed", "open", "half_open"] = "closed"
            elif now - circuit.opened_at >= self.policy.circuit_open_seconds:
                state = "half_open"
            else:
                state = "open"
            rows.append(
                ProviderHealth(
                    provider_id=provider_id,
                    configured=provider.descriptor.configured,
                    allowed=provider_id in self._allowlist,
                    circuit_state=state,
                    capabilities=provider.descriptor.capabilities,
                )
            )
        return tuple(rows)

    async def close(self) -> None:
        """Close each registered provider once."""

        for provider in self._all_providers.values():
            await provider.close()

    async def search_places(
        self, request: PlaceSearchRequest, context: ProviderCallContext
    ) -> PlaceSearchResult:
        return cast(
            PlaceSearchResult,
            await self._execute(
                ProviderCapability.PLACE_SEARCH, "search_places", request, context
            ),
        )

    async def geocode(
        self, request: GeocodeRequest, context: ProviderCallContext
    ) -> GeocodeResult:
        return cast(
            GeocodeResult,
            await self._execute(ProviderCapability.GEOCODE, "geocode", request, context),
        )

    async def route_matrix(
        self, request: RouteMatrixRequest, context: ProviderCallContext
    ) -> RouteMatrixResult:
        return cast(
            RouteMatrixResult,
            await self._execute(
                ProviderCapability.ROUTE_MATRIX, "route_matrix", request, context
            ),
        )

    async def opening_hours(
        self, request: OpeningHoursRequest, context: ProviderCallContext
    ) -> OpeningHoursResult:
        return cast(
            OpeningHoursResult,
            await self._execute(
                ProviderCapability.OPENING_HOURS, "opening_hours", request, context
            ),
        )

    async def weather(
        self, request: WeatherRequest, context: ProviderCallContext
    ) -> WeatherResult:
        return cast(
            WeatherResult,
            await self._execute(ProviderCapability.WEATHER, "weather", request, context),
        )

    async def _execute(
        self,
        capability: ProviderCapability,
        method_name: str,
        request: BaseModel,
        context: ProviderCallContext,
    ) -> ProviderResult:
        now = self._clock()
        requested_deadline = context.deadline_monotonic
        if requested_deadline is None:
            requested_deadline = now + self.policy.default_deadline_seconds
        deadline = min(
            requested_deadline,
            now + self.policy.maximum_deadline_seconds,
        )
        request_hash = self._request_hash(capability, request)
        operation_key = (
            (context.tenant_id, capability.value, context.idempotency_key)
            if context.idempotency_key
            else None
        )

        lock: asyncio.Lock | None = None
        if operation_key is not None:
            async with self._state_lock:
                lock = self._idempotency_locks.setdefault(operation_key, asyncio.Lock())
            await self._acquire(lock, deadline, context)
        try:
            return await self._execute_locked(
                capability,
                method_name,
                request,
                context,
                deadline,
                request_hash,
                operation_key,
            )
        finally:
            if lock is not None and lock.locked():
                lock.release()

    async def _execute_locked(
        self,
        capability: ProviderCapability,
        method_name: str,
        request: BaseModel,
        context: ProviderCallContext,
        deadline: float,
        request_hash: str,
        operation_key: tuple[str, str, str] | None,
    ) -> ProviderResult:
        self._check_cancelled(context)
        now = self._clock()
        async with self._state_lock:
            self._prune_state(now)
            if operation_key is not None:
                prior = self._idempotency.get(operation_key)
                if prior is not None:
                    if prior.request_hash != request_hash:
                        raise ProviderIdempotencyConflictError()
                    return self._with_current_freshness(prior.result)

            cache_key = self._cache_key(capability, request_hash, context)
            cached = self._cache.get(cache_key) if cache_key is not None else None
            if cached is not None and cached.fresh_expires_at > now:
                result = cached.result.model_copy(deep=True)
                if operation_key is not None:
                    self._store_idempotency_locked(operation_key, request_hash, result, now)
                return result

        providers = [
            provider
            for provider in self._providers_by_capability.get(capability, ())
            if provider.descriptor.provider_id in self._allowlist
        ]
        if not providers:
            raise ProviderNotAllowedError()

        last_error: ProviderError | None = None
        for provider in providers:
            provider_id = provider.descriptor.provider_id
            if not provider.descriptor.configured:
                # Configuration absence is a stable capability fact, not a
                # transient outage: do not spend quota/retries or trip a circuit.
                last_error = ProviderUnavailableError(provider_id=provider_id)
                continue
            for attempt in range(self.policy.max_retries + 1):
                self._check_cancelled(context)
                if self._clock() >= deadline:
                    raise ProviderTimeoutError(provider_id=provider_id)
                try:
                    await self._before_call(
                        provider_id,
                        context,
                        cost=self._rate_cost(capability, request),
                    )
                    method = getattr(provider, method_name, None)
                    if method is None or not callable(method):
                        raise ProviderUnavailableError(provider_id=provider_id)
                    result = await self._invoke(
                        provider_id,
                        method,
                        request,
                        deadline,
                        context,
                    )
                    result = self._validate_result(
                        result,
                        provider.descriptor,
                        capability,
                    )
                    await self._record_success(provider_id)
                    return await self._remember_success(
                        capability,
                        request_hash,
                        context,
                        operation_key,
                        result,
                    )
                except asyncio.CancelledError:
                    await self._release_half_open(provider_id)
                    raise
                except ProviderCancelledError:
                    await self._release_half_open(provider_id)
                    raise
                except ProviderInputError:
                    await self._release_half_open(provider_id)
                    raise
                except ProviderError as exc:
                    last_error = exc
                    await self._record_failure(provider_id, exc)
                except Exception:
                    last_error = ProviderUnavailableError(provider_id=provider_id)
                    await self._record_failure(provider_id, last_error)

                if attempt < self.policy.max_retries and last_error.retryable:
                    delay = self.policy.backoff_seconds * (2**attempt)
                    delay += self._random.random() * self.policy.jitter_seconds
                    await self._delay(delay, deadline, context)
                    continue
                break

        if last_error is not None and last_error.retryable:
            stale = await self._get_stale_fallback(
                capability,
                request_hash,
                context,
                operation_key,
            )
            if stale is not None:
                return stale
        raise last_error or ProviderUnavailableError()

    async def _remember_success(
        self,
        capability: ProviderCapability,
        request_hash: str,
        context: ProviderCallContext,
        operation_key: tuple[str, str, str] | None,
        result: ProviderResult,
    ) -> ProviderResult:
        now = self._clock()
        safe_result = result.model_copy(deep=True)
        async with self._state_lock:
            cache_key = self._cache_key(capability, request_hash, context)
            ttl = self._cache_ttls[capability]
            wall_remaining = max(
                0.0,
                (result.provenance.valid_until - datetime.now(UTC)).total_seconds(),
            )
            effective_ttl = min(ttl, wall_remaining)
            if cache_key is not None and effective_ttl > 0:
                if len(self._cache) >= self.policy.max_cache_entries:
                    oldest_key = min(self._cache, key=lambda key: self._cache[key].inserted_at)
                    self._cache.pop(oldest_key, None)
                self._cache[cache_key] = _CacheEntry(
                    result=safe_result.model_copy(deep=True),
                    fresh_expires_at=now + effective_ttl,
                    stale_expires_at=(
                        now + effective_ttl + self._stale_if_error[capability]
                    ),
                    inserted_at=now,
                )
            if operation_key is not None:
                self._store_idempotency_locked(
                    operation_key,
                    request_hash,
                    safe_result,
                    now,
                )
        return safe_result

    async def _get_stale_fallback(
        self,
        capability: ProviderCapability,
        request_hash: str,
        context: ProviderCallContext,
        operation_key: tuple[str, str, str] | None,
    ) -> ProviderResult | None:
        """Return a tenant-scoped stale observation only inside its policy window."""

        cache_key = self._cache_key(capability, request_hash, context)
        if cache_key is None or self._stale_if_error[capability] <= 0:
            return None
        now = self._clock()
        async with self._state_lock:
            cached = self._cache.get(cache_key)
            if (
                cached is None
                or cached.fresh_expires_at > now
                or cached.stale_expires_at <= now
            ):
                return None
            provenance = cached.result.provenance.model_copy(
                update={"freshness_status": FreshnessStatus.STALE}
            )
            result = cached.result.model_copy(
                deep=True,
                update={"provenance": provenance},
            )
            if operation_key is not None:
                self._store_idempotency_locked(operation_key, request_hash, result, now)
            return result

    def _store_idempotency_locked(
        self,
        operation_key: tuple[str, str, str],
        request_hash: str,
        result: ProviderResult,
        now: float,
    ) -> None:
        """Store one bounded idempotency result while ``_state_lock`` is held."""

        if len(self._idempotency) >= self.policy.max_idempotency_entries:
            earliest_key = min(
                self._idempotency,
                key=lambda key: self._idempotency[key].expires_at,
            )
            self._idempotency.pop(earliest_key, None)
        self._idempotency[operation_key] = _IdempotencyEntry(
            request_hash=request_hash,
            result=result.model_copy(deep=True),
            expires_at=now + self.policy.idempotency_ttl_seconds,
        )

    async def _before_call(
        self,
        provider_id: str,
        context: ProviderCallContext,
        *,
        cost: int,
    ) -> None:
        now = self._clock()
        async with self._state_lock:
            circuit = self._circuits[provider_id]
            if circuit.opened_at is not None:
                if now - circuit.opened_at < self.policy.circuit_open_seconds:
                    raise ProviderCircuitOpenError(provider_id=provider_id)
                if circuit.half_open_inflight:
                    raise ProviderCircuitOpenError(provider_id=provider_id)
                circuit.half_open_inflight = True

            rate_key = (provider_id, context.tenant_id)
            window = self._rate_windows[rate_key]
            cutoff = now - self.policy.rate_limit_window_seconds
            while window and window[0] <= cutoff:
                window.popleft()
            if len(window) + cost > self.policy.rate_limit_requests:
                if circuit.opened_at is not None:
                    circuit.half_open_inflight = False
                raise ProviderRateLimitedError(provider_id=provider_id)
            window.extend([now] * cost)

    async def _record_success(self, provider_id: str) -> None:
        async with self._state_lock:
            circuit = self._circuits[provider_id]
            circuit.failures = 0
            circuit.opened_at = None
            circuit.half_open_inflight = False

    async def _record_failure(self, provider_id: str, error: ProviderError) -> None:
        async with self._state_lock:
            circuit = self._circuits[provider_id]
            if circuit.opened_at is not None:
                circuit.half_open_inflight = False
            if not error.counts_toward_circuit:
                return
            circuit.failures += 1
            if circuit.failures >= self.policy.circuit_failure_threshold:
                circuit.opened_at = self._clock()
                circuit.half_open_inflight = False

    async def _release_half_open(self, provider_id: str) -> None:
        """Release a probe slot when caller cancellation/input ends the call neutrally."""

        async with self._state_lock:
            self._circuits[provider_id].half_open_inflight = False

    async def _invoke(
        self,
        provider_id: str,
        method: Callable[[BaseModel, ProviderCallContext], Awaitable[Any]],
        request: BaseModel,
        deadline: float,
        context: ProviderCallContext,
    ) -> ProviderResult:
        semaphore = self._bulkheads[provider_id]
        await self._acquire(semaphore, deadline, context)
        try:
            value = await self._await_with_cancel(method(request, context), deadline, context)
        finally:
            semaphore.release()
        if not isinstance(value, BaseModel):
            raise ProviderResponseError(provider_id=provider_id)
        return cast(ProviderResult, value)

    async def _acquire(
        self,
        lock: asyncio.Lock | asyncio.Semaphore,
        deadline: float,
        context: ProviderCallContext,
    ) -> None:
        await self._await_with_cancel(lock.acquire(), deadline, context)

    async def _await_with_cancel(
        self,
        awaitable: Awaitable[Any],
        deadline: float,
        context: ProviderCallContext,
    ) -> Any:
        remaining = deadline - self._clock()
        if remaining <= 0:
            if inspect.iscoroutine(awaitable):
                awaitable.close()
            raise ProviderTimeoutError()
        task = asyncio.ensure_future(awaitable)
        cancel_task: asyncio.Task[bool] | None = None
        try:
            if context.cancellation_event is None:
                try:
                    return await asyncio.wait_for(task, timeout=remaining)
                except TimeoutError:
                    raise ProviderTimeoutError() from None
            cancel_task = asyncio.create_task(context.cancellation_event.wait())
            done, _ = await asyncio.wait(
                {task, cancel_task},
                timeout=remaining,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if task in done:
                return await task
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            if cancel_task in done and cancel_task.result():
                raise ProviderCancelledError()
            raise ProviderTimeoutError()
        finally:
            if cancel_task is not None:
                cancel_task.cancel()
                with suppress(asyncio.CancelledError):
                    await cancel_task

    async def _delay(
        self, delay: float, deadline: float, context: ProviderCallContext
    ) -> None:
        if delay <= 0:
            return
        await self._await_with_cancel(self._sleep(delay), deadline, context)

    @staticmethod
    def _check_cancelled(context: ProviderCallContext) -> None:
        if context.cancellation_event is not None and context.cancellation_event.is_set():
            raise ProviderCancelledError()

    @staticmethod
    def _validate_result(
        result: ProviderResult,
        descriptor: ProviderDescriptor,
        capability: ProviderCapability,
    ) -> ProviderResult:
        expected_types: dict[ProviderCapability, type[BaseModel]] = {
            ProviderCapability.PLACE_SEARCH: PlaceSearchResult,
            ProviderCapability.GEOCODE: GeocodeResult,
            ProviderCapability.ROUTE_MATRIX: RouteMatrixResult,
            ProviderCapability.OPENING_HOURS: OpeningHoursResult,
            ProviderCapability.WEATHER: WeatherResult,
        }
        expected_type = expected_types[capability]
        if not isinstance(result, expected_type):
            raise ProviderResponseError(provider_id=descriptor.provider_id)
        try:
            validated = expected_type.model_validate(result.model_dump(mode="python"))
        except ValidationError:
            raise ProviderResponseError(provider_id=descriptor.provider_id) from None
        provenance = getattr(validated, "provenance", None)
        if (
            provenance is None
            or provenance.provider_id != descriptor.provider_id
            or provenance.provider_version != descriptor.api_version
            or provenance.capability != capability
        ):
            raise ProviderResponseError(provider_id=descriptor.provider_id)
        return cast(ProviderResult, validated)

    @staticmethod
    def _request_hash(capability: ProviderCapability, request: BaseModel) -> str:
        payload = json.dumps(
            {
                "capability": capability.value,
                "request": request.model_dump(mode="json"),
            },
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()

    @staticmethod
    def _with_current_freshness(result: ProviderResult) -> ProviderResult:
        """Never replay an expired idempotent observation as fresh."""

        if (
            result.provenance.freshness_status is FreshnessStatus.FRESH
            and result.provenance.valid_until <= datetime.now(UTC)
        ):
            provenance = result.provenance.model_copy(
                update={"freshness_status": FreshnessStatus.STALE}
            )
            return result.model_copy(deep=True, update={"provenance": provenance})
        return result.model_copy(deep=True)

    @staticmethod
    def _rate_cost(capability: ProviderCapability, request: BaseModel) -> int:
        """Charge physical calls hidden behind one provider-port operation."""

        if capability is ProviderCapability.ROUTE_MATRIX and isinstance(
            request, RouteMatrixRequest
        ):
            return len(request.destinations)
        if capability is ProviderCapability.OPENING_HOURS and isinstance(
            request, OpeningHoursRequest
        ):
            return (len(request.provider_place_ids) + 9) // 10
        return 1

    @staticmethod
    def _cache_key(
        capability: ProviderCapability,
        request_hash: str,
        context: ProviderCallContext,
    ) -> str | None:
        if context.cache_scope is CacheScope.DISABLED:
            return None
        if context.cache_scope is CacheScope.PUBLIC:
            scope = "public"
        else:
            # Private/user-derived requests can never cross tenant boundaries.
            scope = f"tenant:{context.tenant_id}"
        return f"{scope}:{capability.value}:{request_hash}"

    def _prune_state(self, now: float) -> None:
        self._cache = {
            key: value
            for key, value in self._cache.items()
            if value.stale_expires_at > now
        }
        self._idempotency = {
            key: value for key, value in self._idempotency.items() if value.expires_at > now
        }
        cutoff = now - self.policy.rate_limit_window_seconds
        for key, window in tuple(self._rate_windows.items()):
            while window and window[0] <= cutoff:
                window.popleft()
            if not window:
                self._rate_windows.pop(key, None)
        active_keys = set(self._idempotency)
        self._idempotency_locks = {
            key: lock
            for key, lock in self._idempotency_locks.items()
            if key in active_keys or lock.locked()
        }


def build_default_provider_gateway(
    settings: ProviderSettings | None = None,
) -> ProviderGateway:
    """Build secure-by-default providers from one canonical settings namespace."""

    resolved = settings or ProviderSettings.from_environment()
    if resolved.amap_web_key is not None:
        amap: ProviderPort = AMapProvider(
            api_key=resolved.amap_web_key,
            timeout_seconds=resolved.amap_http_timeout_seconds,
        )
    else:
        amap = UnavailableProvider(
            provider_id="amap",
            display_name="AMap Web Service",
            capabilities=frozenset(
                {
                    ProviderCapability.PLACE_SEARCH,
                    ProviderCapability.GEOCODE,
                    ProviderCapability.ROUTE_MATRIX,
                    ProviderCapability.OPENING_HOURS,
                    ProviderCapability.WEATHER,
                }
            ),
        )
    return ProviderGateway(
        [amap],
        allowlist=resolved.provider_allowlist,
    )


__all__ = ["GatewayPolicy", "ProviderGateway", "build_default_provider_gateway"]
