"""Reliable A2A Task lifecycle service built on official A2A 1.0 types."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from functools import partial
from typing import Any
from uuid import UUID, uuid4

from a2a.server.events.event_queue import Event
from a2a.types import (
    Artifact,
    Message,
    Part,
    Role,
    SendMessageRequest,
    Task,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
)
from a2a.utils.errors import (
    ContentTypeNotSupportedError,
    ExtensionSupportRequiredError,
    InvalidParamsError,
    TaskNotCancelableError,
    TaskNotFoundError,
    UnsupportedOperationError,
)
from google.protobuf.json_format import MessageToDict, ParseDict
from google.protobuf.struct_pb2 import Struct, Value
from google.protobuf.timestamp_pb2 import Timestamp
from pydantic import ValidationError

from .constants import (
    DEFAULT_TASK_TIMEOUT_SECONDS,
    INPUT_REQUEST_SCHEMA_URI,
    INPUT_RESPONSE_SCHEMA_URI,
    MAX_REFERENCE_TASKS,
    MAX_STRUCTURED_INPUT_BYTES,
    MAX_TASK_TIMEOUT_SECONDS,
    PUBLIC_ERROR_SCHEMA_URI,
    TRAVEL_ARTIFACT_EXTENSION_URI,
    artifact_schema_uri,
)
from .models import (
    A2AActor,
    AgentExecutionContext,
    AgentInvocation,
    ArtifactOutput,
    AuthRequiredExecution,
    CompletedExecution,
    ContractValidator,
    DispatchMetadata,
    FailedExecution,
    InputRequiredExecution,
    InputResponse,
    RunTaskRef,
    StrictModel,
    default_contract_validator,
    ensure_aware_future,
)
from .registry import AgentProfile, AgentRegistry
from .store import (
    AgentTaskPersistence,
    DispatchConflict,
    TaskExecutionLease,
    TaskExecutionLeaseLost,
    TaskMissing,
    TaskRecord,
    TaskVersionConflict,
    VersionedEvent,
    clone_proto,
)

logger = logging.getLogger(__name__)

SETTLED_STATES = {
    TaskState.TASK_STATE_COMPLETED,
    TaskState.TASK_STATE_FAILED,
    TaskState.TASK_STATE_CANCELED,
    TaskState.TASK_STATE_REJECTED,
    TaskState.TASK_STATE_INPUT_REQUIRED,
    TaskState.TASK_STATE_AUTH_REQUIRED,
}
TERMINAL_STATES = {
    TaskState.TASK_STATE_COMPLETED,
    TaskState.TASK_STATE_FAILED,
    TaskState.TASK_STATE_CANCELED,
    TaskState.TASK_STATE_REJECTED,
}
CANCELABLE_STATES = {
    TaskState.TASK_STATE_SUBMITTED,
    TaskState.TASK_STATE_WORKING,
    TaskState.TASK_STATE_INPUT_REQUIRED,
    TaskState.TASK_STATE_AUTH_REQUIRED,
}


class StructuredPartMetadata(StrictModel):
    """Only metadata accepted on a RoutePilot structured Part."""

    schema_uri: str
    schema_version: int


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _timestamp(value: datetime | None = None) -> Timestamp:
    timestamp = Timestamp()
    timestamp.FromDatetime(value or _utc_now())
    return timestamp


def _struct(payload: dict[str, Any]) -> Struct:
    return ParseDict(payload, Struct())


def _value(payload: Any) -> Value:
    return ParseDict(payload, Value())


def _as_dict(value: Any) -> dict[str, Any]:
    converted = MessageToDict(value, preserving_proto_field_name=False)
    if not isinstance(converted, dict):
        raise InvalidParamsError(message="Structured Part data must be a JSON object")
    return converted


def _canonical_bytes(payload: Any) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _fingerprint(payload: Any) -> str:
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def _canonical_uuid(value: str, *, field_name: str) -> str:
    try:
        parsed = UUID(value)
    except ValueError as exc:
        raise InvalidParamsError(message=f"{field_name} must be a UUID") from exc
    canonical = str(parsed)
    if value.lower() != canonical:
        raise InvalidParamsError(message=f"{field_name} must use canonical UUID form")
    return canonical


def _safe_task_metadata(record: TaskRecord, *, version: int) -> Struct:
    return _struct(
        {
            TRAVEL_ARTIFACT_EXTENSION_URI: {
                "agent_interface_id": record.agent_interface_id,
                "dispatch_id": record.dispatch_id,
                "run_id": record.run_id,
                "task_version": version,
                "deadline": record.deadline.isoformat(),
            }
        }
    )


def _event_metadata(version: int) -> Struct:
    return _struct({TRAVEL_ARTIFACT_EXTENSION_URI: {"task_version": version}})


def _structured_message(
    *,
    task_id: str,
    context_id: str,
    schema_uri: str,
    payload: dict[str, Any],
) -> Message:
    return Message(
        message_id=str(uuid4()),
        task_id=task_id,
        context_id=context_id,
        role=Role.ROLE_AGENT,
        parts=[
            Part(
                data=_value(payload),
                metadata=_struct({"schema_uri": schema_uri, "schema_version": 1}),
            )
        ],
        extensions=[TRAVEL_ARTIFACT_EXTENSION_URI],
    )


class TaskService:
    """Tenant-scoped A2A Task control plane, separate from Product Run state."""

    def __init__(
        self,
        registry: AgentRegistry,
        store: AgentTaskPersistence,
        *,
        contract_validator: ContractValidator = default_contract_validator,
        execution_lease_seconds: float = 15.0,
        heartbeat_interval_seconds: float | None = None,
    ) -> None:
        self.registry = registry
        self.store = store
        self._contract_validator = contract_validator
        self._execution_lease_seconds = max(
            0.15,
            min(float(execution_lease_seconds), 300.0),
        )
        default_heartbeat = min(2.0, self._execution_lease_seconds / 3)
        self._heartbeat_interval_seconds = max(
            0.02,
            min(
                float(heartbeat_interval_seconds or default_heartbeat),
                self._execution_lease_seconds / 3,
            ),
        )
        self._service_id = uuid4().hex
        self._jobs: dict[tuple[str, str, str], asyncio.Task[None]] = {}
        self._cancel_tokens: dict[tuple[str, str, str], asyncio.Event] = {}

    @staticmethod
    def _assert_tenant(actor: A2AActor, request_tenant: str) -> None:
        if not request_tenant or request_tenant != actor.tenant_id:
            raise TaskNotFoundError(message="Task not found")

    @staticmethod
    def _assert_extension(requested_extensions: set[str], message: Message) -> None:
        if TRAVEL_ARTIFACT_EXTENSION_URI not in requested_extensions:
            raise ExtensionSupportRequiredError(
                message="RoutePilot travel Artifact extension is required"
            )
        if TRAVEL_ARTIFACT_EXTENSION_URI not in set(message.extensions):
            raise ExtensionSupportRequiredError(
                message="Message must declare the RoutePilot travel Artifact extension"
            )

    @staticmethod
    def _assert_configuration(params: SendMessageRequest) -> None:
        configuration = params.configuration
        if configuration.accepted_output_modes:
            accepted = set(configuration.accepted_output_modes)
            if "application/json" not in accepted:
                raise ContentTypeNotSupportedError()
        if configuration.HasField("task_push_notification_config"):
            raise UnsupportedOperationError(message="Push notifications are not enabled")
        if configuration.history_length < 0 or configuration.history_length > 100:
            raise InvalidParamsError(message="historyLength must be between 0 and 100")
        if params.metadata.fields:
            raise InvalidParamsError(
                message="Request metadata is not accepted; use Message metadata"
            )

    @staticmethod
    def _dispatch_metadata(message: Message) -> DispatchMetadata:
        metadata = MessageToDict(message.metadata, preserving_proto_field_name=False)
        if set(metadata) != {TRAVEL_ARTIFACT_EXTENSION_URI}:
            raise InvalidParamsError(message="Message metadata contains unsupported fields")
        payload = metadata.get(TRAVEL_ARTIFACT_EXTENSION_URI)
        if not isinstance(payload, dict):
            raise InvalidParamsError(message="RoutePilot extension metadata must be an object")
        try:
            parsed = DispatchMetadata.model_validate(payload)
        except ValidationError as exc:
            raise InvalidParamsError(message="Invalid RoutePilot dispatch metadata") from exc
        _canonical_uuid(parsed.dispatch_id, field_name="dispatch_id")
        return parsed

    @staticmethod
    def _deadline(metadata: DispatchMetadata) -> datetime:
        now = _utc_now()
        deadline = metadata.deadline or now + timedelta(seconds=DEFAULT_TASK_TIMEOUT_SECONDS)
        try:
            deadline = ensure_aware_future(deadline, now=now)
        except ValueError as exc:
            raise InvalidParamsError(message=str(exc)) from exc
        if (deadline - now).total_seconds() > MAX_TASK_TIMEOUT_SECONDS:
            raise InvalidParamsError(message="deadline exceeds the maximum task timeout")
        return deadline

    def _parse_structured_part(
        self,
        message: Message,
        *,
        schema_uri: str,
    ) -> dict[str, Any]:
        if len(message.parts) != 1:
            raise InvalidParamsError(message="Exactly one structured data Part is required")
        part = message.parts[0]
        if part.WhichOneof("content") != "data":
            raise ContentTypeNotSupportedError(
                message="Only bounded application/json data Parts are accepted"
            )
        metadata_dict = MessageToDict(part.metadata, preserving_proto_field_name=False)
        try:
            metadata = StructuredPartMetadata.model_validate(metadata_dict)
        except ValidationError as exc:
            raise InvalidParamsError(message="Invalid structured Part metadata") from exc
        if metadata.schema_uri != schema_uri or metadata.schema_version != 1:
            raise InvalidParamsError(message="Structured Part schema is not supported")
        payload = _as_dict(part.data)
        if len(_canonical_bytes(payload)) > MAX_STRUCTURED_INPUT_BYTES:
            raise InvalidParamsError(message="Structured Part exceeds the size limit")
        return payload

    def _parse_invocation(self, profile: AgentProfile, message: Message) -> AgentInvocation:
        payload = self._parse_structured_part(message, schema_uri=profile.invocation_schema_uri)
        try:
            invocation = AgentInvocation.model_validate(payload)
        except ValidationError as exc:
            raise InvalidParamsError(message="Invalid agent invocation schema") from exc
        contracts = [artifact.contract for artifact in invocation.artifacts]
        if len(contracts) != len(set(contracts)):
            raise InvalidParamsError(message="Input Artifact contracts must be unique")
        missing = set(profile.required_input_contracts) - set(contracts)
        if missing:
            raise InvalidParamsError(message="Required input Artifacts are missing")
        for artifact in invocation.artifacts:
            try:
                self._contract_validator(artifact.contract, artifact.payload)
            except Exception as exc:
                logger.info("Rejected invalid A2A input contract %s", artifact.contract)
                raise InvalidParamsError(
                    message=f"Artifact does not satisfy {artifact.contract}"
                ) from exc
        return invocation

    def _parse_input_response(self, message: Message) -> InputResponse:
        payload = self._parse_structured_part(message, schema_uri=INPUT_RESPONSE_SCHEMA_URI)
        try:
            return InputResponse.model_validate(payload)
        except ValidationError as exc:
            raise InvalidParamsError(message="Invalid typed input response") from exc

    async def _validate_references(
        self,
        actor: A2AActor,
        profile: AgentProfile,
        run_id: str,
        reference_ids: list[str],
    ) -> None:
        if len(reference_ids) > MAX_REFERENCE_TASKS or len(reference_ids) != len(
            set(reference_ids)
        ):
            raise InvalidParamsError(message="Invalid referenceTaskIds")
        for reference_id in reference_ids:
            try:
                referenced = await self.store.get(
                    actor.tenant_id,
                    profile.interface_id,
                    reference_id,
                )
            except TaskMissing as exc:
                raise InvalidParamsError(message="Referenced Task does not exist") from exc
            if referenced.run_id != run_id:
                raise InvalidParamsError(message="Referenced Task belongs to another Product Run")

    async def send_message(
        self,
        actor: A2AActor,
        agent_interface_id: str,
        params: SendMessageRequest,
        *,
        requested_extensions: set[str],
    ) -> Task:
        """Create/dedupe a Task or resume its typed input interruption."""

        self._assert_tenant(actor, params.tenant)
        profile = self.registry.get(agent_interface_id)
        self._assert_configuration(params)
        message = params.message
        if message.role != Role.ROLE_USER:
            raise InvalidParamsError(message="Only ROLE_USER requests are accepted")
        _canonical_uuid(message.message_id, field_name="messageId")
        self._assert_extension(requested_extensions, message)
        metadata = self._dispatch_metadata(message)

        if message.task_id:
            record = await self._resume_input(
                actor,
                profile,
                message,
                metadata,
            )
            if params.configuration.return_immediately:
                return clone_proto(record.task)
            settled = await self._wait_until_settled(record, profile=profile)
            return clone_proto(settled.task)

        if metadata.dispatch_id != message.message_id:
            raise InvalidParamsError(message="Initial messageId must equal dispatch_id")
        invocation = self._parse_invocation(profile, message)
        deadline = self._deadline(metadata)
        await self._validate_references(
            actor,
            profile,
            metadata.run_id,
            list(message.reference_task_ids),
        )
        task_id = str(uuid4())
        if message.context_id and len(message.context_id) > 96:
            raise InvalidParamsError(message="contextId exceeds the size limit")
        context_id = message.context_id or str(uuid4())
        request_payload = MessageToDict(message, preserving_proto_field_name=False)
        request_fingerprint = _fingerprint(request_payload)
        created_at = _utc_now()
        task = Task(
            id=task_id,
            context_id=context_id,
            status=TaskStatus(
                state=TaskState.TASK_STATE_SUBMITTED,
                timestamp=_timestamp(created_at),
            ),
        )
        draft = TaskRecord(
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            agent_interface_id=profile.interface_id,
            run_id=metadata.run_id,
            dispatch_id=metadata.dispatch_id,
            request_fingerprint=request_fingerprint,
            task=task,
            invocation=invocation,
            deadline=deadline,
            reference_task_ids=tuple(message.reference_task_ids),
            created_at=created_at,
            updated_at=created_at,
            message_fingerprints={message.message_id: request_fingerprint},
        )
        draft.task.metadata.CopyFrom(_safe_task_metadata(draft, version=1))
        try:
            record, created = await self.store.create_or_get(draft)
        except DispatchConflict as exc:
            raise InvalidParamsError(message="dispatch_id was reused with another request") from exc
        if created or record.task.status.state in {
            TaskState.TASK_STATE_SUBMITTED,
            TaskState.TASK_STATE_WORKING,
        }:
            self._launch(
                record,
                profile,
                input_response=record.execution_input,
                already_working=(record.task.status.state == TaskState.TASK_STATE_WORKING),
            )
        if params.configuration.return_immediately:
            return clone_proto(record.task)
        settled = await self._wait_until_settled(record, profile=profile)
        return clone_proto(settled.task)

    async def _resume_input(
        self,
        actor: A2AActor,
        profile: AgentProfile,
        message: Message,
        metadata: DispatchMetadata,
    ) -> TaskRecord:
        try:
            current = await self.store.get(actor.tenant_id, profile.interface_id, message.task_id)
        except TaskMissing as exc:
            raise TaskNotFoundError() from exc
        message_payload = MessageToDict(message, preserving_proto_field_name=False)
        fingerprint = _fingerprint(message_payload)
        prior = current.message_fingerprints.get(message.message_id)
        if prior is not None:
            if prior != fingerprint:
                raise InvalidParamsError(message="messageId was reused with different content")
            return current
        if current.task.status.state != TaskState.TASK_STATE_INPUT_REQUIRED:
            raise InvalidParamsError(message="Task is not waiting for caller input")
        if not message.context_id or message.context_id != current.task.context_id:
            raise InvalidParamsError(message="contextId does not match the Task")
        if metadata.dispatch_id != current.dispatch_id or metadata.run_id != current.run_id:
            raise InvalidParamsError(message="Dispatch metadata does not match the Task")
        response = self._parse_input_response(message)
        if response.request_id != current.pending_input_request_id:
            raise InvalidParamsError(message="Input response does not match the pending request")

        while True:
            current = await self.store.get(actor.tenant_id, profile.interface_id, message.task_id)
            if current.task.status.state != TaskState.TASK_STATE_INPUT_REQUIRED:
                prior = current.message_fingerprints.get(message.message_id)
                if prior == fingerprint:
                    return current
                raise InvalidParamsError(message="Task is not waiting for caller input")
            next_version = current.version + 1
            task = clone_proto(current.task)
            task.status.CopyFrom(
                TaskStatus(state=TaskState.TASK_STATE_WORKING, timestamp=_timestamp())
            )
            updated = replace(
                current,
                task=task,
                version=next_version,
                updated_at=_utc_now(),
                pending_input_request_id=None,
                execution_input=response,
                message_fingerprints={
                    **current.message_fingerprints,
                    message.message_id: fingerprint,
                },
                events=current.events
                + (
                    VersionedEvent(
                        next_version,
                        TaskStatusUpdateEvent(
                            task_id=task.id,
                            context_id=task.context_id,
                            status=clone_proto(task.status),
                            metadata=_event_metadata(next_version),
                        ),
                    ),
                ),
            )
            updated.task.metadata.CopyFrom(_safe_task_metadata(updated, version=next_version))
            try:
                stored = await self.store.replace(updated, expected_version=current.version)
            except TaskVersionConflict:
                continue
            self._launch(stored, profile, input_response=response, already_working=True)
            return stored

    def _launch(
        self,
        record: TaskRecord,
        profile: AgentProfile,
        *,
        input_response: InputResponse | None,
        already_working: bool = False,
    ) -> None:
        if record.task.status.state not in {
            TaskState.TASK_STATE_SUBMITTED,
            TaskState.TASK_STATE_WORKING,
        }:
            return
        key = (record.tenant_id, record.agent_interface_id, record.task.id)
        active = self._jobs.get(key)
        if active is not None and not active.done():
            # A blocking SendMessage can observe INPUT_REQUIRED just before the
            # previous job's done callbacks run. Queue the resumed attempt after
            # that job has fully relinquished the key instead of losing it.
            active.add_done_callback(
                lambda _done: asyncio.get_running_loop().call_soon(
                    partial(
                        self._launch,
                        record,
                        profile,
                        input_response=input_response,
                        already_working=already_working,
                    )
                )
            )
            return
        cancel_token = asyncio.Event()
        self._cancel_tokens[key] = cancel_token
        job = asyncio.create_task(
            self._execute_job(
                record,
                profile,
                input_response=input_response,
                cancel_token=cancel_token,
                already_working=already_working,
            ),
            name=f"a2a:{record.agent_interface_id}:{record.task.id}",
        )
        self._jobs[key] = job

        def _cleanup(done: asyncio.Task[None]) -> None:
            if self._jobs.get(key) is done:
                self._jobs.pop(key, None)
                self._cancel_tokens.pop(key, None)

        job.add_done_callback(_cleanup)

    async def _execute_job(
        self,
        record: TaskRecord,
        profile: AgentProfile,
        *,
        input_response: InputResponse | None,
        cancel_token: asyncio.Event,
        already_working: bool,
    ) -> None:
        lease: TaskExecutionLease | None = None
        try:
            owner = f"{self._service_id}:{uuid4().hex}"
            lease = await self.store.claim_execution(
                record.tenant_id,
                record.agent_interface_id,
                record.task.id,
                owner=owner,
                lease_seconds=self._execution_lease_seconds,
            )
            if lease is None:
                return
            current = record
            if not already_working:
                current = await self._transition(
                    record,
                    allowed_states={TaskState.TASK_STATE_SUBMITTED},
                    new_state=TaskState.TASK_STATE_WORKING,
                    execution_lease=lease,
                )
            else:
                current = await self.store.get(
                    record.tenant_id,
                    record.agent_interface_id,
                    record.task.id,
                )
            if current.task.status.state != TaskState.TASK_STATE_WORKING:
                return
            timeout_seconds = max(0.001, (current.deadline - _utc_now()).total_seconds())
            context = AgentExecutionContext(
                tenant_id=current.tenant_id,
                actor_id=current.actor_id,
                agent_interface_id=current.agent_interface_id,
                task_id=current.task.id,
                context_id=current.task.context_id,
                run_id=current.run_id,
                dispatch_id=current.dispatch_id,
                deadline=current.deadline,
                reference_task_ids=current.reference_task_ids,
            )
            persisted_input = current.execution_input or input_response
            result = await self._execute_with_heartbeat(
                profile,
                context,
                current,
                persisted_input,
                lease,
                cancel_token,
                timeout_seconds=timeout_seconds,
            )
            if cancel_token.is_set():
                return
            await self._apply_execution_result(current, profile, result, lease)
        except TimeoutError:
            await self._fail_if_working(
                record,
                code="AGENT_DEADLINE_EXCEEDED",
                message="The agent task exceeded its deadline.",
                execution_lease=lease,
            )
        except TaskExecutionLeaseLost:
            return
        except asyncio.CancelledError:
            return
        except Exception:
            # Exception strings may contain provider payloads or model scratchpads.
            # Emit only stable identifiers; public Task state gets a safe code.
            logger.error(
                "A2A executor failed interface=%s task=%s",
                record.agent_interface_id,
                record.task.id,
            )
            await self._fail_if_working(
                record,
                code="AGENT_EXECUTION_FAILED",
                message="The agent task could not be completed.",
                execution_lease=lease,
            )
        finally:
            if lease is not None:
                await self.store.release_execution(lease)

    async def _execute_with_heartbeat(
        self,
        profile: AgentProfile,
        context: AgentExecutionContext,
        record: TaskRecord,
        input_response: InputResponse | None,
        lease: TaskExecutionLease,
        cancel_token: asyncio.Event,
        *,
        timeout_seconds: float,
    ) -> Any:
        """Run one executor while a database-backed heartbeat owns its fence."""

        stop = asyncio.Event()
        execution_task = asyncio.create_task(
            profile.executor.execute(
                context,
                record.invocation.model_copy(deep=True),
                input_response.model_copy(deep=True) if input_response else None,
            ),
            name=f"a2a-executor:{record.agent_interface_id}:{record.task.id}",
        )
        heartbeat_task = asyncio.create_task(
            self._heartbeat_execution(
                lease,
                stop=stop,
                cancel_token=cancel_token,
                execution_task=execution_task,
            ),
            name=f"a2a-heartbeat:{record.agent_interface_id}:{record.task.id}",
        )
        try:
            async with asyncio.timeout(timeout_seconds):
                return await execution_task
        finally:
            stop.set()
            if not execution_task.done():
                execution_task.cancel()
            heartbeat_task.cancel()
            await asyncio.gather(execution_task, heartbeat_task, return_exceptions=True)

    async def _heartbeat_execution(
        self,
        lease: TaskExecutionLease,
        *,
        stop: asyncio.Event,
        cancel_token: asyncio.Event,
        execution_task: asyncio.Task[Any],
    ) -> None:
        while not stop.is_set():
            try:
                await asyncio.wait_for(
                    stop.wait(),
                    timeout=self._heartbeat_interval_seconds,
                )
                return
            except TimeoutError:
                pass
            try:
                renewed = await self.store.renew_execution(
                    lease,
                    lease_seconds=self._execution_lease_seconds,
                )
            except Exception:
                logger.exception(
                    "A2A Task lease heartbeat failed interface=%s task=%s",
                    lease.agent_interface_id,
                    lease.task_id,
                )
                renewed = None
            if renewed is None:
                cancel_token.set()
                execution_task.cancel()
                return

    async def _apply_execution_result(
        self,
        record: TaskRecord,
        profile: AgentProfile,
        result: Any,
        execution_lease: TaskExecutionLease,
    ) -> None:
        if isinstance(result, CompletedExecution):
            artifacts = self._validated_output_artifacts(record, profile, result.artifacts)
            await self._transition(
                record,
                allowed_states={TaskState.TASK_STATE_WORKING},
                new_state=TaskState.TASK_STATE_COMPLETED,
                artifacts=artifacts,
                execution_lease=execution_lease,
            )
            return
        if isinstance(result, InputRequiredExecution):
            message = _structured_message(
                task_id=record.task.id,
                context_id=record.task.context_id,
                schema_uri=INPUT_REQUEST_SCHEMA_URI,
                payload=result.request.model_dump(mode="json"),
            )
            await self._transition(
                record,
                allowed_states={TaskState.TASK_STATE_WORKING},
                new_state=TaskState.TASK_STATE_INPUT_REQUIRED,
                status_message=message,
                pending_input_request_id=result.request.request_id,
                execution_lease=execution_lease,
            )
            return
        if isinstance(result, AuthRequiredExecution):
            message = _structured_message(
                task_id=record.task.id,
                context_id=record.task.context_id,
                schema_uri="urn:routepilot:a2a:dependency-auth-request:v1",
                payload={"dependency": result.dependency, "message": result.message},
            )
            await self._transition(
                record,
                allowed_states={TaskState.TASK_STATE_WORKING},
                new_state=TaskState.TASK_STATE_AUTH_REQUIRED,
                status_message=message,
                execution_lease=execution_lease,
            )
            return
        if isinstance(result, FailedExecution):
            await self._fail_if_working(
                record,
                code=result.code,
                message=result.message,
                execution_lease=execution_lease,
            )
            return
        raise ValueError("executor returned an unsupported result")

    def _validated_output_artifacts(
        self,
        record: TaskRecord,
        profile: AgentProfile,
        outputs: list[ArtifactOutput],
    ) -> list[Artifact]:
        identifiers: set[str] = set()
        artifacts: list[Artifact] = []
        for output in outputs:
            if output.contract not in profile.allowed_output_contracts:
                raise ValueError("executor returned an unauthorized Artifact contract")
            self._contract_validator(output.contract, output.payload)
            artifact_id = output.artifact_id or str(uuid4())
            if artifact_id in identifiers:
                raise ValueError("executor returned duplicate Artifact identifiers")
            identifiers.add(artifact_id)
            artifacts.append(
                Artifact(
                    artifact_id=artifact_id,
                    name=output.name,
                    description=output.description or "",
                    parts=[
                        Part(
                            data=_value(output.payload),
                            metadata=_struct(
                                {
                                    "schema_uri": artifact_schema_uri(output.contract),
                                    "schema_version": 1,
                                }
                            ),
                        )
                    ],
                    metadata=_struct(
                        {
                            TRAVEL_ARTIFACT_EXTENSION_URI: {
                                "contract": output.contract,
                                "run_id": record.run_id,
                            }
                        }
                    ),
                    extensions=[TRAVEL_ARTIFACT_EXTENSION_URI],
                )
            )
        return artifacts

    async def _fail_if_working(
        self,
        record: TaskRecord,
        *,
        code: str,
        message: str,
        execution_lease: TaskExecutionLease | None = None,
    ) -> None:
        safe_message = _structured_message(
            task_id=record.task.id,
            context_id=record.task.context_id,
            schema_uri=PUBLIC_ERROR_SCHEMA_URI,
            payload={"code": code, "message": message, "retryable": False},
        )
        await self._transition(
            record,
            allowed_states={TaskState.TASK_STATE_WORKING, TaskState.TASK_STATE_SUBMITTED},
            new_state=TaskState.TASK_STATE_FAILED,
            status_message=safe_message,
            execution_lease=execution_lease,
        )

    async def _transition(
        self,
        record: TaskRecord,
        *,
        allowed_states: set[Any],
        new_state: Any,
        status_message: Message | None = None,
        artifacts: list[Artifact] | None = None,
        pending_input_request_id: str | None = None,
        execution_lease: TaskExecutionLease | None = None,
    ) -> TaskRecord:
        while True:
            try:
                current = await self.store.get(
                    record.tenant_id,
                    record.agent_interface_id,
                    record.task.id,
                )
            except TaskMissing:
                return record
            if current.task.status.state not in allowed_states:
                return current
            next_version = current.version + 1
            task = clone_proto(current.task)
            status = TaskStatus(state=new_state, timestamp=_timestamp())
            if status_message is not None:
                status.message.CopyFrom(status_message)
            task.status.CopyFrom(status)
            new_events: list[VersionedEvent] = []
            for artifact in artifacts or []:
                task.artifacts.add().CopyFrom(artifact)
                new_events.append(
                    VersionedEvent(
                        next_version,
                        TaskArtifactUpdateEvent(
                            task_id=task.id,
                            context_id=task.context_id,
                            artifact=clone_proto(artifact),
                            append=False,
                            last_chunk=True,
                            metadata=_event_metadata(next_version),
                        ),
                    )
                )
            new_events.append(
                VersionedEvent(
                    next_version,
                    TaskStatusUpdateEvent(
                        task_id=task.id,
                        context_id=task.context_id,
                        status=clone_proto(status),
                        metadata=_event_metadata(next_version),
                    ),
                )
            )
            updated = replace(
                current,
                task=task,
                version=next_version,
                updated_at=_utc_now(),
                pending_input_request_id=pending_input_request_id,
                execution_input=(
                    current.execution_input if new_state == TaskState.TASK_STATE_WORKING else None
                ),
                events=current.events + tuple(new_events),
            )
            updated.task.metadata.CopyFrom(_safe_task_metadata(updated, version=next_version))
            try:
                return await self.store.replace(
                    updated,
                    expected_version=current.version,
                    execution_lease=execution_lease,
                )
            except TaskVersionConflict:
                continue

    async def _wait_until_settled(
        self,
        record: TaskRecord,
        *,
        profile: AgentProfile,
    ) -> TaskRecord:
        current = record
        while current.task.status.state not in SETTLED_STATES:
            self._launch(
                current,
                profile,
                input_response=current.execution_input,
                already_working=(current.task.status.state == TaskState.TASK_STATE_WORKING),
            )
            remaining = max(0.001, (current.deadline - _utc_now()).total_seconds())
            changed = await self.store.wait_for_change(
                current.tenant_id,
                current.agent_interface_id,
                current.task.id,
                after_version=current.version,
                timeout_seconds=min(remaining, 1.0),
            )
            if changed is None:
                if _utc_now() >= current.deadline:
                    await self._fail_if_working(
                        current,
                        code="AGENT_DEADLINE_EXCEEDED",
                        message="The agent task exceeded its deadline.",
                    )
                current = await self.store.get(
                    current.tenant_id,
                    current.agent_interface_id,
                    current.task.id,
                )
            else:
                current = changed
        return current

    async def get_task(
        self,
        actor: A2AActor,
        agent_interface_id: str,
        tenant: str,
        task_id: str,
    ) -> TaskRecord:
        """Return a tenant-scoped Task record or a non-enumerating not-found."""

        self._assert_tenant(actor, tenant)
        self.registry.get(agent_interface_id)
        try:
            record = await self.store.get(actor.tenant_id, agent_interface_id, task_id)
        except TaskMissing as exc:
            raise TaskNotFoundError() from exc
        if record.task.status.state in {
            TaskState.TASK_STATE_SUBMITTED,
            TaskState.TASK_STATE_WORKING,
        }:
            self._launch(
                record,
                self.registry.get(agent_interface_id),
                input_response=record.execution_input,
                already_working=(record.task.status.state == TaskState.TASK_STATE_WORKING),
            )
        return record

    async def list_tasks(
        self,
        actor: A2AActor,
        agent_interface_id: str,
        tenant: str,
        *,
        context_id: str | None = None,
        state: int | None = None,
    ) -> list[TaskRecord]:
        """List Tasks only inside the authenticated tenant and interface."""

        self._assert_tenant(actor, tenant)
        self.registry.get(agent_interface_id)
        records = await self.store.list(
            actor.tenant_id,
            agent_interface_id,
            context_id=context_id,
            state=state,
        )
        profile = self.registry.get(agent_interface_id)
        for record in records:
            if record.task.status.state in {
                TaskState.TASK_STATE_SUBMITTED,
                TaskState.TASK_STATE_WORKING,
            }:
                self._launch(
                    record,
                    profile,
                    input_response=record.execution_input,
                    already_working=(record.task.status.state == TaskState.TASK_STATE_WORKING),
                )
        return records

    async def recover_dispatch(
        self,
        actor: A2AActor,
        agent_interface_id: str,
        *,
        run_id: str,
        dispatch_id: str,
        wait_until_settled: bool = True,
    ) -> Task | None:
        """Recover one deterministic local dispatch using its persisted invocation."""

        profile = self.registry.get(agent_interface_id)
        try:
            record = await self.store.get_by_dispatch(
                actor.tenant_id,
                agent_interface_id,
                dispatch_id,
            )
        except TaskMissing:
            return None
        if record.run_id != run_id:
            raise InvalidParamsError(message="Dispatch belongs to another Product Run")
        if record.task.status.state in {
            TaskState.TASK_STATE_SUBMITTED,
            TaskState.TASK_STATE_WORKING,
        }:
            self._launch(
                record,
                profile,
                input_response=record.execution_input,
                already_working=(record.task.status.state == TaskState.TASK_STATE_WORKING),
            )
        if wait_until_settled:
            record = await self._wait_until_settled(record, profile=profile)
        return clone_proto(record.task)

    def _cancel_local(self, tenant_id: str, agent_interface_id: str, task_id: str) -> None:
        key = (tenant_id, agent_interface_id, task_id)
        token = self._cancel_tokens.get(key)
        if token is not None:
            token.set()
        job = self._jobs.get(key)
        if job is not None and not job.done():
            job.cancel()

    async def cancel_task(
        self,
        actor: A2AActor,
        agent_interface_id: str,
        tenant: str,
        task_id: str,
    ) -> Task:
        """Persist cancellation before fencing and stopping local execution."""

        current = await self.get_task(actor, agent_interface_id, tenant, task_id)
        if current.task.status.state not in CANCELABLE_STATES:
            raise TaskNotCancelableError()
        canceled = await self._transition(
            current,
            allowed_states=CANCELABLE_STATES,
            new_state=TaskState.TASK_STATE_CANCELED,
        )
        self._cancel_local(actor.tenant_id, agent_interface_id, task_id)
        return clone_proto(canceled.task)

    async def cancel_run_tasks(self, actor: A2AActor, run_id: str) -> list[Task]:
        """Persistently cancel every cancelable A2A Task mapped to a Product Run."""

        records = await self.store.list_for_run(actor.tenant_id, run_id)
        canceled_tasks: list[Task] = []
        for record in records:
            current = record
            if current.task.status.state in CANCELABLE_STATES:
                current = await self._transition(
                    current,
                    allowed_states=CANCELABLE_STATES,
                    new_state=TaskState.TASK_STATE_CANCELED,
                )
            if current.task.status.state == TaskState.TASK_STATE_CANCELED:
                self._cancel_local(
                    actor.tenant_id,
                    current.agent_interface_id,
                    current.task.id,
                )
                canceled_tasks.append(clone_proto(current.task))
        return canceled_tasks

    async def subscribe(
        self,
        record: TaskRecord,
        *,
        after_version: int,
    ) -> AsyncGenerator[Event, None]:
        """Replay retained Task events, then wait for monotonic updates."""

        cursor = after_version
        current = record
        while True:
            events = [event for event in current.events if event.version > cursor]
            for event in events:
                yield clone_proto(event.event)
            if events:
                cursor = max(item.version for item in events)
            if current.task.status.state in SETTLED_STATES:
                return
            changed = await self.store.wait_for_change(
                current.tenant_id,
                current.agent_interface_id,
                current.task.id,
                after_version=cursor,
                timeout_seconds=15.0,
            )
            if changed is None:
                continue
            current = changed

    async def list_run_task_refs(self, actor: A2AActor, run_id: str) -> list[RunTaskRef]:
        """Expose the explicit Product Run/A2A Task reconciliation mapping."""

        records = await self.store.list_for_run(actor.tenant_id, run_id)
        return [
            RunTaskRef(
                run_id=record.run_id,
                tenant_id=record.tenant_id,
                agent_interface_id=record.agent_interface_id,
                task_id=record.task.id,
                context_id=record.task.context_id,
                dispatch_id=record.dispatch_id,
                status=TaskState.Name(record.task.status.state),
                version=record.version,
                deadline=record.deadline,
            )
            for record in records
        ]

    async def shutdown(self) -> None:
        """Cancel local jobs and release the selected persistence adapter."""

        jobs = list(self._jobs.values())
        for job in jobs:
            job.cancel()
        if jobs:
            await asyncio.gather(*jobs, return_exceptions=True)
        await self.store.close()


__all__ = ["SETTLED_STATES", "TERMINAL_STATES", "TaskService"]
