"""Health and diagnostics endpoint schemas."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


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
    details: dict[str, object] = Field(default_factory=dict)


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
