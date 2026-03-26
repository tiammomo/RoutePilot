"""Artifact retrieval routes."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..api.schemas import ArtifactHistoryResponse, LatestArtifactResponse
from .errors import raise_api_error
from .service_resolver import get_artifact_service

router = APIRouter()


@router.get("/artifacts/{session_id}/latest", response_model=LatestArtifactResponse)
async def get_latest_artifact(session_id: str):
    """Return the latest persisted trip artifact for one session."""
    service = get_artifact_service()
    result = await service.get_latest_artifact(session_id)
    if not result.get("success"):
        raise_api_error(status_code=404, message=result.get("error", "Session not found"), code="SESSION_NOT_FOUND")
    return result


@router.get("/artifacts/{session_id}/history", response_model=ArtifactHistoryResponse)
async def get_artifact_history(session_id: str, limit: int = Query(default=10, ge=1, le=50)):
    """Return persisted artifact snapshots for one session in newest-first order."""
    service = get_artifact_service()
    result = await service.get_artifact_history(session_id, limit=limit)
    if not result.get("success"):
        raise_api_error(status_code=404, message=result.get("error", "Session not found"), code="SESSION_NOT_FOUND")
    return result
