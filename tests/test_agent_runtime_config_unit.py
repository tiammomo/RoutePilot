from __future__ import annotations

from agent.src.graph.builder import get_tool_health_diagnostics
from agent.src.graph.runtime_config import get_runtime_config


def test_runtime_config_parses_env_values(monkeypatch):
    monkeypatch.setenv("AGENT_RELIABILITY_CONTROLS_ENABLED", "false")
    monkeypatch.setenv("AGENT_TIMELINESS_CONTROLS_ENABLED", "true")
    monkeypatch.setenv("AGENT_SECURITY_CONTROLS_ENABLED", "true")
    monkeypatch.setenv("AGENT_COST_CONTROLS_ENABLED", "false")
    monkeypatch.setenv("AGENT_STREAM_EVENTS_VERSION", "v2")
    monkeypatch.setenv("AGENT_INTENT_STRUCTURED_METHOD", "function_calling")
    monkeypatch.setenv("AGENT_MAX_PARALLELISM", "4")
    monkeypatch.setenv("AGENT_TOOL_TIMEOUT_SECONDS", "30")
    monkeypatch.setenv("AGENT_TOOL_MAX_RETRIES", "3")
    monkeypatch.setenv("AGENT_TOOL_COOLDOWN_SECONDS", "55")
    monkeypatch.setenv("AGENT_CIRCUIT_BREAKER_THRESHOLD", "5")
    monkeypatch.setenv("AGENT_MAX_PLAN_STEPS", "9")
    monkeypatch.setenv("AGENT_MAX_EXECUTION_ROUNDS", "12")
    monkeypatch.setenv("AGENT_EARLY_STOP_CONFIDENCE", "0.95")
    monkeypatch.setenv("AGENT_ROUND_MAX_TOOLS", "6")
    monkeypatch.setenv("AGENT_ROUND_MAX_ELAPSED_MS", "20000")
    monkeypatch.setenv("AGENT_ROUND_MAX_TOKENS", "3200")

    cfg = get_runtime_config()
    assert cfg.reliability_controls_enabled is False
    assert cfg.timeliness_controls_enabled is True
    assert cfg.security_controls_enabled is True
    assert cfg.cost_controls_enabled is False
    assert cfg.stream_events_version == "v2"
    assert cfg.intent_structured_methods[0] == "function_calling"
    assert cfg.default_max_parallelism == 4
    assert cfg.default_tool_timeout_seconds == 30
    assert cfg.default_tool_max_retries == 3
    assert cfg.tool_cooldown_seconds == 55
    assert cfg.circuit_breaker_threshold == 5
    assert cfg.max_plan_steps == 9
    assert cfg.max_execution_rounds == 12
    assert cfg.early_stop_confidence_threshold == 0.95
    assert cfg.round_max_tools == 6
    assert cfg.round_max_elapsed_ms == 20000
    assert cfg.round_max_tokens == 3200


def test_runtime_config_invalid_values_fallback(monkeypatch):
    monkeypatch.setenv("AGENT_RELIABILITY_CONTROLS_ENABLED", "invalid")
    monkeypatch.setenv("AGENT_TIMELINESS_CONTROLS_ENABLED", "invalid")
    monkeypatch.setenv("AGENT_SECURITY_CONTROLS_ENABLED", "invalid")
    monkeypatch.setenv("AGENT_COST_CONTROLS_ENABLED", "invalid")
    monkeypatch.setenv("AGENT_STREAM_EVENTS_VERSION", "bad")
    monkeypatch.setenv("AGENT_MAX_PARALLELISM", "0")
    monkeypatch.setenv("AGENT_TOOL_TIMEOUT_SECONDS", "-1")
    monkeypatch.setenv("AGENT_TOOL_MAX_RETRIES", "-9")
    monkeypatch.setenv("AGENT_TOOL_COOLDOWN_SECONDS", "0")
    monkeypatch.setenv("AGENT_CIRCUIT_BREAKER_THRESHOLD", "0")
    cfg = get_runtime_config()

    assert cfg.reliability_controls_enabled is True
    assert cfg.timeliness_controls_enabled is True
    assert cfg.security_controls_enabled is True
    assert cfg.cost_controls_enabled is True
    assert cfg.stream_events_version == "v1"
    assert cfg.default_max_parallelism == 2
    assert cfg.default_tool_timeout_seconds == 20
    assert cfg.default_tool_max_retries == 1
    assert cfg.tool_cooldown_seconds == 45
    assert cfg.circuit_breaker_threshold == 3
    assert cfg.max_plan_steps == 6
    assert cfg.max_execution_rounds == 8
    assert cfg.round_max_tools == 4
    assert cfg.round_max_elapsed_ms == 15000
    assert cfg.round_max_tokens == 2500


def test_tool_health_diagnostics_contains_runtime_config():
    diagnostics = get_tool_health_diagnostics()
    runtime = diagnostics.get("runtime_config", {})
    assert isinstance(runtime, dict)
    assert "stream_events_version" in runtime
    assert "default_max_parallelism" in runtime
