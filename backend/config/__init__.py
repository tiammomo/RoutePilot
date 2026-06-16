"""Configuration module for moyuan-travel-agent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# 配置文件路径
SERVER_CONFIG_PATH = PROJECT_ROOT / "backend" / "config" / "server_config.yaml"


def _parse_bool(value: Any, default: bool) -> bool:
    raw = str(value).strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_int(value: Any, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
        if parsed < minimum:
            return default
        return parsed
    except Exception:
        return default


def _normalize_db_backend(value: Any, default: str = "file") -> str:
    raw = str(value).strip().lower()
    return raw if raw in {"file", "postgres"} else default


class ServerConfig:
    """Server configuration loader.

    Reads from `backend/config/server_config.yaml`, then applies environment overrides.
    The loader is intentionally lightweight so it can be used early during bootstrap.
    """

    _instance: Optional["ServerConfig"] = None
    _config: Dict[str, Any] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance

    def _load(self):
        """Load configuration from YAML file and merge environment overrides."""
        if SERVER_CONFIG_PATH.exists():
            with open(SERVER_CONFIG_PATH, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}
        else:
            self._config = {}
        self._apply_env_overrides()

    def _apply_env_overrides(self) -> None:
        """Merge environment variables on top of YAML values."""
        web = self._config.setdefault("web", {})
        frontend = self._config.setdefault("frontend", {})
        middleware = self._config.setdefault("middleware", {})
        observability = self._config.setdefault("observability", {})
        database = self._config.setdefault("database", {})
        startup = self._config.setdefault("startup", {})

        web["host"] = os.getenv("MOYUAN_WEB_HOST", web.get("host", "0.0.0.0"))
        web["port"] = _parse_int(os.getenv("MOYUAN_WEB_PORT", web.get("port", 38083)), 38083, 1)
        web["debug"] = _parse_bool(os.getenv("MOYUAN_WEB_DEBUG", web.get("debug", False)), False)

        env_cors = os.getenv("CORS_ORIGINS") or os.getenv("MOYUAN_CORS_ORIGINS")
        if env_cors:
            web["cors_origins"] = [item.strip() for item in env_cors.split(",") if item.strip()]

        frontend["port"] = _parse_int(
            os.getenv("MOYUAN_FRONTEND_PORT", frontend.get("port", 33003)),
            33003,
            1,
        )

        middleware["request_timeout_seconds"] = float(
            os.getenv("MOYUAN_REQUEST_TIMEOUT_SECONDS", middleware.get("request_timeout_seconds", 30.0))
        )
        middleware["rate_limit_max_requests"] = _parse_int(
            os.getenv("MOYUAN_RATE_LIMIT_MAX_REQUESTS", middleware.get("rate_limit_max_requests", 100)),
            100,
            1,
        )
        middleware["rate_limit_window_seconds"] = _parse_int(
            os.getenv("MOYUAN_RATE_LIMIT_WINDOW_SECONDS", middleware.get("rate_limit_window_seconds", 60)),
            60,
            1,
        )

        observability["metrics_enabled"] = _parse_bool(
            os.getenv("MOYUAN_METRICS_ENABLED", observability.get("metrics_enabled", True)),
            True,
        )
        observability["metrics_path"] = os.getenv(
            "MOYUAN_METRICS_PATH",
            observability.get("metrics_path", "/api/metrics"),
        )
        observability["structured_logging"] = _parse_bool(
            os.getenv("MOYUAN_STRUCTURED_LOGGING", observability.get("structured_logging", True)),
            True,
        )

        database["backend"] = _normalize_db_backend(
            os.getenv("MOYUAN_DB_BACKEND", database.get("backend", "file")),
            "file",
        )
        database["postgres_dsn"] = str(
            os.getenv("MOYUAN_POSTGRES_DSN", database.get("postgres_dsn", ""))
        ).strip()
        database["pool_min"] = _parse_int(
            os.getenv("MOYUAN_DB_POOL_MIN", database.get("pool_min", 1)),
            1,
            1,
        )
        database["pool_max"] = _parse_int(
            os.getenv("MOYUAN_DB_POOL_MAX", database.get("pool_max", 5)),
            5,
            1,
        )

        startup["fail_fast_validation"] = _parse_bool(
            os.getenv("MOYUAN_FAIL_FAST_STARTUP_VALIDATION", startup.get("fail_fast_validation", False)),
            False,
        )

    def reload(self):
        """Reload configuration from file."""
        self._load()

    @property
    def web_host(self) -> str:
        return str(self._config.get("web", {}).get("host", "0.0.0.0"))

    @property
    def web_port(self) -> int:
        return _parse_int(self._config.get("web", {}).get("port", 38083), 38083, 1)

    @property
    def web_debug(self) -> bool:
        return _parse_bool(self._config.get("web", {}).get("debug", False), False)

    @property
    def cors_origins(self) -> list[str]:
        return list(self._config.get("web", {}).get("cors_origins", []))

    @property
    def frontend_port(self) -> int:
        return _parse_int(self._config.get("frontend", {}).get("port", 33003), 33003, 1)

    @property
    def request_timeout_seconds(self) -> float:
        return float(self._config.get("middleware", {}).get("request_timeout_seconds", 30.0))

    @property
    def rate_limit_max_requests(self) -> int:
        return _parse_int(self._config.get("middleware", {}).get("rate_limit_max_requests", 100), 100, 1)

    @property
    def rate_limit_window_seconds(self) -> int:
        return _parse_int(self._config.get("middleware", {}).get("rate_limit_window_seconds", 60), 60, 1)

    @property
    def metrics_enabled(self) -> bool:
        return _parse_bool(self._config.get("observability", {}).get("metrics_enabled", True), True)

    @property
    def metrics_path(self) -> str:
        return str(self._config.get("observability", {}).get("metrics_path", "/api/metrics"))

    @property
    def structured_logging(self) -> bool:
        return _parse_bool(self._config.get("observability", {}).get("structured_logging", True), True)

    @property
    def db_backend(self) -> str:
        return _normalize_db_backend(self._config.get("database", {}).get("backend", "file"), "file")

    @property
    def postgres_dsn(self) -> str:
        return str(self._config.get("database", {}).get("postgres_dsn", "")).strip()

    @property
    def db_pool_min(self) -> int:
        return _parse_int(self._config.get("database", {}).get("pool_min", 1), 1, 1)

    @property
    def db_pool_max(self) -> int:
        configured = _parse_int(self._config.get("database", {}).get("pool_max", 5), 5, 1)
        return max(self.db_pool_min, configured)

    @property
    def fail_fast_startup_validation(self) -> bool:
        return _parse_bool(self._config.get("startup", {}).get("fail_fast_validation", False), False)

    def get(self, key: str, default: Any = None) -> Any:
        """Get config value by dot-notation key, e.g. `grpc.port`."""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value


# Singleton instance
server_config = ServerConfig()
