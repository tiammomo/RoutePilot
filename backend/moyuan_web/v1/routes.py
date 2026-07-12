"""HTTP and resumable SSE adapters for the RoutePilot V1 API."""

from __future__ import annotations

import json
import re
from collections.abc import AsyncGenerator
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import Response, StreamingResponse

from .auth import require_principal
from .models import (
    ArtifactCommandRequest,
    ArtifactListResponse,
    ArtifactPatchRequest,
    ArtifactView,
    Principal,
    RunControlRequest,
    RunCreateRequest,
    RunResumeRequest,
    RunView,
    TERMINAL_RUN_STATES,
    TripCreateRequest,
    TripListResponse,
    TripMemberListResponse,
    TripMemberUpsertRequest,
    TripMemberView,
    TripPatchRequest,
    TripStatus,
    TripView,
    new_public_id,
    utc_now,
)
from .runtime import V1Runtime, build_default_v1_runtime
from .store import (
    ArtifactContentInvalid,
    ArtifactReadOnly,
    ArtifactTransitionConflict,
    IdempotencyConflict,
    ResourceForbidden,
    ResourceNotFound,
    RunInputExpired,
    RunInputInvalid,
    StoreError,
    VersionConflict,
    canonical_request_hash,
)

router = APIRouter(prefix="/v1")
PrincipalDep = Annotated[Principal, Depends(require_principal)]


def get_runtime(request: Request) -> V1Runtime:
    """Resolve the app-scoped V1 runtime."""

    runtime = getattr(request.app.state, "routepilot_v1_runtime", None)
    if runtime is None:
        runtime = build_default_v1_runtime()
        request.app.state.routepilot_v1_runtime = runtime
        if runtime.a2a_runtime is not None:
            request.app.state.routepilot_v1_a2a_runtime = runtime.a2a_runtime
        if runtime.knowledge_service is not None:
            request.app.state.routepilot_knowledge_service = runtime.knowledge_service
    return runtime


RuntimeDep = Annotated[V1Runtime, Depends(get_runtime)]


def _raise_store_error(exc: StoreError) -> NoReturn:
    if isinstance(exc, ResourceNotFound):
        code, http_status = "RESOURCE_NOT_FOUND", status.HTTP_404_NOT_FOUND
    elif isinstance(exc, ResourceForbidden):
        code, http_status = "ACTION_FORBIDDEN", status.HTTP_403_FORBIDDEN
    elif isinstance(exc, ArtifactReadOnly):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ARTIFACT_READ_ONLY",
                "message": "This Artifact type does not support versioned editing.",
                "retryable": False,
                "current_version": exc.current_version,
            },
        ) from exc
    elif isinstance(exc, ArtifactContentInvalid):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={
                "code": "ARTIFACT_CONTENT_INVALID",
                "message": "Artifact content does not satisfy its registered contract.",
                "retryable": False,
                "current_version": exc.current_version,
            },
        ) from exc
    elif isinstance(exc, ArtifactTransitionConflict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "ARTIFACT_TRANSITION_CONFLICT",
                "message": "The Artifact command is not valid from its current status.",
                "retryable": False,
                "current_version": exc.current_version,
                "current_status": exc.current_status.value,
            },
        ) from exc
    elif isinstance(exc, VersionConflict):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "VERSION_CONFLICT",
                "message": "The resource changed; refresh and retry.",
                "retryable": True,
                "current_version": exc.current_version,
            },
        ) from exc
    elif isinstance(exc, IdempotencyConflict):
        code, http_status = "IDEMPOTENCY_CONFLICT", status.HTTP_409_CONFLICT
    elif isinstance(exc, RunInputExpired):
        code, http_status = "RUN_INPUT_EXPIRED", status.HTTP_410_GONE
    elif isinstance(exc, RunInputInvalid):
        code, http_status = "RUN_INPUT_INVALID", status.HTTP_409_CONFLICT
    else:
        code, http_status = "STORE_ERROR", status.HTTP_500_INTERNAL_SERVER_ERROR
    if isinstance(exc, RunInputExpired):
        public_message = "The pending input expired; start a new planning Run."
    elif isinstance(exc, RunInputInvalid):
        public_message = "The submitted values do not match the pending input request."
    elif isinstance(exc, (ResourceNotFound, ResourceForbidden, IdempotencyConflict)):
        public_message = str(exc)
    else:
        public_message = "The storage operation could not be completed."
    raise HTTPException(
        status_code=http_status,
        detail={"code": code, "message": public_message, "retryable": False},
    ) from exc


@router.post("/trips", response_model=TripView, status_code=status.HTTP_201_CREATED)
async def create_trip(
    payload: TripCreateRequest,
    principal: PrincipalDep,
    runtime: RuntimeDep,
) -> TripView:
    """Create an authenticated user-owned Trip."""

    return await runtime.store.create_trip(principal, payload)


@router.get("/trips", response_model=TripListResponse)
async def list_trips(principal: PrincipalDep, runtime: RuntimeDep) -> TripListResponse:
    """List Trips scoped to the authenticated actor."""

    return TripListResponse(items=await runtime.store.list_trips(principal))


@router.get("/trips/{trip_id}", response_model=TripView)
async def get_trip(trip_id: str, principal: PrincipalDep, runtime: RuntimeDep) -> TripView:
    """Read one tenant-scoped Trip."""

    try:
        return await runtime.store.get_trip(principal, trip_id)
    except StoreError as exc:
        _raise_store_error(exc)


@router.post("/runs/{run_id}/resume", response_model=RunView, status_code=status.HTTP_202_ACCEPTED)
async def resume_run(
    run_id: str,
    payload: RunResumeRequest,
    principal: PrincipalDep,
    runtime: RuntimeDep,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ],
) -> RunView:
    """Validate typed input and re-dispatch a waiting Product Run."""

    try:
        result = await runtime.coordinator.resume(
            principal,
            run_id,
            payload,
            idempotency_key=idempotency_key,
        )
        return result.run
    except StoreError as exc:
        _raise_store_error(exc)


@router.patch("/trips/{trip_id}", response_model=TripView)
async def patch_trip(
    trip_id: str,
    payload: TripPatchRequest,
    principal: PrincipalDep,
    runtime: RuntimeDep,
) -> TripView:
    """Patch Trip metadata."""

    try:
        return await runtime.store.patch_trip(principal, trip_id, payload)
    except StoreError as exc:
        _raise_store_error(exc)


@router.post("/trips/{trip_id}/archive", response_model=TripView)
async def archive_trip(trip_id: str, principal: PrincipalDep, runtime: RuntimeDep) -> TripView:
    """Archive a Trip without deleting history."""

    try:
        return await runtime.store.set_trip_status(principal, trip_id, TripStatus.ARCHIVED)
    except StoreError as exc:
        _raise_store_error(exc)


@router.post("/trips/{trip_id}/restore", response_model=TripView)
async def restore_trip(trip_id: str, principal: PrincipalDep, runtime: RuntimeDep) -> TripView:
    """Restore an archived Trip."""

    try:
        return await runtime.store.set_trip_status(principal, trip_id, TripStatus.ACTIVE)
    except StoreError as exc:
        _raise_store_error(exc)


@router.get("/trips/{trip_id}/members", response_model=TripMemberListResponse)
async def list_trip_members(
    trip_id: str,
    principal: PrincipalDep,
    runtime: RuntimeDep,
) -> TripMemberListResponse:
    """List explicit Trip-scoped authorization grants."""

    try:
        return TripMemberListResponse(
            items=await runtime.store.list_trip_members(principal, trip_id)
        )
    except StoreError as exc:
        _raise_store_error(exc)


@router.put("/trips/{trip_id}/members/{user_id}", response_model=TripMemberView)
async def upsert_trip_member(
    trip_id: str,
    user_id: str,
    payload: TripMemberUpsertRequest,
    principal: PrincipalDep,
    runtime: RuntimeDep,
) -> TripMemberView:
    """Grant viewer/editor access; only owner or tenant admin may manage grants."""

    try:
        return await runtime.store.upsert_trip_member(
            principal,
            trip_id,
            user_id,
            payload,
        )
    except StoreError as exc:
        _raise_store_error(exc)


@router.delete(
    "/trips/{trip_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def remove_trip_member(
    trip_id: str,
    user_id: str,
    principal: PrincipalDep,
    runtime: RuntimeDep,
) -> Response:
    """Revoke a non-owner Trip membership."""

    try:
        await runtime.store.remove_trip_member(principal, trip_id, user_id)
    except StoreError as exc:
        _raise_store_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/trips/{trip_id}/runs", response_model=RunView, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    trip_id: str,
    payload: RunCreateRequest,
    request: Request,
    principal: PrincipalDep,
    runtime: RuntimeDep,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
) -> RunView:
    """Create an asynchronous idempotent Product Run."""

    candidate_trace_id = str(getattr(request.state, "trace_id", "") or "")
    trace_id = (
        candidate_trace_id
        if re.fullmatch(r"[a-z][a-z0-9_:-]{2,95}", candidate_trace_id)
        else new_public_id("trace")
    )
    try:
        result = await runtime.coordinator.submit(
            principal,
            trip_id,
            payload,
            idempotency_key=idempotency_key,
            trace_id=trace_id,
        )
        return result.run
    except StoreError as exc:
        _raise_store_error(exc)


@router.get("/runs/{run_id}", response_model=RunView)
async def get_run(run_id: str, principal: PrincipalDep, runtime: RuntimeDep) -> RunView:
    """Return the current Product Run snapshot."""

    try:
        return await runtime.store.get_run(principal, run_id)
    except StoreError as exc:
        _raise_store_error(exc)


@router.post("/runs/{run_id}/cancel", response_model=RunView)
async def cancel_run(
    run_id: str,
    payload: RunControlRequest,
    principal: PrincipalDep,
    runtime: RuntimeDep,
    _idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=200)],
) -> RunView:
    """CAS-request cancellation and fence late execution results."""

    try:
        return await runtime.coordinator.cancel(
            principal,
            run_id,
            expected_control_version=payload.expected_control_version,
        )
    except StoreError as exc:
        _raise_store_error(exc)


@router.get("/trips/{trip_id}/artifacts", response_model=ArtifactListResponse)
async def list_artifacts(
    trip_id: str,
    principal: PrincipalDep,
    runtime: RuntimeDep,
) -> ArtifactListResponse:
    """List immutable Artifact versions for a Trip."""

    try:
        return ArtifactListResponse(items=await runtime.store.list_artifacts(principal, trip_id))
    except StoreError as exc:
        _raise_store_error(exc)


@router.get("/artifacts/{artifact_id}", response_model=ArtifactView)
async def get_artifact(
    artifact_id: str,
    principal: PrincipalDep,
    runtime: RuntimeDep,
    version: Annotated[int | None, Query(ge=1)] = None,
) -> ArtifactView:
    """Read the latest or one explicitly pinned immutable Artifact version."""

    try:
        return await runtime.store.get_artifact(
            principal,
            artifact_id,
            version=version,
        )
    except StoreError as exc:
        _raise_store_error(exc)


@router.patch("/artifacts/{artifact_id}", response_model=ArtifactView)
async def patch_artifact(
    artifact_id: str,
    payload: ArtifactPatchRequest,
    principal: PrincipalDep,
    runtime: RuntimeDep,
) -> ArtifactView:
    """Create a new candidate version without rewriting prior content."""

    try:
        return await runtime.store.patch_artifact(principal, artifact_id, payload)
    except StoreError as exc:
        _raise_store_error(exc)


@router.post("/artifacts/{artifact_id}/commands", response_model=ArtifactView)
async def command_artifact(
    artifact_id: str,
    payload: ArtifactCommandRequest,
    principal: PrincipalDep,
    runtime: RuntimeDep,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ],
) -> ArtifactView:
    """Apply an idempotent CAS lifecycle command to the latest version."""

    request_hash = canonical_request_hash(
        {
            "artifact_id": artifact_id,
            "command": payload.model_dump(mode="json"),
        }
    )
    try:
        result = await runtime.store.command_artifact(
            principal,
            artifact_id,
            payload,
            idempotency_key=idempotency_key,
            request_hash=request_hash,
        )
        return result.artifact
    except StoreError as exc:
        _raise_store_error(exc)


def _parse_event_cursor(last_event_id: str | None, after_seq: int) -> int:
    candidates = [max(0, after_seq)]
    if last_event_id:
        try:
            candidates.append(max(0, int(last_event_id)))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "INVALID_EVENT_CURSOR",
                    "message": "Last-Event-ID must be an integer sequence.",
                    "retryable": False,
                },
            ) from exc
    return max(candidates)


def _serialize_event(event: Any) -> str:
    payload = event.model_dump(mode="json")
    return (
        f"id: {event.seq}\n"
        f"event: {event.type}\n"
        f"data: {json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}\n\n"
    )


async def _stream_events(
    request: Request,
    runtime: V1Runtime,
    principal: Principal,
    run_id: str,
    *,
    after_seq: int,
) -> AsyncGenerator[str, None]:
    cursor = after_seq
    while True:
        if await request.is_disconnected():
            return

        refreshed = await require_principal(request)
        if (
            refreshed.tenant_id != principal.tenant_id
            or refreshed.user_id != principal.user_id
            or refreshed.authorization_epoch != principal.authorization_epoch
        ):
            return

        events = await runtime.store.list_events(refreshed, run_id, after_seq=cursor)
        for event in events:
            cursor = event.seq
            yield _serialize_event(event)

        run = await runtime.store.get_run(refreshed, run_id)
        if run.lifecycle_state in TERMINAL_RUN_STATES and not events:
            return

        available = await runtime.store.wait_for_events(
            refreshed,
            run_id,
            after_seq=cursor,
            timeout_seconds=15.0,
        )
        if not available:
            yield f": heartbeat {utc_now().isoformat()}\n\n"


@router.get("/runs/{run_id}/events")
async def stream_run_events(
    run_id: str,
    request: Request,
    principal: PrincipalDep,
    runtime: RuntimeDep,
    after_seq: Annotated[int, Query(ge=0)] = 0,
    last_event_id: Annotated[str | None, Header(alias="Last-Event-ID")] = None,
) -> StreamingResponse:
    """Stream browser-safe events with replay and heartbeat."""

    cursor = _parse_event_cursor(last_event_id, after_seq)
    try:
        await runtime.store.get_run(principal, run_id)
    except StoreError as exc:
        _raise_store_error(exc)
    return StreamingResponse(
        _stream_events(request, runtime, principal, run_id, after_seq=cursor),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store, no-transform",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )
