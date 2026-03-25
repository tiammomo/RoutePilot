"""Startup validation and readiness snapshot builders for the web API."""

from __future__ import annotations

import logging
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from moyuan_web.bootstrap_container import initialize_dependency_container
from moyuan_web.bootstrap import PROJECT_ROOT
from moyuan_web.config.runtime import get_llm_config_path, get_model_config_manager, get_server_config
from moyuan_web.observability import emit_structured_log, set_readiness_state

logger = logging.getLogger(__name__)


def _check_ok(name: str, message: str, **details: Any) -> dict[str, Any]:
    """Build one successful readiness-check record with attached metadata."""
    return {
        "name": name,
        "status": "ok",
        "message": message,
        "details": details,
    }


def _check_not_ready(name: str, message: str, **details: Any) -> dict[str, Any]:
    """Build one failed readiness-check record with attached metadata."""
    return {
        "name": name,
        "status": "not_ready",
        "message": message,
        "details": details,
    }


async def build_startup_readiness_snapshot() -> dict[str, Any]:
    """Run startup validation checks and return a readiness snapshot."""
    checks: dict[str, dict[str, Any]] = {}

    # 1) Server config can fall back to defaults, but surface the effective values.
    try:
        server_config = get_server_config()
        config_path = Path(PROJECT_ROOT) / "config" / "server_config.yaml"
        checks["server_config"] = _check_ok(
            "server_config",
            "Server configuration resolved.",
            config_path=str(config_path),
            exists=config_path.exists(),
            web_host=server_config.web_host,
            web_port=server_config.web_port,
            frontend_port=server_config.frontend_port,
            metrics_enabled=server_config.metrics_enabled,
        )
    except Exception as exc:
        checks["server_config"] = _check_not_ready("server_config", f"Failed to resolve server config: {exc}")

    # 2) Data directory must be writable for sessions, memory, checkpoints, and replay outputs.
    data_dir = Path(PROJECT_ROOT) / "data"
    try:
        data_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=data_dir, prefix=".startup-", delete=True):
            pass
        checks["data_dir"] = _check_ok("data_dir", "Runtime data directory is writable.", path=str(data_dir))
    except Exception as exc:
        checks["data_dir"] = _check_not_ready("data_dir", f"Runtime data directory is not writable: {exc}", path=str(data_dir))

    # 3) LLM config should exist and expose at least one active model for production readiness.
    llm_path = Path(get_llm_config_path())
    if not llm_path.exists():
        checks["llm_config"] = _check_not_ready(
            "llm_config",
            "LLM configuration file is missing.",
            path=str(llm_path),
        )
    else:
        try:
            model_manager = get_model_config_manager()
            available_models = model_manager.get_available_models()
            if not available_models:
                checks["llm_config"] = _check_not_ready(
                    "llm_config",
                    "No active model configuration is available.",
                    path=str(llm_path),
                    default_model=model_manager.get_default_model_id(),
                )
            else:
                checks["llm_config"] = _check_ok(
                    "llm_config",
                    "LLM configuration loaded.",
                    path=str(llm_path),
                    default_model=model_manager.get_default_model_id(),
                    active_models=[item["model_id"] for item in available_models],
                )
        except Exception as exc:
            checks["llm_config"] = _check_not_ready(
                "llm_config",
                f"Failed to load model configuration: {exc}",
                path=str(llm_path),
            )

    # 4) Dependency container and chat runtime should resolve cleanly.
    try:
        container = initialize_dependency_container()
        _ = container.resolve("SessionRepository")
        chat_service = container.resolve("ChatService")
        checks["container"] = _check_ok(
            "container",
            "Dependency container resolved required services.",
            services=["SessionRepository", "ChatService"],
        )
    except Exception as exc:
        checks["container"] = _check_not_ready("container", f"Failed to resolve dependency container: {exc}")
        chat_service = None

    if checks["llm_config"]["status"] == "ok" and chat_service is not None:
        try:
            await chat_service.initialize()
            runtime_status = await chat_service.health_status()
            checks["chat_runtime"] = _check_ok(
                "chat_runtime",
                "Chat runtime initialized.",
                initialized=runtime_status.get("initialized", False),
                tools_count=runtime_status.get("tools_count", 0),
                memory_enabled=runtime_status.get("memory_enabled", False),
            )
        except Exception as exc:
            checks["chat_runtime"] = _check_not_ready("chat_runtime", f"Chat runtime initialization failed: {exc}")
    else:
        checks["chat_runtime"] = _check_not_ready(
            "chat_runtime",
            "Chat runtime skipped because prerequisites are not ready.",
        )

    mandatory_checks = ("server_config", "data_dir", "llm_config", "container", "chat_runtime")
    ready = all(checks[name]["status"] == "ok" for name in mandatory_checks)
    snapshot = {
        "status": "ready" if ready else "not_ready",
        "validated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
    set_readiness_state(ready)
    emit_structured_log(
        logger,
        "startup_validation",
        status=snapshot["status"],
        checks={name: item["status"] for name, item in checks.items()},
    )
    return snapshot


async def refresh_app_readiness_state(app: Any) -> dict[str, Any]:
    """Refresh and cache readiness snapshot on the FastAPI application object."""
    snapshot = await build_startup_readiness_snapshot()
    app.state.readiness_snapshot = snapshot
    return snapshot


def readiness_requires_fail_fast() -> bool:
    """Return whether startup validation should fail application boot."""
    try:
        server_config = get_server_config()
        return bool(server_config.fail_fast_startup_validation)
    except Exception:
        return False


async def maybe_fail_fast_on_startup(app: Any) -> dict[str, Any]:
    """Refresh readiness snapshot and optionally raise on startup failure."""
    snapshot = await refresh_app_readiness_state(app)
    if snapshot.get("status") != "ready" and readiness_requires_fail_fast():
        failed = [name for name, item in snapshot.get("checks", {}).items() if item.get("status") != "ok"]
        raise RuntimeError(f"Startup validation failed: {', '.join(failed)}")
    return snapshot
