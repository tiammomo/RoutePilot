"""PostgreSQL Task/inbox/event adapter for the RoutePilot A2A persistence port."""

from __future__ import annotations

import asyncio
import builtins
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from time import monotonic
from typing import Any, cast
from uuid import UUID

from a2a.server.events.event_queue import Event
from a2a.types import (
    Message as A2AMessage,
    Task,
    TaskArtifactUpdateEvent,
    TaskStatusUpdateEvent,
)
from google.protobuf.message import DecodeError, Message as ProtoMessage
from pydantic import ValidationError
from sqlalchemy import and_, func, insert, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, create_async_engine

from .constants import (
    MAX_PERSISTED_EVENT_PROTO_BYTES,
    MAX_PERSISTED_INVOCATION_JSON_BYTES,
    MAX_PERSISTED_TASK_EVENTS,
    MAX_PERSISTED_TASK_PROTO_BYTES,
    MAX_REFERENCE_TASKS,
)
from .models import AgentInvocation, InputResponse
from .sql_tables import (
    agent_dispatch_inbox_table,
    agent_task_events_table,
    agent_tasks_table,
)
from .store import (
    AgentTaskPersistence,
    DispatchConflict,
    TaskExecutionLease,
    TaskExecutionLeaseLost,
    TaskMissing,
    TaskRecord,
    TaskStoreError,
    TaskVersionConflict,
    VersionedEvent,
    clone_record,
)

_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_EVENT_TYPES: dict[str, type[ProtoMessage]] = {
    "message": A2AMessage,
    "task": Task,
    "task_artifact_update": TaskArtifactUpdateEvent,
    "task_status_update": TaskStatusUpdateEvent,
}
_EVENT_KINDS_BY_DESCRIPTOR = {
    message_type.DESCRIPTOR.full_name: kind for kind, message_type in _EVENT_TYPES.items()
}


def normalize_async_database_url(database_url: str) -> str:
    """Normalize a PostgreSQL DSN for SQLAlchemy's psycopg async dialect."""

    normalized = str(database_url or "").strip()
    if normalized.startswith("postgres://"):
        normalized = normalized.replace("postgres://", "postgresql://", 1)
    if normalized.startswith("postgresql://"):
        normalized = normalized.replace("postgresql://", "postgresql+psycopg://", 1)
    if not normalized.startswith("postgresql+psycopg://"):
        raise ValueError("A2A durable storage requires a PostgreSQL psycopg DSN")
    return normalized


def _canonical_json_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise TaskStoreError("A2A persistence JSON is not canonicalizable") from exc


def _bounded_proto_bytes(
    value: ProtoMessage,
    *,
    maximum: int,
    field_name: str,
) -> bytes:
    try:
        payload = value.SerializeToString(deterministic=True)
    except Exception as exc:
        raise TaskStoreError(f"{field_name} protobuf could not be serialized") from exc
    if len(payload) > maximum:
        raise TaskStoreError(f"{field_name} protobuf exceeds the durable-store limit")
    return payload


def _parse_bounded_proto(
    message_type: type[ProtoMessage],
    payload: Any,
    *,
    maximum: int,
    field_name: str,
) -> ProtoMessage:
    raw = bytes(payload) if isinstance(payload, (bytes, bytearray, memoryview)) else b""
    if not raw or len(raw) > maximum:
        raise TaskStoreError(f"stored {field_name} protobuf has an invalid size")
    parsed = message_type()
    try:
        parsed.ParseFromString(raw)
    except DecodeError as exc:
        raise TaskStoreError(f"stored {field_name} protobuf is malformed") from exc
    # Only canonical deterministic bytes are accepted back from persistence.
    # This catches accidental format drift as well as ambiguous encodings.
    if parsed.SerializeToString(deterministic=True) != raw:
        raise TaskStoreError(f"stored {field_name} protobuf is not deterministic")
    return parsed


def _serialize_event(event: Event) -> tuple[str, bytes]:
    descriptor = cast(ProtoMessage, event).DESCRIPTOR.full_name
    kind = _EVENT_KINDS_BY_DESCRIPTOR.get(descriptor)
    if kind is None:
        raise TaskStoreError("unsupported A2A event protobuf type")
    return kind, _bounded_proto_bytes(
        cast(ProtoMessage, event),
        maximum=MAX_PERSISTED_EVENT_PROTO_BYTES,
        field_name="event",
    )


def _deserialize_event(kind: Any, payload: Any) -> Event:
    message_type = _EVENT_TYPES.get(str(kind))
    if message_type is None:
        raise TaskStoreError("stored A2A event kind is unsupported")
    return cast(
        Event,
        _parse_bounded_proto(
            message_type,
            payload,
            maximum=MAX_PERSISTED_EVENT_PROTO_BYTES,
            field_name="event",
        ),
    )


def _invocation_payload(invocation: AgentInvocation) -> dict[str, Any]:
    payload = invocation.model_dump(mode="json")
    if len(_canonical_json_bytes(payload)) > MAX_PERSISTED_INVOCATION_JSON_BYTES:
        raise TaskStoreError("invocation JSON exceeds the durable-store limit")
    return payload


def _validate_record(record: TaskRecord) -> None:
    if not record.tenant_id or len(record.tenant_id) > 128:
        raise TaskStoreError("invalid Task tenant identifier")
    if not record.agent_interface_id or len(record.agent_interface_id) > 128:
        raise TaskStoreError("invalid agent interface identifier")
    if not record.task.id or len(record.task.id) > 96:
        raise TaskStoreError("invalid A2A Task identifier")
    if not record.task.context_id or len(record.task.context_id) > 96:
        raise TaskStoreError("invalid A2A context identifier")
    try:
        dispatch_uuid = str(UUID(record.dispatch_id))
    except ValueError as exc:
        raise TaskStoreError("invalid dispatch identifier") from exc
    if dispatch_uuid != record.dispatch_id.lower():
        raise TaskStoreError("dispatch identifier must use canonical UUID form")
    if not record.actor_id or len(record.actor_id) > 128:
        raise TaskStoreError("invalid Task actor identifier")
    if not record.run_id or len(record.run_id) > 160:
        raise TaskStoreError("invalid Product Run identifier")
    if not _SHA256_PATTERN.fullmatch(record.request_fingerprint):
        raise TaskStoreError("invalid request fingerprint")
    if record.version < 1:
        raise TaskStoreError("Task version must be positive")
    if int(record.task.status.state) < 1 or int(record.task.status.state) > 8:
        raise TaskStoreError("Task state is invalid")
    if record.deadline.tzinfo is None or record.deadline.utcoffset() is None:
        raise TaskStoreError("Task deadline must be timezone-aware")
    if len(record.events) > MAX_PERSISTED_TASK_EVENTS:
        raise TaskStoreError("Task event history exceeds the durable-store limit")
    previous_version = 0
    for item in record.events:
        if item.version < 1 or item.version < previous_version or item.version > record.version:
            raise TaskStoreError("Task event versions are not monotonic")
        previous_version = item.version
    if len(record.reference_task_ids) > MAX_REFERENCE_TASKS or any(
        not item or len(item) > 96 for item in record.reference_task_ids
    ):
        raise TaskStoreError("invalid reference Task identifiers")
    for message_id, fingerprint in record.message_fingerprints.items():
        if not message_id or len(message_id) > 128:
            raise TaskStoreError("invalid message fingerprint identifier")
        if not _SHA256_PATTERN.fullmatch(fingerprint):
            raise TaskStoreError("invalid message fingerprint")
    if record.execution_input is not None:
        payload = record.execution_input.model_dump(mode="json")
        if len(_canonical_json_bytes(payload)) > MAX_PERSISTED_INVOCATION_JSON_BYTES:
            raise TaskStoreError("execution input JSON exceeds the durable-store limit")


class PostgresAgentTaskStore(AgentTaskPersistence):
    """Atomic dispatch dedupe, Task CAS and event replay on PostgreSQL."""

    def __init__(
        self,
        engine: AsyncEngine,
        *,
        poll_interval_seconds: float = 0.1,
    ) -> None:
        self.engine = engine
        self.poll_interval_seconds = max(0.01, min(float(poll_interval_seconds), 2.0))
        self._closed = False

    @classmethod
    def from_database_url(
        cls,
        database_url: str,
        *,
        poll_interval_seconds: float = 0.1,
    ) -> "PostgresAgentTaskStore":
        """Build the pooled adapter without performing runtime DDL."""

        engine = create_async_engine(
            normalize_async_database_url(database_url),
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
        return cls(engine, poll_interval_seconds=poll_interval_seconds)

    def _assert_open(self) -> None:
        if self._closed:
            raise TaskStoreError("A2A durable store is closed")

    @staticmethod
    async def _scope_tenant(connection: AsyncConnection, tenant_id: str) -> None:
        """Set transaction-local RLS context before touching tenant rows."""

        await connection.execute(select(func.set_config("routepilot.tenant_id", tenant_id, True)))

    @staticmethod
    def _record_values(record: TaskRecord) -> dict[str, Any]:
        _validate_record(record)
        task_proto = _bounded_proto_bytes(
            record.task,
            maximum=MAX_PERSISTED_TASK_PROTO_BYTES,
            field_name="Task",
        )
        invocation = _invocation_payload(record.invocation)
        reference_task_ids = list(record.reference_task_ids)
        if len(_canonical_json_bytes(reference_task_ids)) > MAX_PERSISTED_INVOCATION_JSON_BYTES:
            raise TaskStoreError("reference Task identifiers exceed the durable-store limit")
        message_fingerprints = dict(record.message_fingerprints)
        if len(_canonical_json_bytes(message_fingerprints)) > MAX_PERSISTED_INVOCATION_JSON_BYTES:
            raise TaskStoreError("message fingerprints exceed the durable-store limit")
        now = datetime.now(UTC)
        return {
            "tenant_id": record.tenant_id,
            "agent_interface_id": record.agent_interface_id,
            "task_id": record.task.id,
            "actor_id": record.actor_id,
            "run_id": record.run_id,
            "dispatch_id": record.dispatch_id,
            "request_fingerprint": record.request_fingerprint,
            "context_id": record.task.context_id,
            "task_state": int(record.task.status.state),
            "task_proto": task_proto,
            "invocation": invocation,
            "deadline": record.deadline,
            "reference_task_ids": reference_task_ids,
            "version": record.version,
            "event_count": len(record.events),
            "pending_input_request_id": record.pending_input_request_id,
            "execution_input": (
                record.execution_input.model_dump(mode="json")
                if record.execution_input is not None
                else None
            ),
            "message_fingerprints": message_fingerprints,
            "created_at": record.created_at or now,
            "updated_at": record.updated_at or now,
        }

    @staticmethod
    def _event_rows(record: TaskRecord, *, start_index: int = 0) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        occurred_at = record.updated_at or datetime.now(UTC)
        for index, item in enumerate(record.events[start_index:], start=start_index + 1):
            kind, payload = _serialize_event(item.event)
            rows.append(
                {
                    "tenant_id": record.tenant_id,
                    "agent_interface_id": record.agent_interface_id,
                    "task_id": record.task.id,
                    "event_seq": index,
                    "task_version": item.version,
                    "event_kind": kind,
                    "event_proto": payload,
                    "created_at": occurred_at,
                }
            )
        return rows

    async def _load_tx(
        self,
        connection: AsyncConnection,
        tenant_id: str,
        agent_interface_id: str,
        task_id: str,
    ) -> TaskRecord:
        row = (
            (
                await connection.execute(
                    select(agent_tasks_table).where(
                        agent_tasks_table.c.tenant_id == tenant_id,
                        agent_tasks_table.c.agent_interface_id == agent_interface_id,
                        agent_tasks_table.c.task_id == task_id,
                    )
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            raise TaskMissing("task not found")
        event_count = int(row["event_count"])
        if event_count < 0 or event_count > MAX_PERSISTED_TASK_EVENTS:
            raise TaskStoreError("stored Task event count is invalid")
        event_rows = (
            (
                await connection.execute(
                    select(agent_task_events_table)
                    .where(
                        agent_task_events_table.c.tenant_id == tenant_id,
                        agent_task_events_table.c.agent_interface_id == agent_interface_id,
                        agent_task_events_table.c.task_id == task_id,
                    )
                    .order_by(agent_task_events_table.c.event_seq)
                    .limit(MAX_PERSISTED_TASK_EVENTS + 1)
                )
            )
            .mappings()
            .all()
        )
        if len(event_rows) != event_count:
            raise TaskStoreError("stored Task event history is incomplete")

        task = cast(
            Task,
            _parse_bounded_proto(
                Task,
                row["task_proto"],
                maximum=MAX_PERSISTED_TASK_PROTO_BYTES,
                field_name="Task",
            ),
        )
        if task.id != task_id or task.context_id != row["context_id"]:
            raise TaskStoreError("stored Task protobuf identity does not match its row")
        if int(task.status.state) != int(row["task_state"]):
            raise TaskStoreError("stored Task protobuf state does not match its row")
        try:
            invocation_raw = dict(row["invocation"])
            if len(_canonical_json_bytes(invocation_raw)) > MAX_PERSISTED_INVOCATION_JSON_BYTES:
                raise TaskStoreError("stored invocation JSON exceeds the durable-store limit")
            invocation = AgentInvocation.model_validate(invocation_raw)
        except (TypeError, ValueError, ValidationError) as exc:
            raise TaskStoreError("stored invocation JSON is invalid") from exc

        references_raw = row["reference_task_ids"]
        if not isinstance(references_raw, list) or not all(
            isinstance(item, str) for item in references_raw
        ):
            raise TaskStoreError("stored reference Task identifiers are invalid")
        fingerprints_raw = row["message_fingerprints"]
        if not isinstance(fingerprints_raw, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in fingerprints_raw.items()
        ):
            raise TaskStoreError("stored message fingerprints are invalid")
        execution_input_raw = row["execution_input"]
        execution_input: InputResponse | None = None
        if execution_input_raw is not None:
            try:
                raw = dict(execution_input_raw)
                if len(_canonical_json_bytes(raw)) > MAX_PERSISTED_INVOCATION_JSON_BYTES:
                    raise TaskStoreError("stored execution input exceeds the durable-store limit")
                execution_input = InputResponse.model_validate(raw)
            except (TypeError, ValueError, ValidationError) as exc:
                raise TaskStoreError("stored execution input JSON is invalid") from exc

        events: list[VersionedEvent] = []
        prior_seq = 0
        prior_version = 0
        for event_row in event_rows:
            event_seq = int(event_row["event_seq"])
            event_version = int(event_row["task_version"])
            if event_seq != prior_seq + 1:
                raise TaskStoreError("stored Task event sequence is not contiguous")
            if event_version < prior_version or event_version > int(row["version"]):
                raise TaskStoreError("stored Task event version is invalid")
            events.append(
                VersionedEvent(
                    event_version,
                    _deserialize_event(event_row["event_kind"], event_row["event_proto"]),
                )
            )
            prior_seq = event_seq
            prior_version = event_version

        deadline = row["deadline"]
        if not isinstance(deadline, datetime) or deadline.tzinfo is None:
            raise TaskStoreError("stored Task deadline is invalid")
        record = TaskRecord(
            tenant_id=str(row["tenant_id"]),
            actor_id=str(row["actor_id"]),
            agent_interface_id=str(row["agent_interface_id"]),
            run_id=str(row["run_id"]),
            dispatch_id=str(row["dispatch_id"]),
            request_fingerprint=str(row["request_fingerprint"]),
            task=task,
            invocation=invocation,
            deadline=deadline,
            reference_task_ids=tuple(references_raw),
            version=int(row["version"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            pending_input_request_id=row["pending_input_request_id"],
            execution_input=execution_input,
            message_fingerprints=dict(fingerprints_raw),
            events=tuple(events),
        )
        _validate_record(record)
        return record

    async def create_or_get(self, record: TaskRecord) -> tuple[TaskRecord, bool]:
        """Atomically claim one scoped dispatch and create its initial Task."""

        self._assert_open()
        values = self._record_values(record)
        event_rows = self._event_rows(record)
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, record.tenant_id)
            await connection.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:dispatch_scope, 0))"),
                {
                    "dispatch_scope": (
                        f"a2a-dispatch:{record.tenant_id}:"
                        f"{record.agent_interface_id}:{record.dispatch_id}"
                    )
                },
            )
            inbox = (
                (
                    await connection.execute(
                        select(agent_dispatch_inbox_table).where(
                            agent_dispatch_inbox_table.c.tenant_id == record.tenant_id,
                            agent_dispatch_inbox_table.c.agent_interface_id
                            == record.agent_interface_id,
                            agent_dispatch_inbox_table.c.dispatch_id == record.dispatch_id,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if inbox is not None:
                if str(inbox["request_fingerprint"]) != record.request_fingerprint:
                    raise DispatchConflict("dispatch identifier already has another request")
                existing = await self._load_tx(
                    connection,
                    record.tenant_id,
                    record.agent_interface_id,
                    str(inbox["task_id"]),
                )
                return clone_record(existing), False

            task_exists = await connection.scalar(
                select(agent_tasks_table.c.task_id).where(
                    agent_tasks_table.c.tenant_id == record.tenant_id,
                    agent_tasks_table.c.agent_interface_id == record.agent_interface_id,
                    agent_tasks_table.c.task_id == record.task.id,
                )
            )
            if task_exists is not None:
                raise DispatchConflict("task identifier already exists")

            await connection.execute(insert(agent_tasks_table).values(**values))
            await connection.execute(
                insert(agent_dispatch_inbox_table).values(
                    tenant_id=record.tenant_id,
                    agent_interface_id=record.agent_interface_id,
                    dispatch_id=record.dispatch_id,
                    task_id=record.task.id,
                    request_fingerprint=record.request_fingerprint,
                    received_at=record.created_at or datetime.now(UTC),
                )
            )
            if event_rows:
                await connection.execute(insert(agent_task_events_table), event_rows)
            stored = await self._load_tx(
                connection,
                record.tenant_id,
                record.agent_interface_id,
                record.task.id,
            )
        return clone_record(stored), True

    async def get(self, tenant_id: str, agent_interface_id: str, task_id: str) -> TaskRecord:
        self._assert_open()
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, tenant_id)
            record = await self._load_tx(connection, tenant_id, agent_interface_id, task_id)
        return clone_record(record)

    async def get_by_dispatch(
        self,
        tenant_id: str,
        agent_interface_id: str,
        dispatch_id: str,
    ) -> TaskRecord:
        self._assert_open()
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, tenant_id)
            task_id = await connection.scalar(
                select(agent_dispatch_inbox_table.c.task_id).where(
                    agent_dispatch_inbox_table.c.tenant_id == tenant_id,
                    agent_dispatch_inbox_table.c.agent_interface_id == agent_interface_id,
                    agent_dispatch_inbox_table.c.dispatch_id == dispatch_id,
                )
            )
            if task_id is None:
                raise TaskMissing("task not found")
            record = await self._load_tx(
                connection,
                tenant_id,
                agent_interface_id,
                str(task_id),
            )
        return clone_record(record)

    @staticmethod
    def _assert_immutable_fields(current: TaskRecord, replacement: TaskRecord) -> None:
        immutable_current = (
            current.tenant_id,
            current.actor_id,
            current.agent_interface_id,
            current.run_id,
            current.dispatch_id,
            current.request_fingerprint,
            current.task.id,
            current.task.context_id,
            current.invocation,
            current.deadline,
            current.reference_task_ids,
            current.created_at,
        )
        immutable_replacement = (
            replacement.tenant_id,
            replacement.actor_id,
            replacement.agent_interface_id,
            replacement.run_id,
            replacement.dispatch_id,
            replacement.request_fingerprint,
            replacement.task.id,
            replacement.task.context_id,
            replacement.invocation,
            replacement.deadline,
            replacement.reference_task_ids,
            replacement.created_at,
        )
        if immutable_current != immutable_replacement:
            raise TaskStoreError("immutable Task fields changed during replacement")

    @staticmethod
    def _assert_event_prefix(current: TaskRecord, replacement: TaskRecord) -> None:
        if len(replacement.events) < len(current.events):
            raise TaskStoreError("Task replacement truncated retained events")
        for existing, proposed in zip(current.events, replacement.events, strict=False):
            if existing.version != proposed.version:
                raise TaskStoreError("Task replacement rewrote an event version")
            existing_kind, existing_bytes = _serialize_event(existing.event)
            proposed_kind, proposed_bytes = _serialize_event(proposed.event)
            if existing_kind != proposed_kind or existing_bytes != proposed_bytes:
                raise TaskStoreError("Task replacement rewrote retained events")

    async def replace(
        self,
        record: TaskRecord,
        *,
        expected_version: int,
        execution_lease: TaskExecutionLease | None = None,
    ) -> TaskRecord:
        """CAS-replace one Task and append its new replay events transactionally."""

        self._assert_open()
        if record.version != expected_version + 1:
            raise TaskVersionConflict("task state changed")
        values = self._record_values(record)
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, record.tenant_id)
            try:
                current = await self._load_tx(
                    connection,
                    record.tenant_id,
                    record.agent_interface_id,
                    record.task.id,
                )
            except TaskMissing:
                raise
            if current.version != expected_version:
                raise TaskVersionConflict("task state changed")
            self._assert_immutable_fields(current, record)
            self._assert_event_prefix(current, record)
            new_event_rows = self._event_rows(record, start_index=len(current.events))

            update_values = dict(values)
            for field_name in (
                "tenant_id",
                "agent_interface_id",
                "task_id",
                "actor_id",
                "run_id",
                "dispatch_id",
                "request_fingerprint",
                "context_id",
                "invocation",
                "deadline",
                "reference_task_ids",
                "created_at",
                "execution_lease_owner",
                "execution_lease_until",
                "execution_attempt",
            ):
                update_values.pop(field_name, None)
            predicates = [
                agent_tasks_table.c.tenant_id == record.tenant_id,
                agent_tasks_table.c.agent_interface_id == record.agent_interface_id,
                agent_tasks_table.c.task_id == record.task.id,
                agent_tasks_table.c.version == expected_version,
            ]
            if execution_lease is not None:
                predicates.extend(
                    [
                        agent_tasks_table.c.execution_lease_owner == execution_lease.owner,
                        agent_tasks_table.c.execution_attempt == execution_lease.attempt,
                        agent_tasks_table.c.execution_lease_until > func.now(),
                    ]
                )
            if int(record.task.status.state) not in {1, 2}:
                update_values["execution_lease_owner"] = None
                update_values["execution_lease_until"] = None
            result = await connection.execute(
                update(agent_tasks_table).where(*predicates).values(**update_values)
            )
            if result.rowcount != 1:
                if execution_lease is not None:
                    lease_row = (
                        (
                            await connection.execute(
                                select(
                                    agent_tasks_table.c.version,
                                    agent_tasks_table.c.task_state,
                                    agent_tasks_table.c.execution_lease_owner,
                                    agent_tasks_table.c.execution_lease_until,
                                    agent_tasks_table.c.execution_attempt,
                                    (agent_tasks_table.c.execution_lease_until > func.now()).label(
                                        "execution_lease_active"
                                    ),
                                ).where(
                                    agent_tasks_table.c.tenant_id == record.tenant_id,
                                    agent_tasks_table.c.agent_interface_id
                                    == record.agent_interface_id,
                                    agent_tasks_table.c.task_id == record.task.id,
                                )
                            )
                        )
                        .mappings()
                        .one_or_none()
                    )
                    if lease_row is None:
                        raise TaskMissing("task not found")
                    if (
                        lease_row["execution_lease_owner"] != execution_lease.owner
                        or int(lease_row["execution_attempt"]) != execution_lease.attempt
                        or not bool(lease_row["execution_lease_active"])
                        or int(lease_row["task_state"]) not in {1, 2}
                    ):
                        raise TaskExecutionLeaseLost("task execution lease was lost")
                raise TaskVersionConflict("task state changed")
            if new_event_rows:
                await connection.execute(insert(agent_task_events_table), new_event_rows)
            await connection.execute(
                text("SELECT pg_notify('routepilot_a2a_task_changed', :task_scope)"),
                {
                    # PostgreSQL channels have no per-message ACL. Publish only
                    # an opaque wake-up key so LISTEN cannot leak tenant/task IDs.
                    "task_scope": hashlib.sha256(
                        (
                            f"{record.tenant_id}:{record.agent_interface_id}:"
                            f"{record.task.id}:{record.version}"
                        ).encode("utf-8")
                    ).hexdigest()
                },
            )
        return clone_record(record)

    async def claim_execution(
        self,
        tenant_id: str,
        agent_interface_id: str,
        task_id: str,
        *,
        owner: str,
        lease_seconds: float,
    ) -> TaskExecutionLease | None:
        """Atomically claim an unowned or expired submitted/working Task."""

        self._assert_open()
        if not owner or len(owner) > 128:
            raise TaskStoreError("invalid Task execution owner")
        duration = max(0.05, min(float(lease_seconds), 300.0))
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, tenant_id)
            row = (
                (
                    await connection.execute(
                        update(agent_tasks_table)
                        .where(
                            agent_tasks_table.c.tenant_id == tenant_id,
                            agent_tasks_table.c.agent_interface_id == agent_interface_id,
                            agent_tasks_table.c.task_id == task_id,
                            agent_tasks_table.c.task_state.in_((1, 2)),
                            or_(
                                agent_tasks_table.c.execution_lease_owner.is_(None),
                                agent_tasks_table.c.execution_lease_until <= func.now(),
                            ),
                        )
                        .values(
                            execution_lease_owner=owner,
                            execution_lease_until=func.now() + timedelta(seconds=duration),
                            execution_attempt=agent_tasks_table.c.execution_attempt + 1,
                        )
                        .returning(
                            agent_tasks_table.c.execution_lease_until,
                            agent_tasks_table.c.execution_attempt,
                        )
                    )
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                exists = await connection.scalar(
                    select(agent_tasks_table.c.task_id).where(
                        agent_tasks_table.c.tenant_id == tenant_id,
                        agent_tasks_table.c.agent_interface_id == agent_interface_id,
                        agent_tasks_table.c.task_id == task_id,
                    )
                )
                if exists is None:
                    raise TaskMissing("task not found")
                return None
        return TaskExecutionLease(
            tenant_id=tenant_id,
            agent_interface_id=agent_interface_id,
            task_id=task_id,
            owner=owner,
            attempt=int(row["execution_attempt"]),
            lease_until=row["execution_lease_until"],
        )

    async def renew_execution(
        self,
        lease: TaskExecutionLease,
        *,
        lease_seconds: float,
    ) -> TaskExecutionLease | None:
        """Heartbeat only the exact current fencing token; never revive expiry."""

        self._assert_open()
        duration = max(0.05, min(float(lease_seconds), 300.0))
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, lease.tenant_id)
            lease_until = await connection.scalar(
                update(agent_tasks_table)
                .where(
                    agent_tasks_table.c.tenant_id == lease.tenant_id,
                    agent_tasks_table.c.agent_interface_id == lease.agent_interface_id,
                    agent_tasks_table.c.task_id == lease.task_id,
                    agent_tasks_table.c.task_state.in_((1, 2)),
                    agent_tasks_table.c.execution_lease_owner == lease.owner,
                    agent_tasks_table.c.execution_attempt == lease.attempt,
                    agent_tasks_table.c.execution_lease_until > func.now(),
                )
                .values(execution_lease_until=func.now() + timedelta(seconds=duration))
                .returning(agent_tasks_table.c.execution_lease_until)
            )
        if lease_until is None:
            return None
        return TaskExecutionLease(
            tenant_id=lease.tenant_id,
            agent_interface_id=lease.agent_interface_id,
            task_id=lease.task_id,
            owner=lease.owner,
            attempt=lease.attempt,
            lease_until=lease_until,
        )

    async def release_execution(self, lease: TaskExecutionLease) -> None:
        """Release only the matching attempt so a stale worker cannot clear a successor."""

        self._assert_open()
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, lease.tenant_id)
            await connection.execute(
                update(agent_tasks_table)
                .where(
                    agent_tasks_table.c.tenant_id == lease.tenant_id,
                    agent_tasks_table.c.agent_interface_id == lease.agent_interface_id,
                    agent_tasks_table.c.task_id == lease.task_id,
                    agent_tasks_table.c.execution_lease_owner == lease.owner,
                    agent_tasks_table.c.execution_attempt == lease.attempt,
                )
                .values(execution_lease_owner=None, execution_lease_until=None)
            )

    async def list(
        self,
        tenant_id: str,
        agent_interface_id: str,
        *,
        context_id: str | None = None,
        state: int | None = None,
    ) -> list[TaskRecord]:
        self._assert_open()
        predicates = [
            agent_tasks_table.c.tenant_id == tenant_id,
            agent_tasks_table.c.agent_interface_id == agent_interface_id,
        ]
        if context_id is not None:
            predicates.append(agent_tasks_table.c.context_id == context_id)
        if state is not None:
            predicates.append(agent_tasks_table.c.task_state == int(state))
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, tenant_id)
            task_ids = (
                (
                    await connection.execute(
                        select(agent_tasks_table.c.task_id)
                        .where(and_(*predicates))
                        .order_by(agent_tasks_table.c.created_at, agent_tasks_table.c.task_id)
                    )
                )
                .scalars()
                .all()
            )
            records = [
                await self._load_tx(connection, tenant_id, agent_interface_id, str(task_id))
                for task_id in task_ids
            ]
        return [clone_record(record) for record in records]

    async def list_for_run(self, tenant_id: str, run_id: str) -> builtins.list[TaskRecord]:
        self._assert_open()
        async with self.engine.begin() as connection:
            await self._scope_tenant(connection, tenant_id)
            scoped = (
                await connection.execute(
                    select(
                        agent_tasks_table.c.agent_interface_id,
                        agent_tasks_table.c.task_id,
                    )
                    .where(
                        agent_tasks_table.c.tenant_id == tenant_id,
                        agent_tasks_table.c.run_id == run_id,
                    )
                    .order_by(agent_tasks_table.c.created_at, agent_tasks_table.c.task_id)
                )
            ).all()
            records = [
                await self._load_tx(connection, tenant_id, str(interface_id), str(task_id))
                for interface_id, task_id in scoped
            ]
        return [clone_record(record) for record in records]

    async def wait_for_change(
        self,
        tenant_id: str,
        agent_interface_id: str,
        task_id: str,
        *,
        after_version: int,
        timeout_seconds: float,
    ) -> TaskRecord | None:
        """Wait by bounded polling; writers also emit NOTIFY for listener-based deployments."""

        self._assert_open()
        expires = monotonic() + max(0.0, timeout_seconds)
        while True:
            current = await self.get(tenant_id, agent_interface_id, task_id)
            if current.version > after_version:
                return current
            remaining = expires - monotonic()
            if remaining <= 0:
                return None
            await asyncio.sleep(min(self.poll_interval_seconds, remaining))

    async def close(self) -> None:
        """Dispose the SQLAlchemy pool exactly once."""

        if self._closed:
            return
        self._closed = True
        await self.engine.dispose()


__all__ = [
    "PostgresAgentTaskStore",
    "normalize_async_database_url",
]
