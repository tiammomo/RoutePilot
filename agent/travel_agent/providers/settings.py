"""Typed, server-only Provider Gateway configuration."""

from __future__ import annotations

import os

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator

KNOWN_PROVIDER_IDS = frozenset({"amap"})


class ProviderSettings(BaseModel):
    """Single canonical settings surface; secret repr/serialization is redacted."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    amap_web_key: SecretStr | None = None
    provider_allowlist: frozenset[str] = Field(default=KNOWN_PROVIDER_IDS)
    amap_http_timeout_seconds: float = Field(default=3.0, ge=0.1, le=15)

    @field_validator("provider_allowlist")
    @classmethod
    def validate_allowlist(cls, value: frozenset[str]) -> frozenset[str]:
        unknown = value - KNOWN_PROVIDER_IDS
        if unknown:
            raise ValueError("provider allowlist contains an unknown provider id")
        return value

    @classmethod
    def from_environment(cls) -> "ProviderSettings":
        """Read only canonical RoutePilot variables; deprecated key aliases are ignored."""

        raw_key = os.getenv("ROUTEPILOT_AMAP_WEB_KEY", "").strip()
        raw_allowlist = os.getenv(
            "ROUTEPILOT_PROVIDER_ALLOWLIST",
            "amap",
        )
        raw_timeout = os.getenv("ROUTEPILOT_AMAP_HTTP_TIMEOUT_SECONDS", "3.0")
        try:
            timeout = float(raw_timeout)
        except ValueError:
            raise ValueError(
                "ROUTEPILOT_AMAP_HTTP_TIMEOUT_SECONDS must be numeric"
            ) from None
        return cls(
            amap_web_key=SecretStr(raw_key) if raw_key else None,
            provider_allowlist=frozenset(
                item.strip() for item in raw_allowlist.split(",") if item.strip()
            ),
            amap_http_timeout_seconds=timeout,
        )


__all__ = ["KNOWN_PROVIDER_IDS", "ProviderSettings"]
