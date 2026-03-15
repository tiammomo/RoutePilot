"""Unit tests for durable share-link storage behavior."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from shuai_web.services.share_service import ShareService


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
