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
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            config_path: Input `config_path` consumed by this method.
        
        Returns:
            Any: Result value produced by this method.
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
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            config_path: Input `config_path` consumed by this method.
        
        Returns:
            str: Result value produced by this method.
        """
        if os.path.isabs(config_path):
            return config_path
        return str(os.path.join(str(PROJECT_ROOT), config_path))

    def _sync_from_delegate(self) -> None:
        """Sync cached config fields from delegated source manager.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Returns:
            None: Result value produced by this method.
        """
        self.config_path = self._delegate.config_path
        self.config = self._delegate.config
        self.models_config = self._delegate.models_config
        self.default_model_id = self._delegate.default_model_id
        self.travel_knowledge = getattr(self._delegate, "travel_knowledge", {})

    def _load_local_config(self) -> None:
        """Load local yaml/json config and merge with environment substitutions.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Returns:
            None: Result value produced by this method.
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
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            content: Text content to normalize or persist.
        
        Returns:
            str: Result value produced by this method.
        """
        pattern = r"\$\{([^}]+)\}"

        def replace(match):
            """Execute replace in backend support workflow.
            
            Purpose:
                Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
            
            Args:
                match: Input `match` consumed by this method.
            
            Returns:
                Any: Result value produced by this method.
            """
            var_name = match.group(1)
            env_value = os.environ.get(var_name, "")
            return env_value if env_value else match.group(0)

        return re.sub(pattern, replace, content)

    def get_config(self, key: str, default: Any = None) -> Any:
        """Get config from current backend context.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            key: Input `key` consumed by this method.
            default: Input `default` consumed by this method.
        
        Returns:
            Any: Result value produced by this method.
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
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            city_name: Input `city_name` consumed by this method.
        
        Returns:
            Optional[Dict[str, Any]]: Result value produced by this method.
        """
        return self.travel_knowledge.get("cities", {}).get(city_name)

    def get_all_cities(self) -> List[str]:
        """Get all cities from current backend context.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Returns:
            List[str]: Result value produced by this method.
        """
        return list(self.travel_knowledge.get("cities", {}).keys())

    @staticmethod
    def _is_model_active(model_config: Dict[str, Any]) -> bool:
        """Execute is model active in backend support workflow.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            model_config: Input `model_config` consumed by this method.
        
        Returns:
            bool: Result value produced by this method.
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
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Returns:
            List[Dict[str, Any]]: Result value produced by this method.
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
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            model_id: Model identifier used for lookup/update operations.
        
        Returns:
            Dict[str, Any]: Result value produced by this method.
        """
        target = model_id or self.default_model_id
        if target not in self.models_config:
            raise ValueError(f"Model not found: {target}")
        return self.models_config[target]

    def get_default_model_id(self) -> str:
        """Get default model id from current backend context.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Returns:
            str: Result value produced by this method.
        """
        return self.default_model_id

    def get_default_model_config(self) -> Dict[str, Any]:
        """Get default model config from current backend context.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Returns:
            Dict[str, Any]: Result value produced by this method.
        """
        return self.get_model_config(self.default_model_id)

    @property
    def agent_config(self) -> Dict[str, Any]:
        """Execute agent config in backend support workflow.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Returns:
            Dict[str, Any]: Result value produced by this method.
        """
        return self.config.get("agent", {})

    @property
    def web_config(self) -> Dict[str, Any]:
        """Execute web config in backend support workflow.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Returns:
            Dict[str, Any]: Result value produced by this method.
        """
        return self.config.get("web", {})

    @property
    def grpc_config(self) -> Dict[str, Any]:
        """Execute grpc config in backend support workflow.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Returns:
            Dict[str, Any]: Result value produced by this method.
        """
        return self.config.get("grpc", {})


_config_manager: Optional[ConfigManager] = None


def get_config(config_path: str = "config/llm_config.yaml") -> ConfigManager:
    """Get config from current backend context.
    
    Purpose:
        Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
    
    Args:
        config_path: Input `config_path` consumed by this method.
    
    Returns:
        ConfigManager: Result value produced by this method.
    """
    global _config_manager
    if _config_manager is None:
        _config_manager = ConfigManager(config_path)
    return _config_manager
