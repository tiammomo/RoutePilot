"""Authenticated V1 knowledge administration and retrieval endpoints."""

from __future__ import annotations

import os
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from agent.travel_agent.rag import (
    AuthorizedKnowledgeContext,
    IngestDocumentRequest,
    IngestResult,
    KnowledgeAuthorizationError,
    KnowledgeConflictError,
    KnowledgeError,
    KnowledgeService,
    PostgresKnowledgeRepository,
    ResearchQuery,
    RetrievalResult,
    VisibilityScope,
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
    if isinstance(exc, KnowledgeAuthorizationError):
        code, http_status = "KNOWLEDGE_ACTION_FORBIDDEN", status.HTTP_403_FORBIDDEN
    elif isinstance(exc, KnowledgeConflictError):
        code, http_status = "KNOWLEDGE_IDEMPOTENCY_CONFLICT", status.HTTP_409_CONFLICT
    else:
        code, http_status = "KNOWLEDGE_OPERATION_FAILED", status.HTTP_500_INTERNAL_SERVER_ERROR
    message = (
        str(exc)
        if isinstance(exc, (KnowledgeAuthorizationError, KnowledgeConflictError))
        else "The knowledge operation could not be completed."
    )
    raise HTTPException(
        status_code=http_status,
        detail={"code": code, "message": message, "retryable": False},
    ) from exc


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
    if not context.can_manage_tenant_knowledge:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "KNOWLEDGE_ADMIN_ROLE_REQUIRED",
                "message": "admin or tenant_admin role is required.",
                "retryable": False,
            },
        )
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
