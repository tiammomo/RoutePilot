"""Session endpoint schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class UpdateNameRequest(BaseModel):
    """Payload for updating session display name."""

    name: str


class SetModelRequest(BaseModel):
    """Payload for binding a model to a session."""

    model_id: Optional[str] = None
    model: Optional[str] = None

    def resolve_model_id(self) -> Optional[str]:
        """Resolve model id from compatibility fields."""
        model_id = (self.model_id or self.model or "").strip()
        return model_id or None
