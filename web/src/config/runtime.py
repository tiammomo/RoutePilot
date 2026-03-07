"""Runtime configuration accessors for web application."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from src.bootstrap import PROJECT_ROOT, ensure_project_paths
from src.config.config_manager import ConfigManager

ensure_project_paths()


def get_llm_config_path() -> str:
    return str(Path(PROJECT_ROOT) / "config" / "llm_config.yaml")


@lru_cache(maxsize=1)
def get_model_config_manager() -> ConfigManager:
    return ConfigManager(get_llm_config_path())


def get_server_config():
    from config import server_config

    return server_config
