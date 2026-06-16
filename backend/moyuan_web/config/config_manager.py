"""Runtime model-configuration loader for the web layer."""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import yaml

from ..bootstrap import PROJECT_ROOT, ensure_project_paths

ensure_project_paths()


class ConfigManager:
    """Load one LLM config file and expose model/runtime lookup helpers."""

    def __init__(self, config_path: str = "backend/config/llm_config.yaml"):
        """Initialize one config manager from the configured YAML or JSON path."""

        self.config_path = self._resolve_config_path(config_path)
        self.config: Dict[str, Any] = {}
        self.models_config: Dict[str, Dict[str, Any]] = {}
        self.default_model_id: str = "mimo-v2.5-pro"
        self.travel_knowledge: Dict[str, Any] = {}
        self._load_config()

    @staticmethod
    def _resolve_config_path(config_path: str) -> str:
        """Resolve one config path relative to project root when needed."""

        if os.path.isabs(config_path):
            return config_path
        return str(os.path.join(str(PROJECT_ROOT), config_path))

    def _load_config(self) -> None:
        """Load YAML or JSON config into the in-memory runtime view."""

        if not os.path.exists(self.config_path):
            raise FileNotFoundError(f"Configuration file missing: {self.config_path}")

        with open(self.config_path, "r", encoding="utf-8") as f:
            content = f.read()

        content = self._replace_env_vars(content)

        if self.config_path.endswith((".yaml", ".yml")):
            self.config = yaml.safe_load(content)
        else:
            self.config = json.loads(content)

        self.config = self.config or {}
        self.models_config = self.config.get("models", {})
        self.default_model_id = self.config.get("default_model", "mimo-v2.5-pro")
        self.travel_knowledge = self.config.get("travel_knowledge", {})

    @staticmethod
    def _replace_env_vars(content: str) -> str:
        """Replace `${ENV_VAR}` placeholders inside raw config text."""

        pattern = r"\$\{([^}]+)\}"

        def replace(match):
            """Resolve one placeholder token from environment variables."""

            var_name = match.group(1)
            env_value = os.environ.get(var_name, "")
            return env_value if env_value else match.group(0)

        return re.sub(pattern, replace, content)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Return one nested config value via dotted-key lookup."""

        keys = key.split(".")
        value: Any = self.config

        for part in keys:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default

        return value

    def get_city_info(self, city_name: str) -> Optional[Dict[str, Any]]:
        """Return one curated city record from travel-knowledge config."""

        return self.travel_knowledge.get("cities", {}).get(city_name)

    def get_all_cities(self) -> List[str]:
        """Return all configured travel-knowledge city IDs."""

        return list(self.travel_knowledge.get("cities", {}).keys())

    @staticmethod
    def _is_model_active(model_config: Dict[str, Any]) -> bool:
        """Return whether one model entry is usable at runtime."""

        api_key = model_config.get("api_key", "")
        if not api_key:
            return False

        if api_key.startswith("${") and api_key.endswith("}"):
            var_name = api_key[2:-1]
            return bool(os.environ.get(var_name))

        placeholder_markers = ("YOUR_", "YOUR-", "REPLACE-WITH", "PLACEHOLDER", "<REPLACE")
        if any(marker in api_key.upper() for marker in placeholder_markers):
            return False

        return True

    def get_available_models(self) -> List[Dict[str, Any]]:
        """Return active model list filtered by runtime-secret availability."""

        models: List[Dict[str, Any]] = []
        for model_id, model_config in self.models_config.items():
            if not self._is_model_active(model_config):
                continue

            models.append(
                {
                    "model_id": model_id,
                    "name": model_config.get("name", model_id),
                    "provider": model_config.get("provider", "openai"),
                    "model": model_config.get("model", model_id),
                }
            )
        return models

    def get_model_config(self, model_id: Optional[str] = None) -> Dict[str, Any]:
        """Return one configured model payload or the default model when omitted."""

        target = model_id or self.default_model_id
        if target not in self.models_config:
            raise ValueError(f"Model not found: {target}")
        return self.models_config[target]

    def get_default_model_id(self) -> str:
        """Return the configured default model ID."""

        return self.default_model_id

    def get_default_model_config(self) -> Dict[str, Any]:
        """Return the configured default model payload."""

        return self.get_model_config(self.default_model_id)

    @property
    def agent_config(self) -> Dict[str, Any]:
        """Return the raw `agent` config block."""

        return self.config.get("agent", {})

    @property
    def web_config(self) -> Dict[str, Any]:
        """Return the raw `web` config block."""

        return self.config.get("web", {})

    @property
    def grpc_config(self) -> Dict[str, Any]:
        """Return the raw `grpc` config block."""

        return self.config.get("grpc", {})


_config_manager: Optional[ConfigManager] = None


def get_config(config_path: str = "backend/config/llm_config.yaml") -> ConfigManager:
    """Return one process-wide cached config manager instance."""

    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_path)
    return _config_manager
