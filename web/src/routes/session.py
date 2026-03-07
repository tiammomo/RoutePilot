"""Session management routes."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..dependencies.container import get_container
from ..services.session_service import SessionService
from .errors import raise_api_error

router = APIRouter()


class UpdateNameRequest(BaseModel):
    name: str


class SetModelRequest(BaseModel):
    model_id: str


def _get_session_service() -> SessionService:
    return get_container().resolve("SessionService")


def _raise_not_found(message: str) -> None:
    raise_api_error(status_code=404, message=message, code="SESSION_NOT_FOUND")


@router.post("/session/new")
async def create_session(name: Optional[str] = None):
    service = _get_session_service()
    return await service.create_session(name=name)


@router.get("/sessions")
async def list_sessions(include_empty: bool = False):
    service = _get_session_service()
    return await service.list_sessions(include_empty=include_empty)


@router.delete("/session/{session_id}")
async def delete_session(session_id: str):
    service = _get_session_service()
    result = await service.delete_session(session_id)
    if not result.get("success"):
        _raise_not_found(result.get("error", "Session not found"))
    return result


@router.put("/session/{session_id}/name")
async def update_session_name(session_id: str, request: UpdateNameRequest):
    service = _get_session_service()
    result = await service.update_session_name(session_id, request.name)
    if not result.get("success"):
        _raise_not_found(result.get("error", "Session not found"))
    return result


@router.put("/session/{session_id}/model")
async def set_session_model(session_id: str, request: SetModelRequest):
    service = _get_session_service()
    result = await service.update_session_model(session_id, request.model_id)
    if not result.get("success"):
        _raise_not_found(result.get("error", "Session not found"))
    return result


@router.get("/session/{session_id}/model")
async def get_session_model(session_id: str):
    service = _get_session_service()
    result = await service.get_session_model(session_id)
    if not result.get("success"):
        _raise_not_found(result.get("error", "Session not found"))
    return result


@router.post("/clear/{session_id}")
async def clear_chat(session_id: str):
    service = _get_session_service()
    result = await service.clear_chat(session_id)
    if not result.get("success"):
        _raise_not_found(result.get("error", "Session not found"))
    return result


@router.post("/clear")
async def clear_chat_with_query(session_id: str = Query(..., description="Session ID")):
    if not session_id:
        raise_api_error(status_code=400, message="session_id is required", code="INVALID_ARGUMENT")

    service = _get_session_service()
    result = await service.clear_chat(session_id)
    if not result.get("success"):
        _raise_not_found(result.get("error", "Session not found"))
    return result
