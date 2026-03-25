"""Share endpoint schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ShareCreateRequest(BaseModel):
    """Create share-link request body."""

    content: str = Field(min_length=1, max_length=50000)
    title: str | None = Field(default=None, max_length=100)


class ShareCreateResponse(BaseModel):
    """Create share-link response body."""

    success: bool = True
    share_id: str
    share_url: str


class ShareDetailResponse(BaseModel):
    """Shared content response body."""

    success: bool = True
    share_id: str
    title: str | None = None
    content: str
    created_at: str
