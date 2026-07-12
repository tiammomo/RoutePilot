"""Redis Streams adapter for independently executing durable Product Runs."""

from __future__ import annotations

import json
from hashlib import sha256
from typing import Any

from pydantic import Field
from redis.asyncio import Redis

from .models import Principal, StrictModel
from .runtime import V1Runtime
from .store import RunExecutionBusy, RunExecutionLeaseLost


class RunDispatchMessage(StrictModel):
    """Internal, size-bounded dispatch payload emitted through the outbox."""

    tenant_id: str = Field(min_length=1, max_length=128)
    actor_id: str = Field(min_length=1, max_length=128)
    trip_id: str = Field(min_length=1, max_length=96)
    run_id: str = Field(min_length=1, max_length=96)
    trace_id: str = Field(min_length=1, max_length=96)
    control_version: int = Field(ge=1)


class RedisRunWorker:
    """Consume idempotent run dispatches; browser events remain in PostgreSQL."""

    def __init__(
        self,
        redis: Redis,
        runtime: V1Runtime,
        *,
        stream: str = "routepilot:v1:outbox",
        group: str = "routepilot-v1-run-workers",
        consumer: str,
        lease_seconds: float = 60.0,
        reclaim_idle_milliseconds: int | None = None,
    ) -> None:
        if not consumer or len(consumer) > 128:
            raise ValueError("consumer must be between 1 and 128 characters")
        self.redis = redis
        self.runtime = runtime
        self.stream = stream
        self.group = group
        self.consumer = consumer
        if not 0.05 <= lease_seconds <= 3_600:
            raise ValueError("lease_seconds must be between 0.05 and 3600")
        self.lease_seconds = lease_seconds
        resolved_reclaim_idle = (
            int(lease_seconds * 1_000)
            if reclaim_idle_milliseconds is None
            else reclaim_idle_milliseconds
        )
        if not 1 <= resolved_reclaim_idle <= 86_400_000:
            raise ValueError("reclaim idle time must be between 1ms and 24h")
        self.reclaim_idle_milliseconds = resolved_reclaim_idle

    async def ensure_group(self) -> None:
        try:
            await self.redis.xgroup_create(self.stream, self.group, id="0", mkstream=True)
        except Exception as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def _dead_letter(self, entry_id: str, error_code: str) -> None:
        await self.redis.xadd(
            f"{self.stream}:dead-letter",
            {
                "entry_id": entry_id,
                "error_code": error_code[:96],
            },
            maxlen=10_000,
            approximate=True,
        )

    async def process_entry(self, entry_id: str, fields: dict[str, Any]) -> bool:
        event_type = str(fields.get("event_type") or "")
        if event_type != "run.dispatch.requested":
            return True
        raw_payload = fields.get("payload")
        if not isinstance(raw_payload, str) or len(raw_payload) > 32_768:
            await self._dead_letter(entry_id, "INVALID_DISPATCH_PAYLOAD")
            return True
        try:
            decoded = json.loads(raw_payload)
            dispatch = RunDispatchMessage.model_validate(decoded)
        except (TypeError, ValueError, json.JSONDecodeError):
            await self._dead_letter(entry_id, "INVALID_DISPATCH_PAYLOAD")
            return True

        principal = Principal(
            tenant_id=dispatch.tenant_id,
            user_id=dispatch.actor_id,
            roles=frozenset({"owner"}),
        )
        try:
            run = await self.runtime.store.get_run(principal, dispatch.run_id)
            if (
                run.trip_id != dispatch.trip_id
                or run.trace_id != dispatch.trace_id
                or run.actor_id != dispatch.actor_id
                or run.control_version < dispatch.control_version
            ):
                await self._dead_letter(entry_id, "DISPATCH_FENCE_MISMATCH")
                return True
            entry_digest = sha256(str(entry_id).encode("utf-8")).hexdigest()[:24]
            execution_owner = f"{self.consumer[:96]}:{entry_digest}"
            await self.runtime.coordinator.execute_existing(
                principal,
                dispatch.run_id,
                execution_owner=execution_owner,
                lease_seconds=self.lease_seconds,
            )
        except (RunExecutionBusy, RunExecutionLeaseLost):
            return False
        except Exception:
            return False
        return True

    async def _process_entries(self, entries: list[Any]) -> int:
        processed = 0
        for entry_id, fields in entries:
            acknowledged = await self.process_entry(str(entry_id), fields)
            if acknowledged:
                await self.redis.xack(self.stream, self.group, entry_id)
            processed += 1
        return processed

    async def _reclaim_stale(self, *, count: int) -> list[Any]:
        response = await self.redis.xautoclaim(
            self.stream,
            self.group,
            self.consumer,
            min_idle_time=self.reclaim_idle_milliseconds,
            start_id="0-0",
            count=count,
        )
        if not response or len(response) < 2:
            return []
        entries = response[1]
        return list(entries) if isinstance(entries, (list, tuple)) else []

    async def run_once(self, *, block_milliseconds: int = 1_000, count: int = 10) -> int:
        await self.ensure_group()
        bounded_count = max(1, min(count, 100))
        reclaimed = await self._reclaim_stale(count=bounded_count)
        processed = await self._process_entries(reclaimed)
        remaining = bounded_count - processed
        if remaining <= 0:
            return processed
        response = await self.redis.xreadgroup(
            self.group,
            self.consumer,
            {self.stream: ">"},
            count=remaining,
            block=1 if processed else max(1, block_milliseconds),
        )
        for _stream_name, entries in response:
            processed += await self._process_entries(list(entries))
        return processed

    async def close(self) -> None:
        await self.runtime.close()
        await self.redis.aclose()
