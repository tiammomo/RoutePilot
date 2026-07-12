"""Strict contracts for capability-based, immutable public Trip sharing."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from pydantic import Field
from routepilot_contracts import ShareSnapshot

from .models import StrictModel


class ShareStatus(StrEnum):
    """A share is never deleted so revocation remains auditable."""

    ACTIVE = "active"
    REVOKED = "revoked"


class ShareCreateRequest(StrictModel):
    """Pin the exact published TripSnapshot copied into a public projection."""

    artifact_id: str = Field(min_length=3, max_length=96)
    artifact_version: int = Field(ge=1)


class ShareView(StrictModel):
    """Authenticated management view; capability material is never included."""

    share_id: str
    public_id: str
    trip_id: str
    source_artifact_id: str
    source_artifact_version: int = Field(ge=1)
    status: ShareStatus
    version: int = Field(ge=1)
    capability_epoch: int = Field(ge=1)
    created_by: str
    created_at: datetime
    updated_at: datetime
    revoked_at: datetime | None = None


class ShareListResponse(StrictModel):
    items: list[ShareView]


class ShareMutationResponse(StrictModel):
    """A capability is returned only for a current create/rotate epoch."""

    share: ShareView
    capability_secret: str | None = Field(default=None, min_length=32, max_length=128)
    replayed: bool = False


class ShareExchangeRequest(StrictModel):
    """Secret copied from the URL fragment and posted exactly once."""

    secret: str = Field(min_length=32, max_length=128, pattern=r"^[A-Za-z0-9_-]+$")


class ShareExchangeResponse(StrictModel):
    """Server-to-BFF exchange result; browsers receive it only as an HttpOnly cookie."""

    session_token: str = Field(min_length=32, max_length=128)
    expires_at: datetime


class PublicShareSnapshotResponse(StrictModel):
    """Narrow public response containing only the reviewed ShareSnapshot contract."""

    public_id: str
    snapshot: ShareSnapshot


__all__ = [
    "PublicShareSnapshotResponse",
    "ShareCreateRequest",
    "ShareExchangeRequest",
    "ShareExchangeResponse",
    "ShareListResponse",
    "ShareMutationResponse",
    "ShareStatus",
    "ShareView",
]
