"""Opt-in Redis Streams integration for stale Product Run dispatch reclaim."""

from __future__ import annotations

import asyncio
import json
import os
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from backend.moyuan_web.v1.models import (
    Principal,
    RunCommand,
    RunCreateRequest,
    RunLifecycle,
    TripCreateRequest,
)
from backend.moyuan_web.v1.runtime import ExecutionResult, RunCoordinator, V1Runtime
from backend.moyuan_web.v1.store import InMemoryPlatformStore
from backend.moyuan_web.v1.worker import RedisRunWorker


class RedisIntegrationExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, run, principal, progress):
        self.calls += 1
        await progress("planning", "reclaimed", 50)
        return ExecutionResult(
            artifact_type="TripSnapshot",
            schema_version=1,
            content={"answer": "ok", "artifact": {}, "source_run_id": run.run_id},
        )


@pytest.mark.asyncio
async def test_real_redis_xautoclaim_recovers_and_acks_stale_dispatch() -> None:
    redis_url = os.getenv("ROUTEPILOT_TEST_REDIS_URL", "").strip()
    if not redis_url:
        pytest.skip("set ROUTEPILOT_TEST_REDIS_URL to run Redis reclaim integration")

    redis = Redis.from_url(redis_url, decode_responses=True)
    suffix = uuid4().hex
    stream = f"routepilot:test:run-reclaim:{suffix}"
    group = f"routepilot-test-{suffix}"
    store = InMemoryPlatformStore()
    executor = RedisIntegrationExecutor()
    runtime = V1Runtime(
        store=store,
        coordinator=RunCoordinator(store, executor, in_process_execution=False),
    )
    principal = Principal(tenant_id="tenant-redis-real", user_id="owner-redis-real")
    worker = RedisRunWorker(
        redis,
        runtime,
        stream=stream,
        group=group,
        consumer="recovery-worker",
        lease_seconds=1,
        reclaim_idle_milliseconds=5,
    )
    try:
        trip = await store.create_trip(principal, TripCreateRequest(title="Redis reclaim"))
        submitted = await runtime.coordinator.submit(
            principal,
            trip.trip_id,
            RunCreateRequest(command=RunCommand(type="trip.plan", message="恢复")),
            idempotency_key=f"redis-reclaim-{suffix}",
            trace_id=f"trace-{suffix}",
        )
        await worker.ensure_group()
        entry_id = await redis.xadd(
            stream,
            {
                "event_type": "run.dispatch.requested",
                "payload": json.dumps(
                    {
                        "tenant_id": principal.tenant_id,
                        "actor_id": principal.user_id,
                        "trip_id": trip.trip_id,
                        "run_id": submitted.run.run_id,
                        "trace_id": submitted.run.trace_id,
                        "control_version": submitted.run.control_version,
                    }
                ),
            },
        )
        delivered = await redis.xreadgroup(
            group,
            "crashed-worker",
            {stream: ">"},
            count=1,
        )
        assert delivered[0][1][0][0] == entry_id
        await asyncio.sleep(0.02)

        assert await worker.run_once(block_milliseconds=1) == 1
        final = await store.get_run(principal, submitted.run.run_id)
        pending = await redis.xpending(stream, group)
        assert final.lifecycle_state == RunLifecycle.COMPLETED
        assert executor.calls == 1
        assert pending["pending"] == 0
    finally:
        await runtime.close()
        await redis.delete(stream)
        await redis.aclose()
