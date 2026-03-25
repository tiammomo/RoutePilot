"""Route package exports with lazy resolution to avoid heavy import-time side effects."""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "api_docs_router",
    "chat_router",
    "city_router",
    "health_router",
    "map_router",
    "metrics_endpoint",
    "model_router",
    "session_router",
    "share_router",
]


def __getattr__(name: str) -> Any:
    """Resolve route exports lazily so helper imports do not trigger full router initialization."""
    module_map = {
        "api_docs_router": (".api_docs", "router"),
        "chat_router": (".chat", "router"),
        "city_router": (".city", "router"),
        "health_router": (".health", "router"),
        "map_router": (".map", "router"),
        "metrics_endpoint": (".health", "metrics_endpoint"),
        "model_router": (".model", "router"),
        "session_router": (".session", "router"),
        "share_router": (".share", "router"),
    }
    target = module_map.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module_name, attribute_name = target
    module = import_module(module_name, __name__)
    return getattr(module, attribute_name)
