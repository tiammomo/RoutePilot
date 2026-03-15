"""Health check routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse
from starlette.responses import Response
from starlette.status import HTTP_200_OK, HTTP_503_SERVICE_UNAVAILABLE

from ..app_meta import APP_VERSION, build_metadata
from ..dependencies.container import get_container
from ..observability import metrics_response_payload
from ..config.runtime import get_server_config
from ..services.chat_service import ChatService

router = APIRouter()


class HealthResponse(BaseModel):
    """System-level health payload used by `/health`."""

    status: str
    version: str
    timestamp: str
    build: dict[str, object]
    services: dict[str, str]


class LLMHealthResponse(BaseModel):
    """LLM runtime and tool initialization status snapshot."""

    status: Literal["ok", "not initialized"]
    llm_adapter: bool
    tools_count: int
    memory_enabled: bool


class SimpleStatusResponse(BaseModel):
    """Simple OK-style response for liveness/readiness probes."""

    status: str


class ReadinessCheckResponse(BaseModel):
    """Per-check readiness detail returned by `/ready`."""

    name: str
    status: Literal["ok", "not_ready"]
    message: str
    details: dict[str, object] = {}


class ReadinessResponse(BaseModel):
    """Aggregated readiness response with detailed startup validation checks."""

    status: Literal["ready", "not_ready", "starting"]
    validated_at: str | None
    checks: dict[str, ReadinessCheckResponse]


class ToolHealthResponse(BaseModel):
    """Aggregated tool subsystem health diagnostics."""

    status: Literal["ok", "not initialized"]
    initialized: bool
    configured_tools_count: int
    circuit_open_count: int
    slo: dict[str, object]
    intent_aggregate: dict[str, dict[str, object]]
    window_minutes: int
    diagnostics: dict[str, object]


class ToolIntentHealthResponse(BaseModel):
    """Intent-level request SLO snapshot over the rolling health window."""

    status: Literal["ok", "not initialized"]
    window_minutes: int
    total_requests: int
    intent_aggregate: dict[str, dict[str, object]]


def _get_chat_service() -> ChatService:
    """Resolve ChatService through the dependency container."""
    return get_container().resolve("ChatService")


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Return API health plus dependency initialization states."""
    chat_status = await _get_chat_service().health_status()

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
    chat_status = await _get_chat_service().health_status()
    return LLMHealthResponse(
        status="ok" if chat_status.get("initialized") else "not initialized",
        llm_adapter=chat_status.get("llm_adapter", False),
        tools_count=chat_status.get("tools_count", 0),
        memory_enabled=chat_status.get("memory_enabled", False),
    )


@router.get("/health/tools", response_model=ToolHealthResponse)
async def tools_health_check():
    """Return tool diagnostics and aggregated SLO metrics."""
    status = await _get_chat_service().tools_health_status()
    return ToolHealthResponse(**status)


@router.get("/health/tools/intents", response_model=ToolIntentHealthResponse)
async def tools_intents_health_check():
    """Return per-intent request metrics for the monitoring window."""
    status = await _get_chat_service().tools_intents_health_status()
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
