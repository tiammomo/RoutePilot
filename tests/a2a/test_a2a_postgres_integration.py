"""Optional real-PostgreSQL verification of the complete A2A persistence port."""

from __future__ import annotations

import asyncio
import os
from dataclasses import replace

import pytest
from a2a.types import TaskState

from agent.travel_agent.a2a.models import A2AActor, InputResponse
from agent.travel_agent.a2a.postgres_store import PostgresAgentTaskStore
from agent.travel_agent.a2a.registry import build_default_registry
from agent.travel_agent.a2a.service import TaskService
from agent.travel_agent.a2a.store import (
    TaskExecutionLeaseLost,
    TaskMissing,
    TaskVersionConflict,
)
from tests.a2a.test_a2a_execution_recovery_unit import (
    RecoveryExecutor,
    _allow_contracts,
)
from tests.a2a.test_a2a_postgres_store_unit import sample_record, working_record


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_a2a_create_dedupe_cas_event_replay_and_tenant_scope():
    dsn = os.getenv("ROUTEPILOT_A2A_TEST_DSN", "").strip()
    if not dsn:
        pytest.skip("ROUTEPILOT_A2A_TEST_DSN is not configured")
    store = PostgresAgentTaskStore.from_database_url(dsn, poll_interval_seconds=0.01)
    contender_store = PostgresAgentTaskStore.from_database_url(
        dsn,
        poll_interval_seconds=0.01,
    )
    initial = sample_record()
    try:
        created, was_created = await store.create_or_get(initial)
        duplicate, duplicate_created = await store.create_or_get(initial)
        assert was_created is True
        assert duplicate_created is False
        assert duplicate.task.id == created.task.id

        claims = await asyncio.gather(
            store.claim_execution(
                initial.tenant_id,
                initial.agent_interface_id,
                initial.task.id,
                owner="integration-worker-a",
                lease_seconds=5,
            ),
            contender_store.claim_execution(
                initial.tenant_id,
                initial.agent_interface_id,
                initial.task.id,
                owner="integration-worker-b",
                lease_seconds=5,
            ),
        )
        winners = [claim for claim in claims if claim is not None]
        assert len(winners) == 1
        lease = winners[0]
        assert (
            await store.claim_execution(
                initial.tenant_id,
                initial.agent_interface_id,
                initial.task.id,
                owner="integration-worker-b",
                lease_seconds=5,
            )
            is None
        )
        resume_input = InputResponse(
            request_id="clarify_dates",
            values={"start_date": "2026-10-01"},
        )
        replacement = replace(
            working_record(created),
            execution_input=resume_input,
        )
        stored = await store.replace(
            replacement,
            expected_version=1,
            execution_lease=lease,
        )
        assert stored.version == 2
        assert len(stored.events) == 1
        assert await store.renew_execution(lease, lease_seconds=5) is not None
        await store.release_execution(lease)
        successor = await store.claim_execution(
            initial.tenant_id,
            initial.agent_interface_id,
            initial.task.id,
            owner="integration-worker-b",
            lease_seconds=5,
        )
        assert successor is not None
        assert successor.attempt == lease.attempt + 1
        with pytest.raises(TaskExecutionLeaseLost):
            await store.replace(
                replace(stored, version=stored.version + 1),
                expected_version=stored.version,
                execution_lease=lease,
            )
        await store.release_execution(successor)

        fetched = await store.get(
            initial.tenant_id,
            initial.agent_interface_id,
            initial.task.id,
        )
        assert fetched.task == replacement.task
        assert fetched.execution_input == resume_input
        assert fetched.events[0].event == replacement.events[0].event
        assert (
            await store.wait_for_change(
                initial.tenant_id,
                initial.agent_interface_id,
                initial.task.id,
                after_version=1,
                timeout_seconds=0.1,
            )
            == fetched
        )
        assert [
            item.task.id
            for item in await store.list(
                initial.tenant_id,
                initial.agent_interface_id,
                context_id=initial.task.context_id,
            )
        ] == [initial.task.id]
        assert initial.task.id in {
            item.task.id for item in await store.list_for_run(initial.tenant_id, initial.run_id)
        }

        with pytest.raises(TaskMissing):
            await store.get("another-tenant", initial.agent_interface_id, initial.task.id)
        with pytest.raises(TaskVersionConflict):
            await store.replace(replace(replacement, version=3), expected_version=1)
    finally:
        await contender_store.close()
        await store.close()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_postgres_remote_cancel_stops_executor_in_another_service() -> None:
    dsn = os.getenv("ROUTEPILOT_A2A_TEST_DSN", "").strip()
    if not dsn:
        pytest.skip("ROUTEPILOT_A2A_TEST_DSN is not configured")
    worker_store = PostgresAgentTaskStore.from_database_url(
        dsn,
        poll_interval_seconds=0.01,
    )
    controller_store = PostgresAgentTaskStore.from_database_url(
        dsn,
        poll_interval_seconds=0.01,
    )
    executor = RecoveryExecutor()
    registry = build_default_registry(executors={"research": executor})
    worker = TaskService(
        registry,
        worker_store,
        contract_validator=_allow_contracts,
        execution_lease_seconds=0.15,
        heartbeat_interval_seconds=0.02,
    )
    controller = TaskService(
        registry,
        controller_store,
        contract_validator=_allow_contracts,
        execution_lease_seconds=0.15,
        heartbeat_interval_seconds=0.02,
    )
    initial = sample_record()
    actor = A2AActor(tenant_id=initial.tenant_id, actor_id=initial.actor_id)
    try:
        await worker_store.create_or_get(initial)
        await worker.recover_dispatch(
            actor,
            initial.agent_interface_id,
            run_id=initial.run_id,
            dispatch_id=initial.dispatch_id,
            wait_until_settled=False,
        )
        await asyncio.wait_for(executor.started.wait(), timeout=1)
        canceled = await controller.cancel_run_tasks(actor, initial.run_id)
        assert initial.task.id in {task.id for task in canceled}
        await asyncio.wait_for(executor.canceled.wait(), timeout=1)
        current = await controller_store.get(
            initial.tenant_id,
            initial.agent_interface_id,
            initial.task.id,
        )
        assert current.task.status.state == TaskState.TASK_STATE_CANCELED
        assert not current.task.artifacts
    finally:
        await worker.shutdown()
        await controller.shutdown()
