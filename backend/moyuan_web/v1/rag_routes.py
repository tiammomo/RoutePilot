"""Authenticated V1 knowledge administration and retrieval endpoints."""

from __future__ import annotations

import os
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status

from agent.travel_agent.rag import (
    AuthorizedKnowledgeContext,
    IngestDocumentRequest,
    IngestResult,
    IngestionStatus,
    KnowledgeAuthorizationError,
    KnowledgeConflictError,
    KnowledgeError,
    KnowledgeDocumentAdminView,
    KnowledgeDocumentPage,
    KnowledgeDocumentStatusCommand,
    KnowledgeDocumentStatusResult,
    KnowledgeNotFoundError,
    KnowledgeService,
    PostgresKnowledgeRepository,
    ResearchQuery,
    RetrievalResult,
    VisibilityScope,
    KnowledgeVersionConflictError,
)

from .auth import require_principal
from .models import Principal

router = APIRouter(prefix="/knowledge", tags=["v1-knowledge"])
PrincipalDep = Annotated[Principal, Depends(require_principal)]


def _to_context(principal: Principal) -> AuthorizedKnowledgeContext:
    """Convert only server-authenticated identity into an agent-layer context."""

    return AuthorizedKnowledgeContext(
        tenant_id=principal.tenant_id,
        actor_id=principal.user_id,
        roles=principal.roles,
        authorization_epoch=principal.authorization_epoch,
    )


async def get_knowledge_service(request: Request) -> KnowledgeService:
    """Resolve an injected service or a configured PostgreSQL lexical service."""

    service = getattr(request.app.state, "routepilot_knowledge_service", None)
    if service is None:
        product_runtime = getattr(request.app.state, "routepilot_v1_runtime", None)
        if product_runtime is not None:
            service = product_runtime.knowledge_service
    if service is not None:
        if not isinstance(service, KnowledgeService):
            raise RuntimeError("routepilot_knowledge_service must be a KnowledgeService")
        return service

    database_url = (
        os.getenv("ROUTEPILOT_RAG_DATABASE_URL", "").strip()
        or os.getenv("ROUTEPILOT_V1_DATABASE_URL", "").strip()
    )
    if not database_url:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "code": "KNOWLEDGE_SERVICE_UNAVAILABLE",
                "message": "The knowledge repository is not configured.",
                "retryable": True,
            },
        )
    embedding_provider = getattr(request.app.state, "routepilot_embedding_provider", None)
    repository = PostgresKnowledgeRepository.from_database_url(
        database_url,
        embedding_provider=embedding_provider,
    )
    service = KnowledgeService(repository)
    request.app.state.routepilot_knowledge_service = service
    return service


KnowledgeServiceDep = Annotated[KnowledgeService, Depends(get_knowledge_service)]


def _raise_knowledge_error(exc: KnowledgeError) -> NoReturn:
    detail: dict[str, object]
    if isinstance(exc, KnowledgeVersionConflictError):
        code, http_status = "KNOWLEDGE_VERSION_CONFLICT", status.HTTP_409_CONFLICT
        detail = {
            "code": code,
            "message": str(exc),
            "retryable": False,
            "current_version": exc.current_version,
        }
    elif isinstance(exc, KnowledgeNotFoundError):
        code, http_status = "KNOWLEDGE_DOCUMENT_NOT_FOUND", status.HTTP_404_NOT_FOUND
        detail = {"code": code, "message": str(exc), "retryable": False}
    elif isinstance(exc, KnowledgeAuthorizationError):
        code, http_status = "KNOWLEDGE_ACTION_FORBIDDEN", status.HTTP_403_FORBIDDEN
        detail = {"code": code, "message": str(exc), "retryable": False}
    elif isinstance(exc, KnowledgeConflictError):
        code, http_status = "KNOWLEDGE_IDEMPOTENCY_CONFLICT", status.HTTP_409_CONFLICT
        detail = {"code": code, "message": str(exc), "retryable": False}
    else:
        code, http_status = "KNOWLEDGE_OPERATION_FAILED", status.HTTP_500_INTERNAL_SERVER_ERROR
        detail = {
            "code": code,
            "message": "The knowledge operation could not be completed.",
            "retryable": False,
        }
    raise HTTPException(
        status_code=http_status,
        detail=detail,
    ) from exc


def _require_knowledge_admin(context: AuthorizedKnowledgeContext) -> None:
    if not context.can_manage_tenant_knowledge:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "KNOWLEDGE_ADMIN_ROLE_REQUIRED",
                "message": "admin or tenant_admin role is required.",
                "retryable": False,
            },
        )


@router.post(
    "/documents:ingest",
    response_model=IngestResult,
    status_code=status.HTTP_201_CREATED,
)
async def ingest_document(
    payload: IngestDocumentRequest,
    principal: PrincipalDep,
    service: KnowledgeServiceDep,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ],
) -> IngestResult:
    """Ingest supplied text; this endpoint never fetches the source URI."""

    context = _to_context(principal)
    _require_knowledge_admin(context)
    if payload.visibility_scope is VisibilityScope.PUBLIC and not context.can_manage_public_knowledge:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "PUBLIC_KNOWLEDGE_ADMIN_REQUIRED",
                "message": "global admin role is required for public knowledge.",
                "retryable": False,
            },
        )
    try:
        return await service.ingest(
            context,
            payload,
            idempotency_key=idempotency_key,
        )
    except KnowledgeError as exc:
        _raise_knowledge_error(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_KNOWLEDGE_DOCUMENT",
                "message": str(exc),
                "retryable": False,
            },
        ) from exc


@router.get("/documents", response_model=KnowledgeDocumentPage)
async def list_documents(
    principal: PrincipalDep,
    service: KnowledgeServiceDep,
    document_status: Annotated[IngestionStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=4, max_length=96)] = None,
) -> KnowledgeDocumentPage:
    """List provenance metadata without returning stored evidence content."""

    context = _to_context(principal)
    _require_knowledge_admin(context)
    try:
        return await service.list_documents(
            context,
            status=document_status,
            limit=limit,
            cursor=cursor,
        )
    except KnowledgeError as exc:
        _raise_knowledge_error(exc)


@router.get("/documents/{document_id}", response_model=KnowledgeDocumentAdminView)
async def get_document(
    document_id: str,
    principal: PrincipalDep,
    service: KnowledgeServiceDep,
) -> KnowledgeDocumentAdminView:
    """Read one tenant-visible, content-free knowledge metadata record."""

    context = _to_context(principal)
    _require_knowledge_admin(context)
    try:
        return await service.get_document(context, document_id)
    except KnowledgeError as exc:
        _raise_knowledge_error(exc)


@router.post(
    "/documents/{document_id}/status",
    response_model=KnowledgeDocumentStatusResult,
)
async def change_document_status(
    document_id: str,
    payload: KnowledgeDocumentStatusCommand,
    principal: PrincipalDep,
    service: KnowledgeServiceDep,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=8, max_length=200),
    ],
) -> KnowledgeDocumentStatusResult:
    """Publish, quarantine, or tombstone using idempotency plus CAS."""

    context = _to_context(principal)
    _require_knowledge_admin(context)
    try:
        return await service.change_document_status(
            context,
            document_id,
            payload,
            idempotency_key=idempotency_key,
        )
    except KnowledgeError as exc:
        _raise_knowledge_error(exc)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "INVALID_KNOWLEDGE_STATUS_COMMAND",
                "message": str(exc),
                "retryable": False,
            },
        ) from exc


@router.post("/search", response_model=RetrievalResult)
async def search_knowledge(
    payload: ResearchQuery,
    principal: PrincipalDep,
    service: KnowledgeServiceDep,
) -> RetrievalResult:
    """Search public plus current-tenant evidence using server identity."""

    try:
        return await service.retrieve(_to_context(principal), payload)
    except KnowledgeError as exc:
        _raise_knowledge_error(exc)


__all__ = ["get_knowledge_service", "router"]
