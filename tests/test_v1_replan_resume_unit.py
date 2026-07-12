"""Pinned structural replanning and durable Product Run resume tests."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import timedelta

import pytest

from backend.moyuan_web.v1.models import (
    ArtifactCommandRequest,
    ArtifactStatus,
    Principal,
    RunCommand,
    RunCreateRequest,
    RunInputField,
    RunLifecycle,
    RunPendingInput,
    RunResumeRequest,
    TripCreateRequest,
    utc_now,
)
from backend.moyuan_web.v1.runtime import ExecutionResult, RunCoordinator
from backend.moyuan_web.v1.store import (
    InMemoryPlatformStore,
    RunInputExpired,
    RunInputInvalid,
    VersionConflict,
    canonical_request_hash,
)
from tests.contract.samples import build_valid_contracts


class CompletingExecutor:
    calls = 0

    async def execute(self, run, principal, progress):
        self.calls += 1
        await progress("planning", "测试恢复执行", 50)
        return ExecutionResult(
            artifact_type="TripSnapshot",
            schema_version=1,
            content={"schema_version": 1, "source_run_id": run.run_id},
        )


async def _published_snapshot(store: InMemoryPlatformStore, principal: Principal):
    trip = await store.create_trip(principal, TripCreateRequest(title="结构化重规划"))
    content = deepcopy(build_valid_contracts()["TripSnapshot@1"])
    content["artifact_id"] = "snapshot_replan_001"
    content["trip_id"] = trip.trip_id
    artifact = await store.create_artifact(
        principal,
        trip_id=trip.trip_id,
        artifact_id=content["artifact_id"],
        artifact_type="TripSnapshot",
        schema_version=1,
        content=content,
        status=ArtifactStatus.VALIDATED,
    )
    await store.command_artifact(
        principal,
        artifact.artifact_id,
        ArtifactCommandRequest(type="artifact.publish", base_version=artifact.version),
        idempotency_key="publish-replan-base",
        request_hash=canonical_request_hash({"artifact": artifact.artifact_id}),
    )
    return trip, artifact


@pytest.mark.asyncio
async def test_replan_pins_snapshot_and_preserves_unmodified_brief_fields() -> None:
    store = InMemoryPlatformStore()
    principal = Principal(tenant_id="tenant-replan", user_id="owner-replan")
    trip, artifact = await _published_snapshot(store, principal)
    coordinator = RunCoordinator(store, CompletingExecutor(), in_process_execution=False)
    created = await coordinator.submit(
        principal,
        trip.trip_id,
        RunCreateRequest(
            command=RunCommand(
                type="trip.replan",
                message="预算降低，保留博物馆，避开夜市",
                payload={
                    "patch": {
                        "budget": {"min_amount": "1000", "max_amount": "3000", "currency": "CNY"},
                        "preferences": {"add": ["建筑"], "remove": []},
                        "retain_places": ["故宫博物院"],
                        "exclude_places": ["夜市"],
                    }
                },
            ),
            base_artifact_id=artifact.artifact_id,
            base_artifact_version=artifact.version,
        ),
        idempotency_key="replan-pinned-001",
        trace_id="trace-replan-001",
    )
    brief = created.run.command.payload["trip_brief"]
    assert created.run.base_artifact_id == artifact.artifact_id
    assert created.run.base_artifact_version == artifact.version
    assert brief["destination"] == artifact.content["brief"]["destination"]
    assert brief["travelers"] == artifact.content["brief"]["travelers"]
    assert brief["budget"]["max_amount"] == "3000"
    descriptions = {item["description"] for item in brief["constraints"]}
    assert {"故宫博物院", "夜市"}.issubset(descriptions)


@pytest.mark.asyncio
async def test_replan_rejects_a_superseded_base_snapshot() -> None:
    store = InMemoryPlatformStore()
    principal = Principal(tenant_id="tenant-replan-stale", user_id="owner-replan")
    trip, old = await _published_snapshot(store, principal)
    newer_content = deepcopy(old.content)
    newer_content["artifact_id"] = "snapshot_replan_002"
    newer = await store.create_artifact(
        principal,
        trip_id=trip.trip_id,
        artifact_id=newer_content["artifact_id"],
        artifact_type="TripSnapshot",
        schema_version=1,
        content=newer_content,
        status=ArtifactStatus.VALIDATED,
    )
    await store.command_artifact(
        principal,
        newer.artifact_id,
        ArtifactCommandRequest(type="artifact.publish", base_version=1),
        idempotency_key="publish-newer-replan-base",
        request_hash=canonical_request_hash({"artifact": newer.artifact_id}),
    )
    coordinator = RunCoordinator(store, CompletingExecutor(), in_process_execution=False)
    with pytest.raises(VersionConflict):
        await coordinator.submit(
            principal,
            trip.trip_id,
            RunCreateRequest(
                command=RunCommand(type="trip.replan", message="过期修改", payload={"patch": {"exclude_places": ["夜市"]}}),
                base_artifact_id=old.artifact_id,
                base_artifact_version=old.version,
            ),
            idempotency_key="replan-stale-001",
            trace_id="trace-replan-stale",
        )


@pytest.mark.asyncio
async def test_waiting_run_resumes_once_with_typed_input_and_replay() -> None:
    store = InMemoryPlatformStore()
    principal = Principal(tenant_id="tenant-resume", user_id="owner-resume")
    trip = await store.create_trip(principal, TripCreateRequest(title="可恢复规划"))
    executor = CompletingExecutor()
    coordinator = RunCoordinator(store, executor)
    created = await coordinator.submit(
        principal,
        trip.trip_id,
        RunCreateRequest(command=RunCommand(type="trip.plan", message="交互规划", payload={"interactive": True})),
        idempotency_key="interactive-run-001",
        trace_id="trace-resume-001",
    )
    current = created.run
    for _ in range(100):
        current = await store.get_run(principal, created.run.run_id)
        if current.lifecycle_state == RunLifecycle.WAITING_INPUT:
            break
        await asyncio.sleep(0.01)
    assert current.pending_input is not None
    with pytest.raises(RunInputInvalid):
        await coordinator.resume(
            principal,
            current.run_id,
            RunResumeRequest(expected_control_version=current.control_version, request_id="wrong-request", values={"destination": "北京"}),
            idempotency_key="resume-wrong-001",
        )
    values = {
        "destination": "北京", "start_date": "2026-08-01", "end_date": "2026-08-03",
        "adults": 2, "seniors": 0, "budget_min": 1000, "budget_max": 4000, "currency": "CNY",
    }
    request = RunResumeRequest(expected_control_version=current.control_version, request_id=current.pending_input.request_id, values=values)
    resumed = await coordinator.resume(principal, current.run_id, request, idempotency_key="resume-correct-001")
    replayed = await coordinator.resume(principal, current.run_id, request, idempotency_key="resume-correct-001")
    assert resumed.run.lifecycle_state == RunLifecycle.QUEUED
    assert replayed.replayed is True
    for _ in range(100):
        current = await store.get_run(principal, current.run_id)
        if current.lifecycle_state in {RunLifecycle.COMPLETED, RunLifecycle.FAILED}:
            break
        await asyncio.sleep(0.01)
    assert current.lifecycle_state == RunLifecycle.COMPLETED
    assert executor.calls == 1


@pytest.mark.asyncio
async def test_expired_pending_input_cannot_resume() -> None:
    store = InMemoryPlatformStore()
    principal = Principal(tenant_id="tenant-expired", user_id="owner-expired")
    trip = await store.create_trip(principal, TripCreateRequest(title="过期恢复"))
    created = await store.create_run(
        principal,
        trip_id=trip.trip_id,
        command=RunCommand(type="trip.plan", message="过期输入"),
        base_artifact_id=None,
        base_artifact_version=None,
        idempotency_key="expired-run-001",
        request_hash="expired-run-hash",
        trace_id="trace-expired",
    )
    pending = RunPendingInput(
        request_id="input-expired-001",
        prompt="已过期",
        fields=[RunInputField(field_id="destination", label="目的地", input_type="text")],
        expires_at=utc_now() - timedelta(seconds=1),
    )
    waiting, _ = await store.mutate_run(
        principal,
        created.run.run_id,
        expected_control_version=created.run.control_version,
        lifecycle_state=RunLifecycle.WAITING_INPUT,
        pending_input=pending,
        event_type="input.required",
        event_data=pending.model_dump(mode="json"),
    )
    with pytest.raises(RunInputExpired):
        await store.resume_run(
            principal,
            waiting.run_id,
            expected_control_version=waiting.control_version,
            request_id=pending.request_id,
            values={"destination": "北京"},
            idempotency_key="expired-resume-001",
            request_hash="expired-resume-hash",
        )
