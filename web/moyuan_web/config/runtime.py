"""Runtime configuration accessors for web application."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from moyuan_web.bootstrap import PROJECT_ROOT, ensure_project_paths
from moyuan_web.config.config_manager import ConfigManager

ensure_project_paths()


def get_llm_config_path() -> str:
    """Return the canonical LLM YAML config path under project root."""
    return str(Path(PROJECT_ROOT) / "config" / "llm_config.yaml")


@lru_cache(maxsize=1)
def get_model_config_manager() -> ConfigManager:
    """Create and cache the model config manager for request handlers."""
    return ConfigManager(get_llm_config_path())


def get_server_config():
    """Lazy-load server configuration to avoid import cycles during bootstrap."""
    from config import server_config

    return server_config
