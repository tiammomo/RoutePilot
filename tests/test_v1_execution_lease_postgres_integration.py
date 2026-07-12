"""Opt-in PostgreSQL parity test for Product Run execution fencing."""

from __future__ import annotations

import asyncio
import os

import pytest

from backend.moyuan_web.v1.models import (
    ArtifactStatus,
    Principal,
    RunCommand,
    RunLifecycle,
    TripCreateRequest,
)
from backend.moyuan_web.v1.postgres_store import PostgresPlatformStore
from backend.moyuan_web.v1.store import RunExecutionLeaseLost


@pytest.mark.asyncio
async def test_postgres_execution_lease_claim_recovery_and_fencing() -> None:
    dsn = os.getenv("ROUTEPILOT_TEST_POSTGRES_DSN", "").strip()
    if not dsn:
        pytest.skip("set ROUTEPILOT_TEST_POSTGRES_DSN to run PostgreSQL lease parity")

    store = PostgresPlatformStore.from_database_url(dsn)
    principal = Principal(tenant_id="tenant-run-lease-pg", user_id="owner-run-lease-pg")
    try:
        trip = await store.create_trip(principal, TripCreateRequest(title="PG Run Lease"))
        submitted = await store.create_run(
            principal,
            trip_id=trip.trip_id,
            command=RunCommand(type="trip.plan", message="验证 PostgreSQL 租约"),
            base_artifact_id=None,
            base_artifact_version=None,
            idempotency_key=f"pg-run-lease-{trip.trip_id}",
            request_hash="pg-run-lease-request-hash",
            trace_id=f"trace-{trip.trip_id}"[:96],
        )
        first = await store.claim_run_execution(
            principal,
            submitted.run.run_id,
            owner="pg-worker-old",
            lease_seconds=0.05,
        )
        assert first is not None
        assert await store.claim_run_execution(
            principal,
            submitted.run.run_id,
            owner="pg-worker-contender",
            lease_seconds=1,
        ) is None
        running, _ = await store.mutate_run(
            principal,
            submitted.run.run_id,
            expected_control_version=submitted.run.control_version,
            lifecycle_state=RunLifecycle.RUNNING,
            phase="starting",
            execution_lease=first,
            event_type="run.lifecycle_changed",
            event_data={"lifecycle_state": RunLifecycle.RUNNING.value},
        )

        await asyncio.sleep(0.07)
        recovered = await store.claim_run_execution(
            principal,
            submitted.run.run_id,
            owner="pg-worker-recovered",
            lease_seconds=2,
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

        cancel_requested, _ = await store.mutate_run(
            principal,
            running.run_id,
            expected_control_version=running.control_version,
            lifecycle_state=RunLifecycle.CANCEL_REQUESTED,
            phase="canceling",
            event_type="run.lifecycle_changed",
            event_data={"lifecycle_state": RunLifecycle.CANCEL_REQUESTED.value},
        )
        assert cancel_requested.lifecycle_state == RunLifecycle.CANCEL_REQUESTED
        assert await store.renew_run_execution(
            principal,
            recovered,
            lease_seconds=1,
        ) is None
    finally:
        await store.close()
