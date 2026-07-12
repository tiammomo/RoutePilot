"""Crash recovery, fencing, deterministic dispatch, and remote cancellation tests."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

import pytest
from a2a.types import TaskState, TaskStatus

from agent.travel_agent.a2a.models import (
    A2AActor,
    ArtifactOutput,
    CompletedExecution,
    InputResponse,
)
from agent.travel_agent.a2a.registry import build_default_registry
from agent.travel_agent.a2a.service import TaskService
from agent.travel_agent.a2a.store import (
    InMemoryAgentTaskStore,
    TaskExecutionLeaseLost,
    clone_proto,
)
from agent.travel_agent.runtime_v2.orchestrator import LocalA2AAgentMesh
from tests.a2a.test_a2a_postgres_store_unit import sample_record, working_record


def _allow_contracts(contract: str, payload: dict[str, Any]) -> dict[str, Any]:
    assert contract.endswith("@1")
    return payload


class RecoveryExecutor:
    """Observable cancellable executor shared by simulated service processes."""

    def __init__(self) -> None:
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.canceled = asyncio.Event()
        self.inputs: list[InputResponse | None] = []

    async def execute(self, context, invocation, input_response):
        del context, invocation
        self.calls += 1
        self.inputs.append(input_response)
        self.started.set()
        try:
            await self.release.wait()
        except asyncio.CancelledError:
            self.canceled.set()
            raise
        return CompletedExecution(
            artifacts=[
                ArtifactOutput(
                    contract="EvidenceBundle@1",
                    payload={"artifact_type": "EvidenceBundle", "safe": True},
                    name="Recovered evidence",
                )
            ]
        )


def _service(
    store: InMemoryAgentTaskStore,
    executor: RecoveryExecutor,
) -> TaskService:
    registry = build_default_registry(executors={"research": executor})
    return TaskService(
        registry,
        store,
        contract_validator=_allow_contracts,
        execution_lease_seconds=0.15,
        heartbeat_interval_seconds=0.02,
    )


@pytest.mark.asyncio
async def test_in_memory_execution_lease_is_exclusive_renewable_and_fenced() -> None:
    store = InMemoryAgentTaskStore()
    initial, created = await store.create_or_get(sample_record())
    assert created is True

    first = await store.claim_execution(
        initial.tenant_id,
        initial.agent_interface_id,
        initial.task.id,
        owner="worker-a",
        lease_seconds=0.05,
    )
    assert first is not None
    assert (
        await store.claim_execution(
            initial.tenant_id,
            initial.agent_interface_id,
            initial.task.id,
            owner="worker-b",
            lease_seconds=0.05,
        )
        is None
    )

    working = await store.replace(
        working_record(initial),
        expected_version=1,
        execution_lease=first,
    )
    await asyncio.sleep(0.06)
    successor = await store.claim_execution(
        initial.tenant_id,
        initial.agent_interface_id,
        initial.task.id,
        owner="worker-b",
        lease_seconds=0.15,
    )
    assert successor is not None
    assert successor.attempt == first.attempt + 1

    with pytest.raises(TaskExecutionLeaseLost):
        await store.replace(
            replace(working, version=working.version + 1),
            expected_version=working.version,
            execution_lease=first,
        )
    await store.release_execution(first)
    assert await store.renew_execution(successor, lease_seconds=0.15) is not None

    canceled_task = clone_proto(working.task)
    canceled_task.status.CopyFrom(TaskStatus(state=TaskState.TASK_STATE_CANCELED))
    await store.replace(
        replace(working, task=canceled_task, version=working.version + 1),
        expected_version=working.version,
    )
    assert await store.renew_execution(successor, lease_seconds=0.15) is None


@pytest.mark.asyncio
async def test_expired_working_task_recovers_persisted_typed_input_after_restart() -> None:
    store = InMemoryAgentTaskStore()
    executor = RecoveryExecutor()
    initial = working_record(sample_record())
    response = InputResponse(
        request_id="clarify_dates",
        values={"start_date": "2026-10-01"},
    )
    initial = replace(initial, execution_input=response)
    await store.create_or_get(initial)
    dead_lease = await store.claim_execution(
        initial.tenant_id,
        initial.agent_interface_id,
        initial.task.id,
        owner="dead-process",
        lease_seconds=0.05,
    )
    assert dead_lease is not None

    service = _service(store, executor)
    actor = A2AActor(tenant_id=initial.tenant_id, actor_id=initial.actor_id)
    assert (
        await service.recover_dispatch(
            actor,
            initial.agent_interface_id,
            run_id=initial.run_id,
            dispatch_id=initial.dispatch_id,
            wait_until_settled=False,
        )
        is not None
    )
    await asyncio.sleep(0.01)
    assert executor.calls == 0

    await asyncio.sleep(0.05)
    recovery = asyncio.create_task(
        service.recover_dispatch(
            actor,
            initial.agent_interface_id,
            run_id=initial.run_id,
            dispatch_id=initial.dispatch_id,
        )
    )
    await asyncio.wait_for(executor.started.wait(), timeout=1)
    executor.release.set()
    task = await asyncio.wait_for(recovery, timeout=1)
    assert task is not None
    assert task.status.state == TaskState.TASK_STATE_COMPLETED
    assert executor.calls == 1
    assert executor.inputs == [response]
    await service.shutdown()


@pytest.mark.asyncio
async def test_two_processes_recover_one_dispatch_but_only_one_executes() -> None:
    store = InMemoryAgentTaskStore()
    executor = RecoveryExecutor()
    initial, _ = await store.create_or_get(sample_record())
    first_service = _service(store, executor)
    second_service = _service(store, executor)
    actor = A2AActor(tenant_id=initial.tenant_id, actor_id=initial.actor_id)

    recoveries = [
        asyncio.create_task(
            service.recover_dispatch(
                actor,
                initial.agent_interface_id,
                run_id=initial.run_id,
                dispatch_id=initial.dispatch_id,
            )
        )
        for service in (first_service, second_service)
    ]
    await asyncio.wait_for(executor.started.wait(), timeout=1)
    await asyncio.sleep(0.05)
    assert executor.calls == 1
    executor.release.set()
    tasks = await asyncio.wait_for(asyncio.gather(*recoveries), timeout=2)
    assert all(task is not None for task in tasks)
    assert all(
        task.status.state == TaskState.TASK_STATE_COMPLETED for task in tasks if task is not None
    )
    assert executor.calls == 1
    await first_service.shutdown()
    await second_service.shutdown()


@pytest.mark.asyncio
async def test_remote_run_cancel_persists_task_cancel_and_stops_executor() -> None:
    store = InMemoryAgentTaskStore()
    executor = RecoveryExecutor()
    initial, _ = await store.create_or_get(sample_record())
    worker_service = _service(store, executor)
    controller_service = _service(store, executor)
    actor = A2AActor(tenant_id=initial.tenant_id, actor_id=initial.actor_id)

    await worker_service.recover_dispatch(
        actor,
        initial.agent_interface_id,
        run_id=initial.run_id,
        dispatch_id=initial.dispatch_id,
        wait_until_settled=False,
    )
    await asyncio.wait_for(executor.started.wait(), timeout=1)
    canceled = await controller_service.cancel_run_tasks(actor, initial.run_id)
    assert [task.id for task in canceled] == [initial.task.id]
    await asyncio.wait_for(executor.canceled.wait(), timeout=1)

    current = await store.get(
        initial.tenant_id,
        initial.agent_interface_id,
        initial.task.id,
    )
    assert current.task.status.state == TaskState.TASK_STATE_CANCELED
    assert not current.task.artifacts
    await worker_service.shutdown()
    await controller_service.shutdown()


def test_local_mesh_dispatch_identifier_is_stable_and_stage_scoped() -> None:
    first = LocalA2AAgentMesh.deterministic_dispatch_id("tenant-a", "run-a", "research", "research")
    assert first == LocalA2AAgentMesh.deterministic_dispatch_id(
        "tenant-a", "run-a", "research", "research"
    )
    assert first != LocalA2AAgentMesh.deterministic_dispatch_id(
        "tenant-a", "run-a", "research", "alternate-research"
    )
    assert first != LocalA2AAgentMesh.deterministic_dispatch_id(
        "tenant-b", "run-a", "research", "research"
    )
