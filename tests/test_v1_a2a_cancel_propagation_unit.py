"""Product Run cancellation remains retryable until A2A cancellation is durable."""

from __future__ import annotations

import pytest

from backend.moyuan_web.v1.models import (
    Principal,
    RunCreateRequest,
    RunLifecycle,
    TripCreateRequest,
)
from backend.moyuan_web.v1.runtime import RunCoordinator
from backend.moyuan_web.v1.store import InMemoryPlatformStore


class UnusedExecutor:
    async def execute(self, run, principal, progress):  # pragma: no cover
        raise AssertionError("external-mode cancellation must not execute the Run")


@pytest.mark.asyncio
async def test_cancel_requested_retries_a2a_propagation_before_terminal_state() -> None:
    principal = Principal(
        tenant_id="tenant-a",
        user_id="owner-a",
        roles=frozenset({"owner"}),
    )
    store = InMemoryPlatformStore()
    calls: list[tuple[str, str]] = []

    async def cancel_run_tasks(actor: Principal, run_id: str) -> None:
        calls.append((actor.tenant_id, run_id))
        if len(calls) == 1:
            raise RuntimeError("temporary A2A store outage")

    coordinator = RunCoordinator(
        store,
        UnusedExecutor(),
        in_process_execution=False,
        cancel_run_tasks=cancel_run_tasks,
    )
    trip = await store.create_trip(principal, TripCreateRequest(title="恢复取消"))
    submitted = await coordinator.submit(
        principal,
        trip.trip_id,
        RunCreateRequest.model_validate(
            {"command": {"type": "trip.plan", "message": "生成慢行程"}}
        ),
        idempotency_key="cancel-propagation-run",
        trace_id="trace-cancel-propagation",
    )

    with pytest.raises(RuntimeError, match="temporary A2A store outage"):
        await coordinator.cancel(
            principal,
            submitted.run.run_id,
            expected_control_version=submitted.run.control_version,
        )
    pending = await store.get_run(principal, submitted.run.run_id)
    assert pending.lifecycle_state == RunLifecycle.CANCEL_REQUESTED

    await coordinator.cancel(
        principal,
        submitted.run.run_id,
        expected_control_version=pending.control_version,
    )
    terminal = await store.get_run(principal, submitted.run.run_id)
    assert terminal.lifecycle_state == RunLifecycle.CANCELED
    assert calls == [
        (principal.tenant_id, submitted.run.run_id),
        (principal.tenant_id, submitted.run.run_id),
    ]
