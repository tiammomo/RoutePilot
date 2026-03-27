"""Local ASGI smoke tests for share-link routes."""

from __future__ import annotations

import httpx
import pytest

from moyuan_web.main import create_app  # noqa: E402


@pytest.mark.asyncio
async def test_share_route_round_trips_html_delivery_payload():
    app = create_app()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        create_response = await client.post(
            "/api/share-links",
            json={
                "title": "杭州周末方案",
                "content": "杭州周末旅行方案",
                "html_content": "<!doctype html><html><body><h1>杭州周末方案</h1></body></html>",
            },
            headers={"origin": "http://localhost:33001"},
        )

        assert create_response.status_code == 200
        create_payload = create_response.json()
        assert create_payload["share_url"].endswith(f"?share={create_payload['share_id']}")

        detail_response = await client.get(f"/api/share-links/{create_payload['share_id']}")

    assert detail_response.status_code == 200
    detail_payload = detail_response.json()
    assert detail_payload["title"] == "杭州周末方案"
    assert detail_payload["content"] == "杭州周末旅行方案"
    assert detail_payload["html_content"].startswith("<!doctype html>")
