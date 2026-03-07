from __future__ import annotations

from agent.src.graph.builder import get_tool_health_diagnostics
from agent.src.graph.runtime_config import get_runtime_config


def test_runtime_config_parses_env_values(monkeypatch):
    monkeypatch.setenv("AGENT_STREAM_EVENTS_VERSION", "v2")
    monkeypatch.setenv("AGENT_INTENT_STRUCTURED_METHOD", "function_calling")
    monkeypatch.setenv("AGENT_MAX_PARALLELISM", "4")
    monkeypatch.setenv("AGENT_TOOL_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("AGENT_TOOL_MAX_RETRIES", "3")
    monkeypatch.setenv("AGENT_TOOL_COOLDOWN_SECONDS", "55")
    monkeypatch.setenv("AGENT_CIRCUIT_BREAKER_THRESHOLD", "5")

    cfg = get_runtime_config()
    assert cfg.stream_events_version == "v2"
    assert cfg.intent_structured_methods[0] == "function_calling"
    assert cfg.default_max_parallelism == 4
    assert cfg.default_tool_timeout_seconds == 30
    assert cfg.default_tool_max_retries == 3
    assert cfg.tool_cooldown_seconds == 55
    assert cfg.circuit_breaker_threshold == 5


def test_runtime_config_invalid_values_fallback(monkeypatch):
    monkeypatch.setenv("AGENT_STREAM_EVENTS_VERSION", "bad")
    monkeypatch.setenv("AGENT_MAX_PARALLELISM", "0")
    monkeypatch.setenv("AGENT_TOOL_TIMEOUT_SECONDS", "-1")
    monkeypatch.setenv("AGENT_TOOL_MAX_RETRIES", "-9")
    monkeypatch.setenv("AGENT_TOOL_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("AGENT_CIRCUIT_BREAKER_THRESHOLD", "0")
    cfg = get_runtime_config()

    assert cfg.stream_events_version == "v1"
    assert cfg.default_max_parallelism == 2
    assert cfg.default_tool_timeout_seconds == 20
    assert cfg.default_tool_max_retries == 1
    assert cfg.tool_cooldown_seconds == 45
    assert cfg.circuit_breaker_threshold == 3


def test_tool_health_diagnostics_contains_runtime_config():
    diagnostics = get_tool_health_diagnostics()
    runtime = diagnostics.get("runtime_config", {})
    assert isinstance(runtime, dict)
    assert "stream_events_version" in runtime
    assert "default_max_parallelism" in runtime
