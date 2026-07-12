"""RunCoordinator, A2A orchestration adapter, and V1 runtime assembly."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol

from .models import (
    ArtifactStatus,
    ArtifactView,
    PUBLIC_EVENT_TYPES,
    Principal,
    RunCreateRequest,
    RunInputField,
    RunLifecycle,
    RunPendingInput,
    RunResumeRequest,
    RunView,
    TERMINAL_RUN_STATES,
    new_public_id,
    utc_now,
)
from .store import (
    IdempotentRunResult,
    InMemoryPlatformStore,
    PlatformStore,
    RunExecutionBusy,
    RunExecutionLease,
    RunExecutionLeaseLost,
    VersionConflict,
    canonical_request_hash,
)
from .replanning import apply_replan_patch

logger = logging.getLogger(__name__)

ProgressCallback = Callable[[str, str, int], Awaitable[None]]
CancelRunTasksCallback = Callable[[Principal, str], Awaitable[None]]


@dataclass(frozen=True, slots=True)
class ExecutionArtifact:
    """One contract-valid Artifact proposed by an execution profile."""

    artifact_id: str | None
    artifact_type: str
    schema_version: int
    content: dict[str, Any]
    status: ArtifactStatus = ArtifactStatus.VALIDATED


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    """Safe Artifact graph returned by one whole-run execution profile."""

    artifact_type: str
    schema_version: int
    content: dict[str, Any]
    artifact_id: str | None = None
    supporting_artifacts: tuple[ExecutionArtifact, ...] = ()
    publishable: bool = True


class WholeRunExecutor(Protocol):
    """Execute a complete run without exposing private reasoning."""

    async def execute(
        self,
        run: RunView,
        principal: Principal,
        progress: ProgressCallback,
    ) -> ExecutionResult: ...


class OrchestratedWholeRunExecutor:
    """Adapter from Product Run commands to the A2A Travel Orchestrator V2."""

    def __init__(self, orchestrator: Any, *, brief_factory: Any | None = None):
        self._orchestrator = orchestrator
        self._brief_factory = brief_factory

    async def execute(
        self,
        run: RunView,
        principal: Principal,
        progress: ProgressCallback,
    ) -> ExecutionResult:
        from agent.travel_agent.runtime_v2 import StructuredTripRequest
        from routepilot_contracts.artifacts import TripBrief
        from routepilot_contracts.validation import validate_contract

        raw_brief = run.command.payload.get("trip_brief")
        if isinstance(raw_brief, dict):
            brief = validate_contract("TripBrief@1", raw_brief)
        else:
            raw_request = run.command.payload.get("trip_request")
            resume_input = run.command.payload.get("resume_input")
            if not isinstance(raw_request, dict) and isinstance(resume_input, dict):
                values = resume_input.get("values")
                if isinstance(values, dict):
                    raw_request = {
                        "destination": values.get("destination"),
                        "start_date": values.get("start_date"),
                        "end_date": values.get("end_date"),
                        "adults": values.get("adults", 1),
                        "seniors": values.get("seniors", 0),
                        "budget_min": str(values.get("budget_min", "")),
                        "budget_max": str(values.get("budget_max", "")),
                        "currency": values.get("currency", "CNY"),
                        "preferences": values.get("preferences", []),
                        "accessibility_needs": values.get("accessibility_needs", []),
                    }
            if not isinstance(raw_request, dict) or self._brief_factory is None:
                raise ValueError("v2 execution requires command.payload.trip_brief or trip_request")
            brief = await self._brief_factory.build(
                StructuredTripRequest.model_validate(raw_request),
                tenant_id=principal.tenant_id,
                actor_id=principal.user_id,
                run_id=run.run_id,
            )
        if not isinstance(brief, TripBrief):
            raise ValueError("trip_brief contract is incompatible")
        raw_title = run.command.payload.get("title")
        title = (
            raw_title.strip()
            if isinstance(raw_title, str) and raw_title.strip()
            else f"{brief.destination.display_name}旅行计划"
        )
        result = await self._orchestrator.execute(
            tenant_id=principal.tenant_id,
            actor_id=principal.user_id,
            run_id=run.run_id,
            trip_id=run.trip_id,
            title=title,
            brief=brief,
            goal=run.command.message,
            progress=progress,
        )
        supporting = (
            result.brief,
            result.evidence,
            result.candidates,
            result.plan,
            result.constraints,
            result.semantics,
            result.validation,
        )
        return ExecutionResult(
            artifact_id=result.snapshot.artifact_id,
            artifact_type="TripSnapshot",
            schema_version=1,
            content=result.snapshot.model_dump(mode="json"),
            supporting_artifacts=tuple(
                ExecutionArtifact(
                    artifact_id=artifact.artifact_id,
                    artifact_type=artifact.artifact_type,
                    schema_version=artifact.schema_version,
                    content=artifact.model_dump(mode="json"),
                    status=(
                        ArtifactStatus.CANDIDATE
                        if artifact is result.plan and not result.validation.publishable
                        else ArtifactStatus.VALIDATED
                    ),
                )
                for artifact in supporting
            ),
            publishable=result.validation.publishable,
        )


PUBLIC_EVENT_DATA_FIELDS: dict[str, frozenset[str]] = {
    "run.accepted": frozenset({"lifecycle_state", "phase", "control_version"}),
    "run.lifecycle_changed": frozenset(
        {"previous_state", "lifecycle_state", "reason_code", "control_version"}
    ),
    "run.phase_changed": frozenset(
        {"previous_phase", "phase", "label", "progress_percent", "control_version"}
    ),
    "agent.activity": frozenset(
        {"agent", "activity", "status", "duration_ms", "sources", "control_version"}
    ),
    "artifact.candidate_updated": frozenset({"artifact_ref", "status", "control_version"}),
    "artifact.published": frozenset({"artifact_ref", "status", "control_version"}),
    "citation.added": frozenset({"citation", "artifact_ref", "control_version"}),
    "risk.detected": frozenset(
        {"risk_id", "severity", "message", "artifact_ref", "control_version"}
    ),
    "input.required": frozenset(
        {"request_id", "prompt", "fields", "expires_at", "control_version"}
    ),
    "approval.required": frozenset(
        {"approval_id", "prompt", "artifact_ref", "expires_at", "control_version"}
    ),
    "run.completed": frozenset(
        {"lifecycle_state", "snapshot_ref", "duration_ms", "control_version"}
    ),
    "run.failed": frozenset({"lifecycle_state", "failed_phase", "error", "control_version"}),
    "run.canceled": frozenset({"lifecycle_state", "canceled_by", "reason", "control_version"}),
}


def _contract_phase(phase: str) -> str:
    normalized = str(phase or "").strip().lower()
    if normalized in {
        "accepted",
        "clarification",
        "research",
        "planning",
        "validation",
        "approval",
        "publishing",
        "finalizing",
        "finished",
    }:
        return normalized
    if normalized in {"starting"}:
        return "accepted"
    if normalized in {"understanding", "intent", "clarify"}:
        return "clarification"
    if normalized in {"composing", "compose"}:
        return "finalizing"
    if normalized in {"published"}:
        return "publishing"
    if normalized in {"completed", "failed", "canceled", "canceling"}:
        return "finished"
    return "planning"


def project_public_event_data(
    event_type: PUBLIC_EVENT_TYPES,
    data: dict[str, Any],
    *,
    run: RunView | None = None,
    lifecycle_state: RunLifecycle | None = None,
    phase: str | None = None,
    artifact: ArtifactView | None = None,
    error_code: str | None = None,
) -> dict[str, Any]:
    """Whitelist event data so internal payloads can never pass through."""

    allowed = PUBLIC_EVENT_DATA_FIELDS.get(event_type)
    if allowed is None:
        raise ValueError(f"unsupported public event type: {event_type}")
    projected = {key: value for key, value in data.items() if key in allowed}
    if event_type == "run.lifecycle_changed" and run is not None:
        projected = {
            "previous_state": run.lifecycle_state.value,
            "lifecycle_state": (lifecycle_state or run.lifecycle_state).value,
            "reason_code": str(data.get("reason_code") or data.get("reason") or "state_transition")[
                :128
            ],
        }
    elif event_type == "run.phase_changed" and run is not None:
        projected = {
            "previous_phase": _contract_phase(run.phase),
            "phase": _contract_phase(phase or str(data.get("phase") or run.phase)),
            "progress_percent": max(
                0,
                min(100, int(data.get("progress_percent") or data.get("progress") or 0)),
            ),
            "label": str(data.get("label") or "进度已更新")[:256],
        }
    elif event_type in {"artifact.candidate_updated", "artifact.published"}:
        artifact_id = artifact.artifact_id if artifact else str(data.get("artifact_id") or "")
        version = artifact.version if artifact else int(data.get("artifact_version") or 1)
        artifact_type = artifact.artifact_type if artifact else str(data.get("artifact_type") or "")
        schema_version = (
            artifact.schema_version if artifact else int(data.get("schema_version") or 1)
        )
        projected = {
            "artifact_ref": {
                "artifact_type": artifact_type,
                "artifact_id": artifact_id,
                "schema_version": schema_version,
                "version": version,
            },
            "status": str(data.get("status") or "candidate"),
        }
    elif event_type == "run.completed" and run is not None:
        projected = {
            "lifecycle_state": RunLifecycle.COMPLETED.value,
            "snapshot_ref": {
                "artifact_type": str(data.get("artifact_type") or "TripSnapshot"),
                "artifact_id": str(data.get("artifact_id") or run.result_artifact_id or ""),
                "schema_version": int(data.get("schema_version") or 1),
                "version": int(data.get("artifact_version") or run.result_artifact_version or 1),
            },
            "duration_ms": max(0, int((utc_now() - run.created_at).total_seconds() * 1000)),
        }
    elif event_type == "run.failed" and run is not None:
        code = str(error_code or data.get("error_code") or "RUN_EXECUTION_FAILED")[:64]
        projected = {
            "lifecycle_state": RunLifecycle.FAILED.value,
            "failed_phase": _contract_phase(phase or run.phase),
            "error": {
                "code": code,
                "message": "规划未能完成，请稍后重试。",
                "retryable": code != "VALIDATION_BLOCKED",
            },
        }
    elif event_type == "run.canceled":
        projected = {
            "lifecycle_state": RunLifecycle.CANCELED.value,
            "canceled_by": str(data.get("canceled_by") or "user"),
            "reason": str(data.get("reason") or "用户已取消本次规划。")[:2000],
        }
    return projected


class RunCoordinator:
    """Unique Product Run control plane using CAS for every transition."""

    def __init__(
        self,
        store: PlatformStore,
        executor: WholeRunExecutor,
        *,
        in_process_execution: bool = True,
        cancel_run_tasks: CancelRunTasksCallback | None = None,
    ):
        self.store = store
        self.executor = executor
        self.in_process_execution = in_process_execution
        self._cancel_run_tasks = cancel_run_tasks
        self._tasks: dict[str, asyncio.Task[None]] = {}
        self._task_guard = asyncio.Lock()

    async def submit(
        self,
        principal: Principal,
        trip_id: str,
        request: RunCreateRequest,
        *,
        idempotency_key: str,
        trace_id: str,
    ) -> IdempotentRunResult:
        request_hash = canonical_request_hash(
            {
                "trip_id": trip_id,
                "request": request.model_dump(mode="json"),
            }
        )
        command = request.command
        if command.type == "trip.replan":
            from routepilot_contracts.artifacts import TripSnapshot
            from routepilot_contracts.validation import validate_contract
            from .models import ReplanPatch

            if request.base_artifact_id is None or request.base_artifact_version is None:
                raise ValueError("replan requires a pinned base Artifact")
            base = await self.store.get_artifact(
                principal,
                request.base_artifact_id,
                version=request.base_artifact_version,
            )
            if base.trip_id != trip_id or base.artifact_type != "TripSnapshot":
                raise VersionConflict(base.version)
            parsed = validate_contract("TripSnapshot@1", base.content)
            if not isinstance(parsed, TripSnapshot):
                raise ValueError("base Artifact is not a TripSnapshot")
            patch = ReplanPatch.model_validate(command.payload.get("patch"))
            patched_brief = apply_replan_patch(parsed.brief, patch, principal=principal)
            command = command.model_copy(
                update={
                    "payload": {
                        **command.payload,
                        "trip_brief": patched_brief.model_dump(mode="json"),
                        "base_snapshot_ref": {
                            "artifact_id": base.artifact_id,
                            "version": base.version,
                        },
                    }
                }
            )
        result = await self.store.create_run(
            principal,
            trip_id=trip_id,
            command=command,
            base_artifact_id=request.base_artifact_id,
            base_artifact_version=request.base_artifact_version,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
            trace_id=trace_id,
        )
        if not result.replayed and self.in_process_execution:
            task = asyncio.create_task(
                self._execute(result.run.run_id, principal),
                name=f"routepilot-run-{result.run.run_id}",
            )
            async with self._task_guard:
                self._tasks[result.run.run_id] = task
            task.add_done_callback(lambda _: asyncio.create_task(self._forget(result.run.run_id)))
        return result

    @staticmethod
    def _required_input(run: RunView) -> RunPendingInput | None:
        """Build one persisted clarification request for an incomplete plan command."""

        if run.command.type != "trip.plan":
            return None
        if run.command.payload.get("interactive") is not True:
            return None
        if isinstance(run.command.payload.get("trip_brief"), dict) or isinstance(
            run.command.payload.get("trip_request"), dict
        ):
            return None
        if isinstance(run.command.payload.get("resume_input"), dict):
            return None
        return RunPendingInput(
            request_id=new_public_id("input"),
            prompt="请补充目的地、日期、同行人数和预算后继续规划。",
            fields=[
                RunInputField(field_id="destination", label="目的地", input_type="text"),
                RunInputField(field_id="start_date", label="开始日期", input_type="date"),
                RunInputField(field_id="end_date", label="结束日期", input_type="date"),
                RunInputField(field_id="adults", label="成人数量", input_type="number"),
                RunInputField(field_id="seniors", label="老人数量", input_type="number", required=False),
                RunInputField(field_id="budget_min", label="最低预算", input_type="number"),
                RunInputField(field_id="budget_max", label="最高预算", input_type="number"),
                RunInputField(
                    field_id="currency",
                    label="币种",
                    input_type="single_select",
                    options=["CNY", "USD", "EUR", "JPY"],
                ),
            ],
            expires_at=utc_now() + timedelta(minutes=30),
        )

    async def resume(
        self,
        principal: Principal,
        run_id: str,
        request: RunResumeRequest,
        *,
        idempotency_key: str,
    ) -> IdempotentRunResult:
        """Idempotently resume a persisted input interruption."""

        request_hash = canonical_request_hash(
            {"run_id": run_id, "request": request.model_dump(mode="json")}
        )
        result = await self.store.resume_run(
            principal,
            run_id,
            expected_control_version=request.expected_control_version,
            request_id=request.request_id,
            values=request.values,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        if not result.replayed and self.in_process_execution:
            task = asyncio.create_task(
                self._execute(result.run.run_id, principal),
                name=f"routepilot-run-{result.run.run_id}-resume",
            )
            async with self._task_guard:
                self._tasks[result.run.run_id] = task
            task.add_done_callback(lambda _: asyncio.create_task(self._forget(result.run.run_id)))
        return result

    async def execute_existing(
        self,
        principal: Principal,
        run_id: str,
        *,
        execution_owner: str | None = None,
        lease_seconds: float = 60.0,
    ) -> RunView:
        """Claim, heartbeat, execute, and safely release one external Run lease."""

        current = await self.store.get_run(principal, run_id)
        if current.lifecycle_state not in {RunLifecycle.QUEUED, RunLifecycle.RUNNING}:
            return current
        owner = execution_owner or new_public_id("worker")
        lease = await self.store.claim_run_execution(
            principal,
            run_id,
            owner=owner,
            lease_seconds=lease_seconds,
        )
        if lease is None:
            current = await self.store.get_run(principal, run_id)
            if current.lifecycle_state in {RunLifecycle.QUEUED, RunLifecycle.RUNNING}:
                raise RunExecutionBusy("run execution is owned by another worker")
            return current

        lease_lost = asyncio.Event()
        stop_heartbeat = asyncio.Event()
        execution_task = asyncio.create_task(
            self._execute(
                run_id,
                principal,
                execution_lease=lease,
            ),
            name=f"routepilot-external-run-{run_id}-{lease.attempt}",
        )
        heartbeat_task = asyncio.create_task(
            self._heartbeat_execution_lease(
                principal,
                lease,
                lease_seconds=lease_seconds,
                stop=stop_heartbeat,
                lease_lost=lease_lost,
                execution_task=execution_task,
            ),
            name=f"routepilot-run-heartbeat-{run_id}-{lease.attempt}",
        )
        try:
            try:
                await execution_task
            except asyncio.CancelledError:
                if lease_lost.is_set():
                    raise RunExecutionLeaseLost("run execution lease heartbeat was lost") from None
                raise
            if lease_lost.is_set():
                raise RunExecutionLeaseLost("run execution lease heartbeat was lost")
        finally:
            stop_heartbeat.set()
            heartbeat_task.cancel()
            await asyncio.gather(heartbeat_task, return_exceptions=True)
            await self.store.release_run_execution(principal, lease)
        return await self.store.get_run(principal, run_id)

    async def _heartbeat_execution_lease(
        self,
        principal: Principal,
        lease: RunExecutionLease,
        *,
        lease_seconds: float,
        stop: asyncio.Event,
        lease_lost: asyncio.Event,
        execution_task: asyncio.Task[None],
    ) -> None:
        interval = max(0.02, min(20.0, lease_seconds / 3))
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=interval)
                return
            except TimeoutError:
                pass
            try:
                renewed = await self.store.renew_run_execution(
                    principal,
                    lease,
                    lease_seconds=lease_seconds,
                )
            except Exception:
                logger.exception(
                    "V1 run lease heartbeat failed",
                    extra={"run_id": lease.run_id, "attempt": lease.attempt},
                )
                renewed = None
            if renewed is None:
                lease_lost.set()
                execution_task.cancel()
                return

    async def _forget(self, run_id: str) -> None:
        async with self._task_guard:
            self._tasks.pop(run_id, None)

    async def close(self) -> None:
        """Cancel and drain local reference tasks during application shutdown."""

        async with self._task_guard:
            tasks = list(self._tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _transition(
        self,
        principal: Principal,
        run: RunView,
        *,
        lifecycle_state: RunLifecycle | None = None,
        phase: str | None = None,
        pending_input: RunPendingInput | None = None,
        artifact: ArtifactView | None = None,
        error_code: str | None = None,
        execution_lease: RunExecutionLease | None = None,
        event_type: PUBLIC_EVENT_TYPES,
        data: dict[str, Any],
    ) -> RunView:
        updated, _ = await self.store.mutate_run(
            principal,
            run.run_id,
            expected_control_version=run.control_version,
            lifecycle_state=lifecycle_state,
            phase=phase,
            pending_input=pending_input,
            result_artifact=artifact,
            public_error_code=error_code,
            execution_lease=execution_lease,
            event_type=event_type,
            event_data=project_public_event_data(
                event_type,
                data,
                run=run,
                lifecycle_state=lifecycle_state,
                phase=phase,
                artifact=artifact,
                error_code=error_code,
            ),
        )
        return updated

    async def _progress(
        self,
        principal: Principal,
        run_id: str,
        phase: str,
        label: str,
        progress: int,
        execution_lease: RunExecutionLease | None = None,
    ) -> None:
        current = await self.store.get_run(principal, run_id)
        if current.lifecycle_state in TERMINAL_RUN_STATES | {RunLifecycle.CANCEL_REQUESTED}:
            raise asyncio.CancelledError
        await self._transition(
            principal,
            current,
            phase=phase,
            execution_lease=execution_lease,
            event_type="run.phase_changed",
            data={
                "phase": phase,
                "label": label[:160],
                "progress": max(0, min(100, int(progress))),
            },
        )

    async def _execute(
        self,
        run_id: str,
        principal: Principal,
        *,
        execution_lease: RunExecutionLease | None = None,
    ) -> None:
        try:
            current = await self.store.get_run(principal, run_id)
            if current.lifecycle_state == RunLifecycle.QUEUED:
                current = await self._transition(
                    principal,
                    current,
                    lifecycle_state=RunLifecycle.RUNNING,
                    phase="starting",
                    execution_lease=execution_lease,
                    event_type="run.lifecycle_changed",
                    data={"lifecycle_state": RunLifecycle.RUNNING.value},
                )
            elif current.lifecycle_state != RunLifecycle.RUNNING:
                return

            pending_input = self._required_input(current)
            if pending_input is not None:
                await self._transition(
                    principal,
                    current,
                    lifecycle_state=RunLifecycle.WAITING_INPUT,
                    phase="clarification",
                    pending_input=pending_input,
                    execution_lease=execution_lease,
                    event_type="input.required",
                    data=pending_input.model_dump(mode="json"),
                )
                return

            async def progress(phase: str, label: str, percent: int) -> None:
                await self._progress(
                    principal,
                    run_id,
                    phase,
                    label,
                    percent,
                    execution_lease,
                )

            result = await self.executor.execute(current, principal, progress)
            current = await self.store.get_run(principal, run_id)
            if current.lifecycle_state != RunLifecycle.RUNNING:
                raise asyncio.CancelledError

            for supporting in result.supporting_artifacts:
                await self.store.create_artifact(
                    principal,
                    trip_id=current.trip_id,
                    artifact_id=supporting.artifact_id,
                    artifact_type=supporting.artifact_type,
                    schema_version=supporting.schema_version,
                    content=supporting.content,
                    status=supporting.status,
                    execution_lease=execution_lease,
                )
            current = await self.store.get_run(principal, run_id)
            if current.lifecycle_state != RunLifecycle.RUNNING:
                raise asyncio.CancelledError
            artifact = await self.store.create_artifact(
                principal,
                trip_id=current.trip_id,
                artifact_id=result.artifact_id,
                artifact_type=result.artifact_type,
                schema_version=result.schema_version,
                content=result.content,
                status=ArtifactStatus.CANDIDATE,
                execution_lease=execution_lease,
            )
            current = await self.store.get_run(principal, run_id)
            if current.lifecycle_state != RunLifecycle.RUNNING:
                raise asyncio.CancelledError
            if not result.publishable:
                current = await self._transition(
                    principal,
                    current,
                    phase="validation",
                    execution_lease=execution_lease,
                    event_type="artifact.candidate_updated",
                    data={
                        "artifact_id": artifact.artifact_id,
                        "artifact_version": artifact.version,
                        "artifact_type": artifact.artifact_type,
                        "schema_version": artifact.schema_version,
                        "status": ArtifactStatus.CANDIDATE.value,
                    },
                )
                await self._transition(
                    principal,
                    current,
                    lifecycle_state=RunLifecycle.FAILED,
                    phase="validation",
                    error_code="VALIDATION_BLOCKED",
                    execution_lease=execution_lease,
                    event_type="run.failed",
                    data={
                        "lifecycle_state": RunLifecycle.FAILED.value,
                        "error_code": "VALIDATION_BLOCKED",
                    },
                )
                return
            current = await self._transition(
                principal,
                current,
                phase="published",
                artifact=artifact,
                execution_lease=execution_lease,
                event_type="artifact.published",
                data={
                    "artifact_id": artifact.artifact_id,
                    "artifact_version": artifact.version,
                    "artifact_type": artifact.artifact_type,
                    "status": ArtifactStatus.PUBLISHED.value,
                },
            )
            await self._transition(
                principal,
                current,
                lifecycle_state=RunLifecycle.COMPLETED,
                phase="completed",
                execution_lease=execution_lease,
                event_type="run.completed",
                data={
                    "lifecycle_state": RunLifecycle.COMPLETED.value,
                    "artifact_id": artifact.artifact_id,
                    "artifact_version": artifact.version,
                    "artifact_type": artifact.artifact_type,
                    "schema_version": artifact.schema_version,
                },
            )
        except asyncio.CancelledError:
            if execution_lease is None:
                await self._finish_canceled(principal, run_id)
            else:
                current = await self.store.get_run(principal, run_id)
                if current.lifecycle_state == RunLifecycle.CANCEL_REQUESTED:
                    await self._finish_canceled(principal, run_id)
                    return
                if current.lifecycle_state in TERMINAL_RUN_STATES:
                    return
                raise
        except RunExecutionLeaseLost:
            raise
        except VersionConflict:
            current = await self.store.get_run(principal, run_id)
            if current.lifecycle_state == RunLifecycle.CANCEL_REQUESTED:
                await self._finish_canceled(principal, run_id)
        except Exception:
            logger.exception("V1 run execution failed", extra={"run_id": run_id})
            await self._finish_failed(
                principal,
                run_id,
                error_code="RUN_EXECUTION_FAILED",
                execution_lease=execution_lease,
            )

    async def _finish_canceled(self, principal: Principal, run_id: str) -> None:
        current = await self.store.get_run(principal, run_id)
        if current.lifecycle_state in TERMINAL_RUN_STATES:
            return
        try:
            await self._transition(
                principal,
                current,
                lifecycle_state=RunLifecycle.CANCELED,
                phase="canceled",
                event_type="run.canceled",
                data={"lifecycle_state": RunLifecycle.CANCELED.value},
            )
        except VersionConflict:
            return

    async def _finish_failed(
        self,
        principal: Principal,
        run_id: str,
        *,
        error_code: str,
        execution_lease: RunExecutionLease | None = None,
    ) -> None:
        current = await self.store.get_run(principal, run_id)
        if current.lifecycle_state in TERMINAL_RUN_STATES | {RunLifecycle.CANCEL_REQUESTED}:
            if current.lifecycle_state == RunLifecycle.CANCEL_REQUESTED:
                await self._finish_canceled(principal, run_id)
            return
        try:
            await self._transition(
                principal,
                current,
                lifecycle_state=RunLifecycle.FAILED,
                phase="failed",
                error_code=error_code,
                execution_lease=execution_lease,
                event_type="run.failed",
                data={
                    "lifecycle_state": RunLifecycle.FAILED.value,
                    "error_code": error_code,
                },
            )
        except (VersionConflict, RunExecutionLeaseLost):
            return

    async def cancel(
        self,
        principal: Principal,
        run_id: str,
        *,
        expected_control_version: int,
    ) -> RunView:
        current = await self.store.get_run(principal, run_id)
        if current.lifecycle_state in TERMINAL_RUN_STATES:
            return current
        if current.lifecycle_state == RunLifecycle.CANCEL_REQUESTED:
            updated = current
        else:
            updated = await self._transition(
                principal,
                current.model_copy(update={"control_version": expected_control_version}),
                lifecycle_state=RunLifecycle.CANCEL_REQUESTED,
                phase="canceling",
                event_type="run.lifecycle_changed",
                data={
                    "lifecycle_state": RunLifecycle.CANCEL_REQUESTED.value,
                    "reason": "user_requested",
                },
            )
        callback_error: Exception | None = None
        task: asyncio.Task[None] | None = None
        try:
            if self._cancel_run_tasks is not None:
                await self._cancel_run_tasks(principal, run_id)
        except Exception as exc:
            # The Product Run stays cancel_requested so an idempotent retry can
            # finish durable A2A propagation instead of falsely reporting a
            # fully canceled graph.
            callback_error = exc
        finally:
            # Request cancellation is a BaseException on modern asyncio. Once
            # cancel_requested is durable, local Product execution must still
            # stop even if the HTTP caller disconnects during A2A propagation.
            async with self._task_guard:
                task = self._tasks.get(run_id)
            if task is not None:
                task.cancel()
        if task is None and callback_error is None:
            await self._finish_canceled(principal, run_id)
        if callback_error is not None:
            raise callback_error
        return updated


@dataclass(slots=True)
class V1Runtime:
    """Dependencies shared by V1 routes."""

    store: PlatformStore
    coordinator: RunCoordinator
    a2a_runtime: Any | None = None
    knowledge_service: Any | None = None
    provider_gateway: Any | None = None
    share_service: Any | None = None

    async def close(self) -> None:
        """Release optional durable-store resources."""

        await self.coordinator.close()
        if self.a2a_runtime is not None:
            await self.a2a_runtime.task_service.shutdown()
        if self.knowledge_service is not None:
            await self.knowledge_service.close()
        if self.provider_gateway is not None:
            await self.provider_gateway.close()
        close = getattr(self.store, "close", None)
        if close is not None:
            await close()


def build_default_v1_runtime() -> V1Runtime:
    """Build a durable production runtime or an explicit local reference runtime."""

    database_url = os.getenv("ROUTEPILOT_V1_DATABASE_URL", "").strip()
    environment = os.getenv("ENVIRONMENT", "dev").strip().lower()
    if database_url:
        from .postgres_store import PostgresPlatformStore

        store: PlatformStore = PostgresPlatformStore.from_database_url(database_url)
    elif environment in {"production", "prod", "staging"}:
        raise RuntimeError("ROUTEPILOT_V1_DATABASE_URL is required outside local/test environments")
    else:
        store = InMemoryPlatformStore()
    execution_mode = (
        os.getenv(
            "ROUTEPILOT_V1_EXECUTION_MODE",
            "external" if database_url else "inline",
        )
        .strip()
        .lower()
    )
    if execution_mode not in {"inline", "external"}:
        raise RuntimeError("ROUTEPILOT_V1_EXECUTION_MODE must be inline or external")
    if execution_mode == "inline" and environment in {"production", "prod", "staging"}:
        raise RuntimeError("production V1 Run execution must use the external worker")
    knowledge_service = None
    rag_database_url = os.getenv("ROUTEPILOT_RAG_DATABASE_URL", "").strip() or database_url
    if rag_database_url:
        from agent.travel_agent.rag import (
            KnowledgeService,
            PostgresKnowledgeRepository,
            build_embedding_provider_from_env,
        )

        knowledge_service = KnowledgeService(
            PostgresKnowledgeRepository.from_database_url(
                rag_database_url,
                embedding_provider=build_embedding_provider_from_env(),
            )
        )

    from agent.travel_agent.providers import build_default_provider_gateway
    from agent.travel_agent.runtime_v2 import (
        LocalA2AAgentMesh,
        ResilientGeocodeService,
        TripBriefFactory,
        TravelOrchestratorV2,
        build_core_a2a_executors,
        build_research_directive_generator_from_env,
    )
    from agent.travel_agent.a2a.models import A2AActor
    from .a2a_routes import build_default_a2a_runtime

    provider_gateway = build_default_provider_gateway()
    a2a_runtime = build_default_a2a_runtime(
        executors=build_core_a2a_executors(
            knowledge=knowledge_service,
            providers=provider_gateway,
            directive_generator=build_research_directive_generator_from_env(),
        )
    )
    execution_profile = (
        os.getenv(
            "ROUTEPILOT_V1_EXECUTION_PROFILE",
            "v2_research_planning",
        )
        .strip()
        .lower()
    )
    if execution_profile != "v2_research_planning":
        raise RuntimeError("ROUTEPILOT_V1_EXECUTION_PROFILE must be v2_research_planning")
    executor: WholeRunExecutor = OrchestratedWholeRunExecutor(
        TravelOrchestratorV2(LocalA2AAgentMesh(a2a_runtime.task_service)),
        brief_factory=TripBriefFactory(ResilientGeocodeService(provider_gateway)),
    )

    async def cancel_a2a_tasks(principal: Principal, run_id: str) -> None:
        await a2a_runtime.task_service.cancel_run_tasks(
            A2AActor(
                tenant_id=principal.tenant_id,
                actor_id=principal.user_id,
                roles=principal.roles,
            ),
            run_id,
        )

    return V1Runtime(
        store=store,
        coordinator=RunCoordinator(
            store,
            executor,
            in_process_execution=execution_mode == "inline",
            cancel_run_tasks=cancel_a2a_tasks,
        ),
        a2a_runtime=a2a_runtime,
        knowledge_service=knowledge_service,
        provider_gateway=provider_gateway,
    )
