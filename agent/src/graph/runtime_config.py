"""Runtime configuration registry for agent graph execution."""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass

logger = logging.getLogger(__name__)

_SUPPORTED_STREAM_EVENT_VERSIONS = {"v1", "v2"}
_SUPPORTED_INTENT_STRUCTURED_METHODS = {"json_schema", "function_calling", "json_mode"}


@dataclass(frozen=True)
class AgentRuntimeConfig:
    stream_events_version: str
    intent_structured_methods: tuple[str, ...]
    default_max_parallelism: int
    default_tool_timeout_seconds: int
    default_tool_max_retries: int
    tool_cooldown_seconds: int
    circuit_breaker_threshold: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _parse_int_env(name: str, default: int, min_value: int = 0) -> int:
    raw = str(os.getenv(name, str(default))).strip()
    try:
        value = int(raw)
        if value < min_value:
            raise ValueError(f"value must be >= {min_value}")
        return value
    except Exception:
        logger.warning("Invalid %s=%s, fallback=%s", name, raw, default)
        return default


def _resolve_stream_events_version() -> str:
    raw = str(os.getenv("AGENT_STREAM_EVENTS_VERSION", "v1")).strip().lower()
    if raw in _SUPPORTED_STREAM_EVENT_VERSIONS:
        return raw
    logger.warning("Unsupported AGENT_STREAM_EVENTS_VERSION=%s, fallback=v1", raw)
    return "v1"


def _resolve_intent_structured_methods() -> tuple[str, ...]:
    preferred = str(os.getenv("AGENT_INTENT_STRUCTURED_METHOD", "json_schema")).strip().lower()
    fallback_order = [preferred, "json_schema", "function_calling", "json_mode"]
    methods: list[str] = []
    for method in fallback_order:
        if method not in _SUPPORTED_INTENT_STRUCTURED_METHODS:
            continue
        if method not in methods:
            methods.append(method)
    if not methods:
        methods = ["json_schema", "function_calling", "json_mode"]
    return tuple(methods)


def get_runtime_config() -> AgentRuntimeConfig:
    return AgentRuntimeConfig(
        stream_events_version=_resolve_stream_events_version(),
        intent_structured_methods=_resolve_intent_structured_methods(),
        default_max_parallelism=_parse_int_env("AGENT_MAX_PARALLELISM", default=2, min_value=1),
        default_tool_timeout_seconds=_parse_int_env("AGENT_TOOL_TIMEOUT_SECONDS", default=20, min_value=1),
        default_tool_max_retries=_parse_int_env("AGENT_TOOL_MAX_RETRIES", default=1, min_value=0),
        tool_cooldown_seconds=_parse_int_env("AGENT_TOOL_COOLDOWN_SECONDS", default=45, min_value=1),
        circuit_breaker_threshold=_parse_int_env("AGENT_CIRCUIT_BREAKER_THRESHOLD", default=3, min_value=1),
    )
