"""Shared helpers for chat service internals."""

from __future__ import annotations

from typing import Any, Optional


def merge_artifact_payload(
    base: Optional[dict[str, Any]],
    patch: Optional[dict[str, Any]],
) -> dict[str, Any]:
    """Deep-merge artifact fragments so preview, patch, and final snapshots stay aligned."""
    merged = dict(base or {})
    if not isinstance(patch, dict):
        return merged

    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = merge_artifact_payload(merged.get(key), value)
            continue
        merged[key] = value
    return merged
