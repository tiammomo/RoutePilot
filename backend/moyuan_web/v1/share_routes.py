"""Authenticated share management and capability-only public share exchange."""

from __future__ import annotations

from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status

from .auth import require_principal
from .models import Principal
from .routes import get_runtime
from .share_models import (
    PublicShareSnapshotResponse,
    ShareCreateRequest,
    ShareExchangeRequest,
    ShareExchangeResponse,
    ShareListResponse,
    ShareMutationResponse,
)
from .share_service import (
    ShareCapabilityInvalid,
    ShareConflict,
    ShareError,
    ShareNotFound,
    ShareRateLimited,
    ShareService,
)
from .store import ResourceForbidden, ResourceNotFound, StoreError

router = APIRouter(tags=["v1-shares"])
PrincipalDep = Annotated[Principal, Depends(require_principal)]


def get_share_service(request: Request) -> ShareService:
    """Resolve one app-scoped service using the same tenant store and engine."""

    service = getattr(request.app.state, "routepilot_share_service", None)
    if service is not None:
        if not isinstance(service, ShareService):
            raise RuntimeError("routepilot_share_service must be a ShareService")
        return service
    runtime = get_runtime(request)
    if runtime.share_service is None:
        runtime.share_service = ShareService(runtime.store)
    request.app.state.routepilot_share_service = runtime.share_service
    return runtime.share_service


ShareServiceDep = Annotated[ShareService, Depends(get_share_service)]


def _raise_share_error(exc: ShareError | StoreError) -> NoReturn:
    headers: dict[str, str] | None = None
    if isinstance(exc, (ShareNotFound, ResourceNotFound)):
        code, http_status, message = "SHARE_NOT_FOUND", 404, "Share not found."
    elif isinstance(exc, ResourceForbidden):
        code, http_status, message = "SHARE_ACTION_FORBIDDEN", 403, "Share action forbidden."
    elif isinstance(exc, ShareConflict):
        detail: dict[str, object] = {
            "code": "SHARE_VERSION_CONFLICT",
            "message": "The share changed; refresh and retry.",
            "retryable": True,
        }
        if exc.current_version is not None:
            detail["current_version"] = exc.current_version
        raise HTTPException(status_code=409, detail=detail) from exc
    elif isinstance(exc, ShareRateLimited):
        code, http_status, message = (
            "SHARE_EXCHANGE_RATE_LIMITED",
            429,
            "Share access is temporarily unavailable.",
        )
        headers = {"Retry-After": str(exc.retry_after_seconds)}
    elif isinstance(exc, ShareCapabilityInvalid):
        code, http_status, message = (
            "SHARE_ACCESS_INVALID",
            401,
            "Share access is invalid or expired.",
        )
    else:
        code, http_status, message = (
            "SHARE_OPERATION_FAILED",
            500,
            "The share operation could not be completed.",
        )
    raise HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message, "retryable": False},
        headers=headers,
    ) from exc


@router.post(
    "/trips/{trip_id}/shares",
    response_model=ShareMutationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_share(
    trip_id: str,
    payload: ShareCreateRequest,
    principal: PrincipalDep,
    service: ShareServiceDep,
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=200)
    ],
) -> ShareMutationResponse:
    try:
        return await service.create(
            principal,
            trip_id,
            payload,
            idempotency_key=idempotency_key,
        )
    except (ShareError, StoreError) as exc:
        _raise_share_error(exc)


@router.get("/trips/{trip_id}/shares", response_model=ShareListResponse)
async def list_shares(
    trip_id: str,
    principal: PrincipalDep,
    service: ShareServiceDep,
) -> ShareListResponse:
    try:
        return await service.list(principal, trip_id)
    except (ShareError, StoreError) as exc:
        _raise_share_error(exc)


@router.post("/shares/{share_id}/rotate", response_model=ShareMutationResponse)
async def rotate_share(
    share_id: str,
    principal: PrincipalDep,
    service: ShareServiceDep,
    expected_version: Annotated[int, Header(alias="If-Match", ge=1)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=200)
    ],
) -> ShareMutationResponse:
    try:
        return await service.rotate(
            principal,
            share_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
        )
    except (ShareError, StoreError) as exc:
        _raise_share_error(exc)


@router.post("/shares/{share_id}/revoke", response_model=ShareMutationResponse)
async def revoke_share(
    share_id: str,
    principal: PrincipalDep,
    service: ShareServiceDep,
    expected_version: Annotated[int, Header(alias="If-Match", ge=1)],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=200)
    ],
) -> ShareMutationResponse:
    try:
        return await service.revoke(
            principal,
            share_id,
            expected_version=expected_version,
            idempotency_key=idempotency_key,
        )
    except (ShareError, StoreError) as exc:
        _raise_share_error(exc)


@router.post(
    "/public/shares/{public_id}/exchange",
    response_model=ShareExchangeResponse,
)
async def exchange_share_capability(
    public_id: str,
    payload: ShareExchangeRequest,
    response: Response,
    service: ShareServiceDep,
) -> ShareExchangeResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    try:
        return await service.exchange(public_id, payload.secret)
    except (ShareError, StoreError) as exc:
        _raise_share_error(exc)


@router.get(
    "/public/shares/{public_id}/snapshot",
    response_model=PublicShareSnapshotResponse,
)
async def get_public_share_snapshot(
    public_id: str,
    response: Response,
    service: ShareServiceDep,
    session_token: Annotated[
        str,
        Header(alias="X-RoutePilot-Share-Session", min_length=32, max_length=128),
    ],
) -> PublicShareSnapshotResponse:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    try:
        return await service.public_snapshot(public_id, session_token)
    except (ShareError, StoreError) as exc:
        _raise_share_error(exc)


__all__ = ["get_share_service", "router"]
