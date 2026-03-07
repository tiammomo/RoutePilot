"""Model info routes."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter

from src.config.runtime import get_model_config_manager
from .errors import raise_api_error

router = APIRouter()
logger = logging.getLogger(__name__)

_config_manager: Any = None


def set_config_manager(config_manager: Any) -> None:
    """Compatibility hook for external wiring."""
    global _config_manager
    _config_manager = config_manager


def _resolve_config_manager() -> Any:
    if _config_manager is not None:
        return _config_manager
    try:
        return get_model_config_manager()
    except Exception as exc:
        logger.warning("Failed to load model config manager; using fallback models: %s", exc)
        return None


def _fallback_models():
    return [
        {"model_id": "minimax-m2-5", "name": "MiniMax M2.5", "provider": "anthropic", "model": "MiniMax-M2.5"},
        {"model_id": "gpt-4o-mini", "name": "GPT-4o Mini", "provider": "openai", "model": "gpt-4o-mini"},
        {"model_id": "gpt-4o", "name": "GPT-4o", "provider": "openai", "model": "gpt-4o"},
        {
            "model_id": "claude-3-5-sonnet",
            "name": "Claude 3.5 Sonnet",
            "provider": "anthropic",
            "model": "claude-3-5-sonnet",
        },
    ]


@router.get("/models")
async def list_models():
    config_manager = _resolve_config_manager()
    if config_manager is not None:
        try:
            return {"success": True, "models": config_manager.get_available_models()}
        except Exception as exc:
            logger.warning("Failed to list configured models; using fallback models: %s", exc)

    return {"success": True, "models": _fallback_models()}


@router.get("/models/{model_id}")
async def get_model(model_id: str):
    config_manager = _resolve_config_manager()
    if config_manager is not None:
        try:
            model_config = config_manager.get_model_config(model_id)
            return {
                "success": True,
                "model_id": model_id,
                "name": model_config.get("name", model_id),
                "provider": model_config.get("provider", "unknown"),
                **model_config,
            }
        except ValueError:
            pass

    fallback_map = {item["model_id"]: item for item in _fallback_models()}
    if model_id not in fallback_map:
        raise_api_error(status_code=404, message="Model not found", code="MODEL_NOT_FOUND")

    return {"success": True, **fallback_map[model_id]}
