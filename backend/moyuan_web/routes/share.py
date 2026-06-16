"""Share link endpoints for itinerary content."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Request

from ..api.error_codes import ApiErrorCode
from ..api.schemas.share import ShareCreateRequest, ShareCreateResponse, ShareDetailResponse
from ..api.validation import SHARE_ID_PATTERN
from .errors import raise_api_error
from .service_resolver import get_share_service

router = APIRouter()

ShareIdParam = Annotated[str, Path(min_length=10, max_length=10, pattern=SHARE_ID_PATTERN)]


@router.post("/share-links", response_model=ShareCreateResponse)
async def create_share_link(request: ShareCreateRequest, fastapi_request: Request):
    """Create a short share id and return an app URL with share query parameter."""
    _ = fastapi_request
    try:
        share_id, _record = await get_share_service().create(
            title=request.title,
            content=request.content,
            html_content=request.html_content,
            delivery_bundle=request.delivery_bundle.model_dump() if request.delivery_bundle else None,
        )
    except ValueError as exc:
        raise_api_error(status_code=422, message=str(exc), code=ApiErrorCode.SHARE_INVALID)

    origin = fastapi_request.headers.get("origin") or "http://localhost:33003"
    share_url = f"{origin}/?share={share_id}"
    return ShareCreateResponse(success=True, share_id=share_id, share_url=share_url)


@router.get("/share-links/{share_id}", response_model=ShareDetailResponse)
async def get_share_link(share_id: ShareIdParam):
    """Fetch shared travel-plan content by share id."""
    record = await get_share_service().get(share_id)
    if not record:
        raise_api_error(status_code=404, message="Share link not found", code=ApiErrorCode.SHARE_NOT_FOUND)

    return ShareDetailResponse(
        success=True,
        share_id=share_id,
        title=record.get("title") or "",
        content=str(record.get("content") or ""),
        html_content=(str(record.get("html_content") or "") or None),
        delivery_bundle=record.get("delivery_bundle") or None,
        created_at=str(record.get("created_at") or ""),
    )
