"""Automated tests for file session storage persistence robustness."""

import json
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_DIR = PROJECT_ROOT / "web"
if str(WEB_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_DIR))

from shuai_web.storage.session_storage import FileSessionStorage


@pytest.mark.asyncio
async def test_file_session_storage_writes_primary_and_backup(tmp_path):
    storage_path = tmp_path / "sessions.json"
    storage = FileSessionStorage(str(storage_path))

    await storage.save("s1", {"session_id": "s1", "messages": []})

    backup_path = tmp_path / f"sessions.json{FileSessionStorage.BACKUP_SUFFIX}"
    assert storage_path.exists()
    assert backup_path.exists()

    backup_snapshot = json.loads(backup_path.read_text(encoding="utf-8"))
    assert "s1" in backup_snapshot


@pytest.mark.asyncio
async def test_file_session_storage_recovers_from_backup_when_primary_corrupted(tmp_path):
    storage_path = tmp_path / "sessions.json"
    storage = FileSessionStorage(str(storage_path))
    await storage.save("s1", {"session_id": "s1", "messages": [{"role": "user", "content": "hello"}]})

    # Simulate interrupted write on primary file.
    storage_path.write_text("{invalid-json", encoding="utf-8")

    recovered = FileSessionStorage(str(storage_path))
    loaded = await recovered.load("s1")
    assert loaded is not None
    assert loaded.get("session_id") == "s1"

    repaired_snapshot = json.loads(storage_path.read_text(encoding="utf-8"))
    assert "s1" in repaired_snapshot
