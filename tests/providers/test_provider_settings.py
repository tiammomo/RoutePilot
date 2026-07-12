"""Typed provider settings and canonical secret-name tests."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from agent.travel_agent.providers import ProviderSettings


def test_settings_ignore_deprecated_key_alias_and_redact_canonical_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("ROUTEPILOT_AMAP_WEB_KEY", raising=False)
    monkeypatch.delenv("ROUTEPILOT_PROVIDER_ALLOWLIST", raising=False)
    monkeypatch.setenv("AMAP_API_KEY", "deprecated-secret-must-be-ignored")
    unconfigured = ProviderSettings.from_environment()
    assert unconfigured.amap_web_key is None

    secret = "canonical-server-secret"
    monkeypatch.setenv("ROUTEPILOT_AMAP_WEB_KEY", secret)
    configured = ProviderSettings.from_environment()

    assert configured.amap_web_key is not None
    assert configured.amap_web_key.get_secret_value() == secret
    assert secret not in repr(configured)
    assert secret not in configured.model_dump_json()
    assert configured.provider_allowlist == frozenset({"amap"})


def test_settings_reject_unknown_allowlisted_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ROUTEPILOT_PROVIDER_ALLOWLIST", "amap,typo-provider")

    with pytest.raises(ValidationError, match="unknown provider id"):
        ProviderSettings.from_environment()
