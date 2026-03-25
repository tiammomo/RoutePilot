"""Chat endpoint request schemas."""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel


class ChatRequest(BaseModel):
    """Request payload for the streaming chat endpoint."""

    message: str
    display_message: Optional[str] = None
    session_id: Optional[str] = None
    mode: Optional[str] = "react"
