"""Health check routes."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from ..app_meta import APP_VERSION
from ..dependencies.container import get_container
from ..services.chat_service import ChatService

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    version: str
    timestamp: str
    services: dict[str, str]


class LLMHealthResponse(BaseModel):
    status: Literal["ok", "not initialized"]
    llm_adapter: bool
    tools_count: int
    memory_enabled: bool


class SimpleStatusResponse(BaseModel):
    status: str


class ToolHealthResponse(BaseModel):
    status: Literal["ok", "not initialized"]
    initialized: bool
    configured_tools_count: int
    circuit_open_count: int
    slo: dict[str, object]
    intent_aggregate: dict[str, dict[str, object]]
    window_minutes: int
    diagnostics: dict[str, object]


class ToolIntentHealthResponse(BaseModel):
    status: Literal["ok", "not initialized"]
    window_minutes: int
    total_requests: int
    intent_aggregate: dict[str, dict[str, object]]


def _get_chat_service() -> ChatService:
    return get_container().resolve("ChatService")


@router.get("/health", response_model=HealthResponse)
async def health_check():
    chat_status = await _get_chat_service().health_status()

    return HealthResponse(
        status="healthy",
        version=APP_VERSION,
        timestamp=datetime.now(timezone.utc).isoformat(),
        services={
            "api": "healthy",
            "llm": "initialized" if chat_status.get("initialized") else "not initialized",
            "sessions": "healthy",
        },
    )


@router.get("/health/llm", response_model=LLMHealthResponse)
async def llm_health_check():
    chat_status = await _get_chat_service().health_status()
    return LLMHealthResponse(
        status="ok" if chat_status.get("initialized") else "not initialized",
        llm_adapter=chat_status.get("llm_adapter", False),
        tools_count=chat_status.get("tools_count", 0),
        memory_enabled=chat_status.get("memory_enabled", False),
    )


@router.get("/health/tools", response_model=ToolHealthResponse)
async def tools_health_check():
    status = await _get_chat_service().tools_health_status()
    return ToolHealthResponse(**status)


@router.get("/health/tools/intents", response_model=ToolIntentHealthResponse)
async def tools_intents_health_check():
    status = await _get_chat_service().tools_intents_health_status()
    return ToolIntentHealthResponse(**status)


@router.get("/ready", response_model=SimpleStatusResponse)
async def readiness_check():
    return SimpleStatusResponse(status="ready")


@router.get("/live", response_model=SimpleStatusResponse)
async def liveness_check():
    return SimpleStatusResponse(status="alive")
