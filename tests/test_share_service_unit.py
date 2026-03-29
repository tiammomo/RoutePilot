"""Unit tests for durable share-link storage behavior."""

from __future__ import annotations

import json

import pytest

from moyuan_web.services.share_service import ShareService


@pytest.mark.asyncio
async def test_share_service_writes_primary_and_backup(tmp_path):
    storage_path = tmp_path / "share_links.json"
    service = ShareService(str(storage_path))

    share_id, record = await service.create(title="Weekend", content="Plan content")

    backup_path = tmp_path / f"share_links.json{ShareService.BACKUP_SUFFIX}"
    assert share_id
    assert record["share_id"] == share_id
    assert storage_path.exists()
    assert backup_path.exists()

    primary_snapshot = json.loads(storage_path.read_text(encoding="utf-8"))
    backup_snapshot = json.loads(backup_path.read_text(encoding="utf-8"))
    assert share_id in primary_snapshot
    assert share_id in backup_snapshot


@pytest.mark.asyncio
async def test_share_service_recovers_from_backup_when_primary_corrupted(tmp_path):
    storage_path = tmp_path / "share_links.json"
    service = ShareService(str(storage_path))
    share_id, _ = await service.create(title="Weekend", content="Plan content")

    storage_path.write_text("{invalid-json", encoding="utf-8")

    recovered = ShareService(str(storage_path))
    record = await recovered.get(share_id)
    assert record is not None
    assert record.get("share_id") == share_id

    repaired_snapshot = json.loads(storage_path.read_text(encoding="utf-8"))
    assert share_id in repaired_snapshot


@pytest.mark.asyncio
async def test_share_service_persists_html_delivery_payload(tmp_path):
    storage_path = tmp_path / "share_links.json"
    service = ShareService(str(storage_path))
    delivery_bundle = {
        "schemaVersion": "2026-03-29",
        "descriptor": {
            "title": "Weekend",
            "filenameBase": "travel-plan-weekend",
            "summary": "Weekend itinerary",
            "summaryLines": ["Destination: Hangzhou"],
            "metrics": [],
            "warnings": [],
            "subagentTrail": ["Planning"],
            "shareContent": "Weekend\nDestination: Hangzhou",
            "htmlDocumentTitle": "Weekend | Moyuan Travel Agent",
            "htmlSections": [],
        },
        "artifact": {"itinerary": {"planId": "plan-weekend"}},
        "executionReceipt": {"sessionId": "session-1"},
        "htmlContent": "<!doctype html><html><body><h1>Weekend</h1></body></html>",
        "share": {"title": "Weekend", "content": "Weekend\nDestination: Hangzhou"},
    }

    share_id, record = await service.create(
        title="Weekend",
        content="Plan content",
        html_content="<!doctype html><html><body><h1>Weekend</h1></body></html>",
        delivery_bundle=delivery_bundle,
    )

    assert share_id
    assert record["html_content"].startswith("<!doctype html>")
    assert record["delivery_bundle"] == delivery_bundle

    snapshot = json.loads(storage_path.read_text(encoding="utf-8"))
    assert snapshot[share_id]["html_content"].startswith("<!doctype html>")
    assert snapshot[share_id]["delivery_bundle"] == delivery_bundle
