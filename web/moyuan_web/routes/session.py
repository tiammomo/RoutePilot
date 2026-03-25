"""Session management routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query

from ..api.schemas.session import SetModelRequest, UpdateNameRequest
from .errors import raise_api_error
from .service_resolver import get_chat_service, get_session_service

router = APIRouter()


def _raise_not_found(message: str) -> None:
    """Raise standard not-found response for session endpoints."""
    raise_api_error(status_code=404, message=message, code="SESSION_NOT_FOUND")


@router.post("/session/new")
async def create_session(name: Optional[str] = None):
    """Create a new chat session with optional custom name."""
    service = get_session_service()
    return await service.create_session(name=name)


@router.get("/sessions")
async def list_sessions(include_empty: bool = False):
    """List sessions, optionally including empty sessions."""
    service = get_session_service()
    return await service.list_sessions(include_empty=include_empty)


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    """Delete session and all associated messages."""
    service = get_session_service()
    result = await service.delete_session(session_id)
    if not result.get("success"):
        _raise_not_found(result.get("error", "Session not found"))
    return result


@router.put("/session/{session_id}/name")
async def update_session_name(session_id: str, request: UpdateNameRequest):
    """Update session display name."""
    service = get_session_service()
    result = await service.update_session_name(session_id, request.name)
    if not result.get("success"):
        _raise_not_found(result.get("error", "Session not found"))
    return result


@router.put("/session/{session_id}/model")
async def set_session_model(session_id: str, request: SetModelRequest):
    """Bind a model id to a session."""
    model_id = request.resolve_model_id()
    if not model_id:
        raise_api_error(status_code=422, message="model_id is required", code="INVALID_ARGUMENT")

    service = get_session_service()
    result = await service.update_session_model(session_id, model_id)
    if not result.get("success"):
        _raise_not_found(result.get("error", "Session not found"))
    return result


@router.get("/session/{session_id}/model")
async def get_session_model(session_id: str):
    """Get model binding metadata for a session."""
    service = get_session_service()
    result = await service.get_session_model(session_id)
    if not result.get("success"):
        _raise_not_found(result.get("error", "Session not found"))
    return result


@router.get("/session/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Return persisted public messages for one session."""
    service = get_chat_service()
    result = await service.get_messages(session_id)
    if not result.get("success"):
        _raise_not_found(result.get("error", "Session not found"))
    return result


@router.post("/clear/{session_id}")
async def clear_chat(session_id: str):
    """Clear all messages in the target session."""
    service = get_session_service()
    result = await service.clear_chat(session_id)
    if not result.get("success"):
        _raise_not_found(result.get("error", "Session not found"))
    return result


@router.post("/clear")
async def clear_chat_with_query(session_id: str = Query(..., description="Session ID")):
    """Backward-compatible clear endpoint that accepts session_id query param."""
    if not session_id:
        raise_api_error(status_code=400, message="session_id is required", code="INVALID_ARGUMENT")

    service = get_session_service()
    result = await service.clear_chat(session_id)
    if not result.get("success"):
        _raise_not_found(result.get("error", "Session not found"))
    return result
