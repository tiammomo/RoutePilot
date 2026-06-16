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
                "delivery_bundle": {
                    "schemaVersion": "2026-03-29",
                    "descriptor": {
                        "title": "杭州周末方案",
                        "filenameBase": "travel-plan-plan-hz",
                        "summary": "周末轻松游",
                        "summaryLines": ["目的地：杭州"],
                        "metrics": [],
                        "warnings": [],
                        "subagentTrail": ["规划"],
                        "shareContent": "杭州周末方案\n目的地：杭州",
                        "htmlDocumentTitle": "杭州周末方案 | Moyuan Travel Agent",
                        "htmlSections": [],
                    },
                    "artifact": {"itinerary": {"planId": "plan-hz"}},
                    "executionReceipt": {"sessionId": "session-1"},
                    "htmlContent": "<!doctype html><html><body><h1>杭州周末方案</h1></body></html>",
                    "share": {
                        "title": "杭州周末方案",
                        "content": "杭州周末方案\n目的地：杭州",
                    },
                },
            },
            headers={"origin": "http://localhost:33003"},
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
    assert detail_payload["delivery_bundle"]["schemaVersion"] == "2026-03-29"
    assert detail_payload["delivery_bundle"]["descriptor"]["filenameBase"] == "travel-plan-plan-hz"
    assert detail_payload["delivery_bundle"]["share"]["content"] == "杭州周末方案\n目的地：杭州"
