"""Deterministic persistence and runtime-selection tests for durable A2A Tasks."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from a2a.types import Task, TaskState, TaskStatus, TaskStatusUpdateEvent
from google.protobuf.timestamp_pb2 import Timestamp

from agent.travel_agent.a2a.constants import MAX_PERSISTED_TASK_PROTO_BYTES
from agent.travel_agent.a2a.models import AgentInvocation, ArtifactInput
from agent.travel_agent.a2a.postgres_store import (
    PostgresAgentTaskStore,
    _bounded_proto_bytes,
    _deserialize_event,
    _parse_bounded_proto,
    _serialize_event,
    normalize_async_database_url,
)
from agent.travel_agent.a2a.store import (
    InMemoryAgentTaskStore,
    TaskRecord,
    TaskStoreError,
    VersionedEvent,
    clone_proto,
)
from backend.moyuan_web.v1.a2a_routes import build_default_a2a_runtime


def _timestamp(now: datetime) -> Timestamp:
    value = Timestamp()
    value.FromDatetime(now)
    return value


def sample_record() -> TaskRecord:
    now = datetime.now(UTC)
    dispatch_id = str(uuid4())
    fingerprint = hashlib.sha256(b"request").hexdigest()
    task = Task(
        id=str(uuid4()),
        context_id=str(uuid4()),
        status=TaskStatus(
            state=TaskState.TASK_STATE_SUBMITTED,
            timestamp=_timestamp(now),
        ),
    )
    return TaskRecord(
        tenant_id="tenant-a",
        actor_id="actor-a",
        agent_interface_id="research",
        run_id="run-integration",
        dispatch_id=dispatch_id,
        request_fingerprint=fingerprint,
        task=task,
        invocation=AgentInvocation(
            goal="Research one destination",
            artifacts=[
                ArtifactInput(
                    contract="TripBrief@1",
                    payload={"artifact_type": "TripBrief"},
                )
            ],
        ),
        deadline=now + timedelta(minutes=5),
        version=1,
        created_at=now,
        updated_at=now,
        message_fingerprints={dispatch_id: fingerprint},
    )


def working_record(initial: TaskRecord) -> TaskRecord:
    now = datetime.now(UTC)
    task = clone_proto(initial.task)
    task.status.CopyFrom(
        TaskStatus(
            state=TaskState.TASK_STATE_WORKING,
            timestamp=_timestamp(now),
        )
    )
    event = TaskStatusUpdateEvent(
        task_id=task.id,
        context_id=task.context_id,
        status=clone_proto(task.status),
    )
    return replace(
        initial,
        task=task,
        version=2,
        updated_at=now,
        events=(VersionedEvent(2, event),),
    )


def test_protobuf_and_json_snapshot_are_deterministic_and_bounded():
    record = working_record(sample_record())
    values = PostgresAgentTaskStore._record_values(record)
    assert values["task_proto"] == record.task.SerializeToString(deterministic=True)
    assert values["task_state"] == TaskState.TASK_STATE_WORKING
    assert values["invocation"] == record.invocation.model_dump(mode="json")

    parsed = _parse_bounded_proto(
        Task,
        values["task_proto"],
        maximum=MAX_PERSISTED_TASK_PROTO_BYTES,
        field_name="Task",
    )
    assert parsed == record.task
    event_kind, event_bytes = _serialize_event(record.events[0].event)
    assert event_kind == "task_status_update"
    assert _deserialize_event(event_kind, event_bytes) == record.events[0].event


def test_corrupt_or_oversized_protobuf_fails_closed():
    with pytest.raises(TaskStoreError, match="invalid size"):
        _parse_bounded_proto(Task, b"", maximum=100, field_name="Task")
    with pytest.raises(TaskStoreError, match="malformed"):
        _parse_bounded_proto(Task, b"\xff", maximum=100, field_name="Task")

    oversized = Task(id="x" * 2_000)
    with pytest.raises(TaskStoreError, match="exceeds"):
        _bounded_proto_bytes(oversized, maximum=10, field_name="Task")


def test_replacement_cannot_rewrite_immutable_fields_or_retained_events():
    current = working_record(sample_record())
    PostgresAgentTaskStore._assert_immutable_fields(current, current)
    PostgresAgentTaskStore._assert_event_prefix(current, current)

    with pytest.raises(TaskStoreError, match="immutable"):
        PostgresAgentTaskStore._assert_immutable_fields(
            current,
            replace(current, run_id="another-run"),
        )
    rewritten = replace(
        current,
        events=(
            VersionedEvent(
                2,
                TaskStatusUpdateEvent(
                    task_id=current.task.id,
                    context_id=current.task.context_id,
                    status=TaskStatus(state=TaskState.TASK_STATE_FAILED),
                ),
            ),
        ),
    )
    with pytest.raises(TaskStoreError, match="rewrote retained events"):
        PostgresAgentTaskStore._assert_event_prefix(current, rewritten)


def test_database_url_normalization_and_production_fail_closed(monkeypatch):
    assert normalize_async_database_url("postgres://db/test") == (
        "postgresql+psycopg://db/test"
    )
    assert normalize_async_database_url("postgresql://db/test") == (
        "postgresql+psycopg://db/test"
    )
    with pytest.raises(ValueError, match="PostgreSQL"):
        normalize_async_database_url("sqlite:///tmp/test.db")

    monkeypatch.delenv("ROUTEPILOT_A2A_DATABASE_URL", raising=False)
    monkeypatch.delenv("ROUTEPILOT_V1_DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="A2A_DATABASE_URL"):
        build_default_a2a_runtime(environment="production", database_url="")


@pytest.mark.asyncio
async def test_database_url_uses_postgres_adapter_and_runtime_closes_it(monkeypatch):
    selected_store = InMemoryAgentTaskStore()
    close = AsyncMock(wraps=selected_store.close)
    monkeypatch.setattr(selected_store, "close", close)
    monkeypatch.setattr(
        PostgresAgentTaskStore,
        "from_database_url",
        lambda database_url: selected_store,
    )
    monkeypatch.setenv("ROUTEPILOT_A2A_DATABASE_URL", "postgresql://db/a2a")
    monkeypatch.delenv("ROUTEPILOT_V1_DATABASE_URL", raising=False)

    runtime = build_default_a2a_runtime(environment="production")
    assert runtime.store is selected_store
    await runtime.close()
    close.assert_awaited_once()


@pytest.mark.asyncio
async def test_postgres_store_close_disposes_pool_once():
    engine = AsyncMock()
    store = PostgresAgentTaskStore(engine)
    await store.close()
    await store.close()
    engine.dispose.assert_awaited_once()
