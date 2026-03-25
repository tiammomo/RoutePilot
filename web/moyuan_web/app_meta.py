"""Application metadata shared across web routes, startup, and release workflows."""

from __future__ import annotations

import os
from typing import Any


APP_NAME = "moyuan-travel-agent API"
DEFAULT_APP_VERSION = "3.3.0"
APP_VERSION = str(os.getenv("APP_VERSION", DEFAULT_APP_VERSION)).strip() or DEFAULT_APP_VERSION
APP_BUILD_SHA = str(os.getenv("APP_BUILD_SHA", "local")).strip() or "local"
APP_BUILD_CREATED_AT = str(os.getenv("APP_BUILD_CREATED_AT", "")).strip()


def build_metadata() -> dict[str, Any]:
    """Return build metadata surfaced through health/root endpoints and release artifacts."""
    return {
        "version": APP_VERSION,
        "sha": APP_BUILD_SHA,
        "created_at": APP_BUILD_CREATED_AT,
    }
