"""Health check routes."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.responses import Response
from starlette.status import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE

from ..api.schemas.health import (
    HealthResponse,
    LLMHealthResponse,
    ReadinessResponse,
    SimpleStatusResponse,
    ToolHealthResponse,
    ToolIntentHealthResponse,
)
from ..app_meta import APP_VERSION, build_metadata
from ..observability import metrics_response_payload
from ..config.runtime import get_server_config
from .service_resolver import get_chat_service

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Return API health plus dependency initialization states."""
    chat_status = await get_chat_service().health_status()

    return HealthResponse(
        status="healthy",
        version=APP_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        build=build_metadata(),
        services={
            "api": "healthy",
            "llm": "initialized" if chat_status.get("initialized") else "not initialized",
            "sessions": "healthy",
        },
    )


@router.get("/health/llm", response_model=LLMHealthResponse)
async def llm_health_check():
    """Return LLM adapter and tool readiness details."""
    chat_status = await get_chat_service().health_status()
    return LLMHealthResponse(
        status="ok" if chat_status.get("initialized") else "not initialized",
        llm_adapter=chat_status.get("llm_adapter", False),
        tools_count=chat_status.get("tools_count", 0),
        memory_enabled=chat_status.get("memory_enabled", False),
    )


@router.get("/health/tools", response_model=ToolHealthResponse)
async def tools_health_check():
    """Return tool diagnostics and aggregated SLO metrics."""
    status = await get_chat_service().tools_health_status()
    return ToolHealthResponse(**status)


@router.get("/health/tools/intents", response_model=ToolIntentHealthResponse)
async def tools_intents_health_check():
    """Return per-intent request metrics for the monitoring window."""
    status = await get_chat_service().tools_intents_health_status()
    return ToolIntentHealthResponse(**status)


@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check(request: Request):
    """Kubernetes readiness probe endpoint backed by real startup validation state."""
    snapshot = getattr(
        request.app.state,
        "readiness_snapshot",
        {"status": "starting", "validated_at": None, "checks": {}},
    )
    status_code = HTTP_200_OK if snapshot.get("status") == "ready" else HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(
        content=ReadinessResponse(**snapshot).model_dump(),
        status_code=status_code,
    )


@router.get("/live", response_model=SimpleStatusResponse)
async def liveness_check():
    """Kubernetes liveness probe endpoint."""
    return SimpleStatusResponse(status="alive")


@router.get("/metrics", include_in_schema=False)
async def metrics_endpoint():
    """Expose Prometheus metrics for web/API health and SSE activity."""
    try:
        if not get_server_config().metrics_enabled:
            raise HTTPException(status_code=404, detail="Metrics endpoint is disabled")
    except HTTPException:
        raise
    except Exception:
        pass
    payload, content_type = metrics_response_payload()
    return Response(content=payload, media_type=content_type)
