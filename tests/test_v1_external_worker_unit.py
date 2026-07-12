"""Independent worker boundary and idempotent dispatch tests."""

from __future__ import annotations

import asyncio
import json

import pytest

from backend.moyuan_web.v1.models import (
    ArtifactStatus,
    Principal,
    RunCommand,
    RunCreateRequest,
    RunLifecycle,
    TripCreateRequest,
)
from backend.moyuan_web.v1.runtime import ExecutionResult, RunCoordinator, V1Runtime
from backend.moyuan_web.v1.store import InMemoryPlatformStore
from backend.moyuan_web.v1.store import RunExecutionBusy, RunExecutionLeaseLost
from backend.moyuan_web.v1.worker import RedisRunWorker


class FakeExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(self, run, principal, progress):
        self.calls += 1
        await progress("planning", "正在生成", 50)
        return ExecutionResult(
            artifact_type="TripSnapshot",
            schema_version=1,
            content={"answer": "ok", "artifact": {}, "source_run_id": run.run_id},
        )


class FakeRedis:
    def __init__(self) -> None:
        self.dead_letters: list[tuple[str, dict[str, str]]] = []

    async def xadd(self, stream, fields, **_kwargs):
        self.dead_letters.append((stream, fields))
        return "1-0"


class FakeStreamsRedis(FakeRedis):
    def __init__(self, reclaimed: list[tuple[str, dict[str, str]]]) -> None:
        super().__init__()
        self.reclaimed = reclaimed
        self.acked: list[str] = []
        self.autoclaim_calls = 0

    async def xgroup_create(self, *_args, **_kwargs):
        return True

    async def xautoclaim(self, *_args, **_kwargs):
        self.autoclaim_calls += 1
        return ["0-0", list(self.reclaimed), []]

    async def xreadgroup(self, *_args, **_kwargs):
        return []

    async def xack(self, _stream, _group, entry_id):
        self.acked.append(str(entry_id))
        self.reclaimed = [item for item in self.reclaimed if item[0] != str(entry_id)]
        return 1


class GatedExecutor(FakeExecutor):
    def __init__(self) -> None:
        super().__init__()
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(self, run, principal, progress):
        self.calls += 1
        await progress("planning", "正在生成", 50)
        self.started.set()
        await self.release.wait()
        return ExecutionResult(
            artifact_type="TripSnapshot",
            schema_version=1,
            content={"answer": "late", "artifact": {}, "source_run_id": run.run_id},
        )


@pytest.mark.asyncio
async def test_external_run_waits_for_dispatch_and_executes_exactly_once() -> None:
    store = InMemoryPlatformStore()
    executor = FakeExecutor()
    runtime = V1Runtime(
        store=store,
        coordinator=RunCoordinator(store, executor, in_process_execution=False),
    )
    principal = Principal(tenant_id="tenant-a", user_id="user-a", roles=frozenset({"owner"}))
    trip = await store.create_trip(principal, TripCreateRequest(title="北京"))
    submitted = await runtime.coordinator.submit(
        principal,
        trip.trip_id,
        RunCreateRequest(command=RunCommand(type="trip.plan", message="两日行程")),
        idempotency_key="external-worker-test",
        trace_id="trace-external-worker",
    )

    assert submitted.run.lifecycle_state == RunLifecycle.QUEUED
    assert executor.calls == 0

    worker = RedisRunWorker(FakeRedis(), runtime, consumer="test-worker")  # type: ignore[arg-type]
    payload = {
        "tenant_id": principal.tenant_id,
        "actor_id": principal.user_id,
        "trip_id": trip.trip_id,
        "run_id": submitted.run.run_id,
        "trace_id": submitted.run.trace_id,
        "control_version": submitted.run.control_version,
    }
    first = await worker.process_entry(
        "1-0",
        {"event_type": "run.dispatch.requested", "payload": json.dumps(payload)},
    )
    replay = await worker.process_entry(
        "1-1",
        {"event_type": "run.dispatch.requested", "payload": json.dumps(payload)},
    )

    assert first is True
    assert replay is True
    assert executor.calls == 1
    assert (await store.get_run(principal, submitted.run.run_id)).lifecycle_state == RunLifecycle.COMPLETED


@pytest.mark.asyncio
async def test_invalid_dispatch_is_dead_lettered_without_execution() -> None:
    store = InMemoryPlatformStore()
    runtime = V1Runtime(
        store=store,
        coordinator=RunCoordinator(store, FakeExecutor(), in_process_execution=False),
    )
    redis = FakeRedis()
    worker = RedisRunWorker(redis, runtime, consumer="test-worker")  # type: ignore[arg-type]

    acknowledged = await worker.process_entry(
        "2-0",
        {"event_type": "run.dispatch.requested", "payload": "not-json"},
    )

    assert acknowledged is True
    assert redis.dead_letters[0][0].endswith(":dead-letter")
    assert redis.dead_letters[0][1]["error_code"] == "INVALID_DISPATCH_PAYLOAD"


@pytest.mark.asyncio
async def test_external_cancel_fences_a_late_worker_result_before_artifact_creation() -> None:
    store = InMemoryPlatformStore()
    executor = GatedExecutor()
    coordinator = RunCoordinator(store, executor, in_process_execution=False)
    principal = Principal(tenant_id="tenant-a", user_id="user-a", roles=frozenset({"owner"}))
    trip = await store.create_trip(principal, TripCreateRequest(title="取消竞态"))
    submitted = await coordinator.submit(
        principal,
        trip.trip_id,
        RunCreateRequest(command=RunCommand(type="trip.plan", message="慢速规划")),
        idempotency_key="external-cancel-fence",
        trace_id="trace-external-cancel",
    )

    execution = asyncio.create_task(
        coordinator.execute_existing(principal, submitted.run.run_id)
    )
    await asyncio.wait_for(executor.started.wait(), timeout=1)
    current = await store.get_run(principal, submitted.run.run_id)
    canceled = await coordinator.cancel(
        principal,
        current.run_id,
        expected_control_version=current.control_version,
    )
    executor.release.set()
    await execution

    final = await store.get_run(principal, current.run_id)
    assert canceled.lifecycle_state == RunLifecycle.CANCEL_REQUESTED
    assert final.lifecycle_state == RunLifecycle.CANCELED
    assert final.result_artifact_id is None
    assert await store.list_artifacts(principal, trip.trip_id) == []


@pytest.mark.asyncio
async def test_execution_lease_attempt_fences_expired_worker_side_effects() -> None:
    store = InMemoryPlatformStore()
    principal = Principal(tenant_id="tenant-lease", user_id="owner-lease")
    trip = await store.create_trip(principal, TripCreateRequest(title="租约 fencing"))
    submitted = await store.create_run(
        principal,
        trip_id=trip.trip_id,
        command=RunCommand(type="trip.plan", message="恢复测试"),
        base_artifact_id=None,
        base_artifact_version=None,
        idempotency_key="lease-attempt-test",
        request_hash="request-hash",
        trace_id="trace-lease-attempt",
    )
    first = await store.claim_run_execution(
        principal,
        submitted.run.run_id,
        owner="worker-old",
        lease_seconds=0.05,
    )
    assert first is not None
    assert await store.claim_run_execution(
        principal,
        submitted.run.run_id,
        owner="worker-contender",
        lease_seconds=0.05,
    ) is None

    await asyncio.sleep(0.06)
    recovered = await store.claim_run_execution(
        principal,
        submitted.run.run_id,
        owner="worker-recovered",
        lease_seconds=1,
    )
    assert recovered is not None
    assert recovered.attempt == first.attempt + 1
    assert await store.renew_run_execution(
        principal,
        first,
        lease_seconds=1,
    ) is None
    assert await store.release_run_execution(principal, first) is False

    with pytest.raises(RunExecutionLeaseLost):
        await store.create_artifact(
            principal,
            trip_id=trip.trip_id,
            artifact_type="TripSnapshot",
            schema_version=1,
            content={"answer": "stale"},
            status=ArtifactStatus.CANDIDATE,
            execution_lease=first,
        )


@pytest.mark.asyncio
async def test_heartbeat_keeps_long_execution_single_owner() -> None:
    store = InMemoryPlatformStore()
    executor = GatedExecutor()
    coordinator = RunCoordinator(store, executor, in_process_execution=False)
    principal = Principal(tenant_id="tenant-heartbeat", user_id="owner-heartbeat")
    trip = await store.create_trip(principal, TripCreateRequest(title="续租测试"))
    submitted = await coordinator.submit(
        principal,
        trip.trip_id,
        RunCreateRequest(command=RunCommand(type="trip.plan", message="慢规划")),
        idempotency_key="heartbeat-test",
        trace_id="trace-heartbeat",
    )
    execution = asyncio.create_task(
        coordinator.execute_existing(
            principal,
            submitted.run.run_id,
            execution_owner="worker-primary",
            lease_seconds=0.09,
        )
    )
    await asyncio.wait_for(executor.started.wait(), timeout=1)
    await asyncio.sleep(0.14)
    with pytest.raises(RunExecutionBusy):
        await coordinator.execute_existing(
            principal,
            submitted.run.run_id,
            execution_owner="worker-duplicate",
            lease_seconds=0.09,
        )
    executor.release.set()
    final = await asyncio.wait_for(execution, timeout=1)
    assert final.lifecycle_state == RunLifecycle.COMPLETED
    assert executor.calls == 1


@pytest.mark.asyncio
async def test_expired_running_run_is_recovered_by_a_new_attempt() -> None:
    store = InMemoryPlatformStore()
    executor = FakeExecutor()
    coordinator = RunCoordinator(store, executor, in_process_execution=False)
    principal = Principal(tenant_id="tenant-recovery", user_id="owner-recovery")
    trip = await store.create_trip(principal, TripCreateRequest(title="崩溃恢复"))
    submitted = await coordinator.submit(
        principal,
        trip.trip_id,
        RunCreateRequest(command=RunCommand(type="trip.plan", message="恢复运行")),
        idempotency_key="running-recovery-test",
        trace_id="trace-running-recovery",
    )
    abandoned = await store.claim_run_execution(
        principal,
        submitted.run.run_id,
        owner="crashed-worker",
        lease_seconds=0.05,
    )
    assert abandoned is not None
    await store.mutate_run(
        principal,
        submitted.run.run_id,
        expected_control_version=submitted.run.control_version,
        lifecycle_state=RunLifecycle.RUNNING,
        phase="starting",
        execution_lease=abandoned,
        event_type="run.lifecycle_changed",
        event_data={"lifecycle_state": RunLifecycle.RUNNING.value},
    )

    await asyncio.sleep(0.06)
    recovered = await coordinator.execute_existing(
        principal,
        submitted.run.run_id,
        execution_owner="recovery-worker",
        lease_seconds=1,
    )
    assert recovered.lifecycle_state == RunLifecycle.COMPLETED
    assert executor.calls == 1


@pytest.mark.asyncio
async def test_worker_reclaims_pending_dispatch_and_only_acks_after_lease_claim() -> None:
    store = InMemoryPlatformStore()
    executor = FakeExecutor()
    runtime = V1Runtime(
        store=store,
        coordinator=RunCoordinator(store, executor, in_process_execution=False),
    )
    principal = Principal(tenant_id="tenant-reclaim", user_id="owner-reclaim")
    trip = await store.create_trip(principal, TripCreateRequest(title="Redis reclaim"))
    submitted = await runtime.coordinator.submit(
        principal,
        trip.trip_id,
        RunCreateRequest(command=RunCommand(type="trip.plan", message="重投递")),
        idempotency_key="redis-reclaim-test",
        trace_id="trace-redis-reclaim",
    )
    payload = json.dumps(
        {
            "tenant_id": principal.tenant_id,
            "actor_id": principal.user_id,
            "trip_id": trip.trip_id,
            "run_id": submitted.run.run_id,
            "trace_id": submitted.run.trace_id,
            "control_version": submitted.run.control_version,
        }
    )
    redis = FakeStreamsRedis(
        [("9-0", {"event_type": "run.dispatch.requested", "payload": payload})]
    )
    active = await store.claim_run_execution(
        principal,
        submitted.run.run_id,
        owner="still-alive-worker",
        lease_seconds=1,
    )
    assert active is not None
    worker = RedisRunWorker(
        redis,  # type: ignore[arg-type]
        runtime,
        consumer="recovery-consumer",
        lease_seconds=1,
        reclaim_idle_milliseconds=1,
    )

    assert await worker.run_once(block_milliseconds=1) == 1
    assert redis.autoclaim_calls == 1
    assert redis.acked == []
    assert executor.calls == 0

    assert await store.release_run_execution(principal, active) is True
    assert await worker.run_once(block_milliseconds=1) == 1
    assert redis.acked == ["9-0"]
    assert executor.calls == 1


@pytest.mark.asyncio
async def test_worker_shutdown_abandons_running_run_for_recovery_without_canceling_it() -> None:
    store = InMemoryPlatformStore()
    executor = GatedExecutor()
    coordinator = RunCoordinator(store, executor, in_process_execution=False)
    principal = Principal(tenant_id="tenant-shutdown", user_id="owner-shutdown")
    trip = await store.create_trip(principal, TripCreateRequest(title="Worker shutdown"))
    submitted = await coordinator.submit(
        principal,
        trip.trip_id,
        RunCreateRequest(command=RunCommand(type="trip.plan", message="可恢复")),
        idempotency_key="worker-shutdown-test",
        trace_id="trace-worker-shutdown",
    )
    execution = asyncio.create_task(
        coordinator.execute_existing(
            principal,
            submitted.run.run_id,
            execution_owner="worker-shutting-down",
            lease_seconds=1,
        )
    )
    await asyncio.wait_for(executor.started.wait(), timeout=1)
    execution.cancel()
    with pytest.raises(asyncio.CancelledError):
        await execution
    assert (
        await store.get_run(principal, submitted.run.run_id)
    ).lifecycle_state == RunLifecycle.RUNNING

    executor.release.set()
    recovered = await coordinator.execute_existing(
        principal,
        submitted.run.run_id,
        execution_owner="worker-after-restart",
        lease_seconds=1,
    )
    assert recovered.lifecycle_state == RunLifecycle.COMPLETED
    assert executor.calls == 2
