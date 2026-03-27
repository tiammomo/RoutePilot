"""Share link endpoints for itinerary content."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..api.schemas.share import ShareCreateRequest, ShareCreateResponse, ShareDetailResponse
from .errors import raise_api_error
from .service_resolver import get_share_service

router = APIRouter()


@router.post("/share-links", response_model=ShareCreateResponse)
async def create_share_link(request: ShareCreateRequest, fastapi_request: Request):
    """Create a short share id and return an app URL with share query parameter."""
    _ = fastapi_request
    try:
        share_id, _record = await get_share_service().create(
            title=request.title,
            content=request.content,
            html_content=request.html_content,
        )
    except ValueError as exc:
        raise_api_error(status_code=422, message=str(exc), code="SHARE_INVALID")

    origin = fastapi_request.headers.get("origin") or "http://localhost:33001"
    share_url = f"{origin}/?share={share_id}"
    return ShareCreateResponse(success=True, share_id=share_id, share_url=share_url)


@router.get("/share-links/{share_id}", response_model=ShareDetailResponse)
async def get_share_link(share_id: str):
    """Fetch shared travel-plan content by share id."""
    record = await get_share_service().get(share_id)
    if not record:
        raise_api_error(status_code=404, message="Share link not found", code="SHARE_NOT_FOUND")

    return ShareDetailResponse(
        success=True,
        share_id=share_id,
        title=record.get("title") or "",
        content=str(record.get("content") or ""),
        html_content=(str(record.get("html_content") or "") or None),
        created_at=str(record.get("created_at") or ""),
    )
