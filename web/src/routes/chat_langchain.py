"""LangChain chat routes."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..dependencies.container import get_container
from ..services.chat_service import ChatService

router = APIRouter()


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None
    mode: Optional[str] = "react"


def _get_chat_service() -> ChatService:
    container = get_container()
    return container.resolve("ChatService")


@router.post("/chat/stream")
async def stream_chat(request: ChatRequest, fastapi_request: Request):
    if not request.message or not request.message.strip():
        raise HTTPException(status_code=422, detail="消息不能为空")
    if len(request.message) > 5000:
        raise HTTPException(status_code=422, detail="消息长度不能超过5000字符")

    service = _get_chat_service()

    return StreamingResponse(
        service.stream_chat(
            message=request.message.strip(),
            session_id=request.session_id,
            mode=request.mode or "react",
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
