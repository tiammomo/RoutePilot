"""Unit tests for FastAPI application bootstrap helpers."""

from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from moyuan_web.bootstrap_app import (  # noqa: E402
    DEFAULT_CORS_ORIGINS,
    build_root_payload,
    resolve_allowed_origins,
    should_register_metrics_alias,
)


def test_resolve_allowed_origins_prefers_env_override(monkeypatch):
    server_config = SimpleNamespace(cors_origins=["http://config.example"])
    monkeypatch.setenv("CORS_ORIGINS", "http://env-one.example,http://env-two.example")

    allowed = resolve_allowed_origins(server_config)

    assert allowed == ["http://env-one.example", "http://env-two.example"]


def test_resolve_allowed_origins_falls_back_to_config_then_defaults(monkeypatch):
    monkeypatch.delenv("CORS_ORIGINS", raising=False)

    config_allowed = resolve_allowed_origins(SimpleNamespace(cors_origins=["http://config.example"]))
    default_allowed = resolve_allowed_origins(None)

    assert config_allowed == ["http://config.example"]
    assert default_allowed == list(DEFAULT_CORS_ORIGINS)


def test_should_register_metrics_alias_only_for_custom_enabled_path():
    assert should_register_metrics_alias(SimpleNamespace(metrics_enabled=True, metrics_path="/internal/metrics")) is True
    assert should_register_metrics_alias(SimpleNamespace(metrics_enabled=True, metrics_path="/api/metrics")) is False
    assert should_register_metrics_alias(SimpleNamespace(metrics_enabled=False, metrics_path="/internal/metrics")) is False
    assert should_register_metrics_alias(None) is False


def test_build_root_payload_exposes_docs_and_build_metadata():
    payload = build_root_payload()

    assert payload["name"]
    assert payload["version"]
    assert payload["docs"] == "/docs"
    assert payload["rapidoc"] == "/rapidoc"
    assert payload["redoc"] == "/redoc"
    assert payload["openapi"] == "/openapi.json"
    assert isinstance(payload["build"], dict)
