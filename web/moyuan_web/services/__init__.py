"""Application service layer for session and chat orchestration."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = ["ChatService", "SessionService", "CityService", "MapService", "ShareService"]


def __getattr__(name: str) -> Any:
    """Resolve service exports lazily to avoid heavy import-time side effects."""
    module_map = {
        "ChatService": ".chat_service",
        "CityService": ".city_service",
        "MapService": ".map_service",
        "ShareService": ".share_service",
        "SessionService": ".session_service",
    }
    module_name = module_map.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = import_module(module_name, __name__)
    return getattr(module, name)
