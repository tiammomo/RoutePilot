"""Web-layer configuration manager.

Prefers delegating to agent's ConfigManager implementation. Falls back to a
local lightweight implementation when agent config module is unavailable.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, List, Optional

import yaml

from ..bootstrap import PROJECT_ROOT, ensure_project_paths

ensure_project_paths()

_AGENT_CONFIG_MANAGER_CLASS = None
try:
    from config.config_manager import ConfigManager as AgentConfigManager

    _AGENT_CONFIG_MANAGER_CLASS = AgentConfigManager
except (ImportError, ValueError):
    _AGENT_CONFIG_MANAGER_CLASS = None


class ConfigManager:
    """Configuration manager with agent-first delegation."""

    def __init__(self, config_path: str = "config/llm_config.yaml"):
        """Initialize config manager and hydrate runtime cache from source files/environment.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            config_path: Filesystem/resource path for `config_path` resolution.
        
        Returns:
            Any: Runtime-dependent object returned to the calling layer.
        """
        self._delegate = None
        self.config_path = self._resolve_config_path(config_path)

        self.config: Dict[str, Any] = {}
        self.models_config: Dict[str, Dict[str, Any]] = {}
        self.default_model_id: str = "gpt-4o-mini"
        self.travel_knowledge: Dict[str, Any] = {}

        if _AGENT_CONFIG_MANAGER_CLASS is not None:
            self._delegate = _AGENT_CONFIG_MANAGER_CLASS(self.config_path)
            self._sync_from_delegate()
        else:
            self._load_local_config()

    @staticmethod
    def _resolve_config_path(config_path: str) -> str:
        """Resolve effective config path with environment override and fallback defaults.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            config_path: Filesystem/resource path for `config_path` resolution.
        
        Returns:
            str: Normalized text string used by downstream logic.
        """
        if os.path.isabs(config_path):
            return config_path
        return str(os.path.join(str(PROJECT_ROOT), config_path))

    def _sync_from_delegate(self) -> None:
        """Sync cached config fields from delegated source manager.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        self.config_path = self._delegate.config_path
        self.config = self._delegate.config
        self.models_config = self._delegate.models_config
        self.default_model_id = self._delegate.default_model_id
        self.travel_knowledge = getattr(self._delegate, "travel_knowledge", {})

    def _load_local_config(self) -> None:
        """Load local yaml/json config and merge with environment substitutions.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
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
        self.default_model_id = self.config.get("default_model", "gpt-4o-mini")
        self.travel_knowledge = self.config.get("travel_knowledge", {})

    @staticmethod
    def _replace_env_vars(content: str) -> str:
        """Replace ${ENV_VAR} placeholders recursively inside config payload.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            content: Text content to normalize or persist.
        
        Returns:
            str: Normalized text string used by downstream logic.
        """
        pattern = r"\$\{([^}]+)\}"

        def replace(match):
            """Replace environment placeholders in configuration text.
            
            Purpose:
                Document service/API behavior, side effects, and integration expectations for maintainers.
            
            Args:
                match: Regex match object containing parsed configuration placeholders.
            
            Returns:
                Any: Runtime-dependent object returned to the calling layer.
            """
            var_name = match.group(1)
            env_value = os.environ.get(var_name, "")
            return env_value if env_value else match.group(0)

        return re.sub(pattern, replace, content)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get config from current backend context.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            key: Input field `key` used for normalization or matching rules.
            default: Fallback value used when parsing fails or variable is missing.
        
        Returns:
            Any: Runtime-dependent object returned to the calling layer.
        """
        keys = key.split(".")
        value: Any = self.config

        for part in keys:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default

        return value

    def get_city_info(self, city_name: str) -> Optional[Dict[str, Any]]:
        """Get city info from current backend context.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            city_name: Text input `city_name` used for parsing, prompt assembly, or display.
        
        Returns:
            Optional[Dict[str, Any]]: Computed value returned to the caller.
        """
        return self.travel_knowledge.get("cities", {}).get(city_name)

    def get_all_cities(self) -> List[str]:
        """Get all cities from current backend context.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            List[str]: Computed value returned to the caller.
        """
        return list(self.travel_knowledge.get("cities", {}).keys())

    @staticmethod
    def _is_model_active(model_config: Dict[str, Any]) -> bool:
        """Check whether a model entry is enabled and active.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            model_config: Model configuration payload loaded from runtime settings.
        
        Returns:
            bool: Boolean outcome flag used by guards or success checks.
        """
        api_key = model_config.get("api_key", "")
        if not api_key:
            return False

        if api_key.startswith("${") and api_key.endswith("}"):
            var_name = api_key[2:-1]
            return bool(os.environ.get(var_name))

        if "YOUR_" in api_key.upper():
            return False

        return True

    def get_available_models(self) -> List[Dict[str, Any]]:
        """Return active model list filtered by runtime flags and model status.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            List[Dict[str, Any]]: Computed value returned to the caller.
        """
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
        """Return model config for one model ID with fallback to default model.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            model_id: Model identifier used for lookup/update operations.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        target = model_id or self.default_model_id
        if target not in self.models_config:
            raise ValueError(f"Model not found: {target}")
        return self.models_config[target]

    def get_default_model_id(self) -> str:
        """Get default model id from current backend context.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            str: Normalized text string used by downstream logic.
        """
        return self.default_model_id

    def get_default_model_config(self) -> Dict[str, Any]:
        """Get default model config from current backend context.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        return self.get_model_config(self.default_model_id)

    @property
    def agent_config(self) -> Dict[str, Any]:
        """Return validated agent configuration snapshot.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        return self.config.get("agent", {})

    @property
    def web_config(self) -> Dict[str, Any]:
        """Return validated web configuration snapshot.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        return self.config.get("web", {})

    @property
    def grpc_config(self) -> Dict[str, Any]:
        """Return validated gRPC configuration snapshot.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            Dict[str, Any]: Computed value returned to the caller.
        """
        return self.config.get("grpc", {})


_config_manager: Optional[ConfigManager] = None


def get_config(config_path: str = "config/llm_config.yaml") -> ConfigManager:
    """Get config from current backend context.
    
    Purpose:
        Document service/API behavior, side effects, and integration expectations for maintainers.
    
    Args:
        config_path: Filesystem/resource path for `config_path` resolution.
    
    Returns:
        ConfigManager: Computed value returned to the caller.
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_path)
    return _config_manager
