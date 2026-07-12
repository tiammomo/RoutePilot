"""V1 problem-detail isolation at the shared FastAPI exception boundary."""

from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict

from backend.moyuan_web.error_handlers import register_exception_handlers


class _StrictPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str


def _app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.post("/api/v1/validate")
    async def validate(payload: _StrictPayload) -> _StrictPayload:
        return payload

    @app.get("/api/v1/forbidden")
    async def forbidden() -> None:
        raise HTTPException(
            status_code=403,
            detail={
                "code": "ACTION_FORBIDDEN",
                "message": "The action is not permitted.",
                "retryable": False,
                "private_debug": "must-not-cross-boundary",
            },
        )

    return app


@pytest.mark.asyncio
async def test_v1_validation_never_echoes_input_values() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()),
        base_url="http://testserver",
    ) as client:
        response = await client.post(
            "/api/v1/validate",
            json={"title": 42, "access_token": "secret-value"},
        )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "INVALID_REQUEST"
    assert "secret-value" not in response.text
    assert "body.access_token" in response.json()["detail"]["fields"]


@pytest.mark.asyncio
async def test_v1_http_errors_keep_the_public_contract_and_drop_private_fields() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app()),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/forbidden")

    assert response.status_code == 403
    assert response.json() == {
        "detail": {
            "code": "ACTION_FORBIDDEN",
            "message": "The action is not permitted.",
            "retryable": False,
        }
    }
