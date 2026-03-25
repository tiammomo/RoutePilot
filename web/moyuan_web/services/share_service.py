"""Persistent share-link storage service."""

from __future__ import annotations

import asyncio
import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format.
    
    Purpose:
        Document service/API behavior, side effects, and integration expectations for maintainers.
    
    Returns:
        str: Normalized text string used by downstream logic.
    """
    return datetime.now(timezone.utc).isoformat()


class ShareService:
    """Create and fetch shared travel plans using local JSON storage."""

    BACKUP_SUFFIX = ".bak"

    def __init__(self, file_path: str = "data/share_links.json") -> None:
        """Initialize share service and load persisted share-link index from disk.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            file_path: Filesystem/resource path for `file_path` resolution.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        os.makedirs(os.path.dirname(file_path) or ".", exist_ok=True)
        self._file_path = file_path
        self._lock = asyncio.Lock()
        self._items: dict[str, dict[str, Any]] = self._load_from_file()

    @classmethod
    def _backup_path(cls, path: str) -> str:
        """Return backup filepath for the primary share-link snapshot."""
        return f"{path}{cls.BACKUP_SUFFIX}"

    @staticmethod
    def _load_json_file(path: str) -> dict[str, dict[str, Any]] | None:
        """Load one JSON snapshot file when it exists and is well-formed."""
        try:
            with open(path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return None
        return payload if isinstance(payload, dict) else None

    @staticmethod
    def _fsync_directory(path: str) -> None:
        """Best-effort directory fsync so renamed snapshots survive process crashes."""
        try:
            directory_fd = os.open(path, os.O_RDONLY)
        except OSError:
            return
        try:
            os.fsync(directory_fd)
        except OSError:
            pass
        finally:
            os.close(directory_fd)

    def _atomic_write_json(self, path: str, payload: dict[str, dict[str, Any]]) -> None:
        """Persist JSON payload atomically using temp-file plus replace."""
        target_dir = os.path.dirname(path) or "."
        os.makedirs(target_dir, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(
            prefix=f".{os.path.basename(path)}.",
            suffix=".tmp",
            dir=target_dir,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as tmp_file:
                json.dump(payload, tmp_file, ensure_ascii=False, indent=2)
                tmp_file.flush()
                os.fsync(tmp_file.fileno())
            os.replace(temp_path, path)
            self._fsync_directory(target_dir)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

    def _load_from_file(self) -> dict[str, dict[str, Any]]:
        """Load share-link records from persistence file into memory cache.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            dict[str, dict[str, Any]]: Computed value returned to the caller.
        """
        primary = self._file_path
        backup = self._backup_path(primary)

        primary_payload = self._load_json_file(primary)
        if primary_payload is not None:
            return primary_payload

        backup_payload = self._load_json_file(backup)
        if backup_payload is None:
            return {}

        # If the main file is corrupted or missing, rewrite it from the last known-good backup.
        try:
            self._atomic_write_json(primary, backup_payload)
        except OSError:
            pass
        return backup_payload

    def _save_to_file(self) -> None:
        """Persist current share-link cache to disk.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Returns:
            None: No explicit return value; side effects happen in-place.
        """
        self._atomic_write_json(self._file_path, self._items)
        self._atomic_write_json(self._backup_path(self._file_path), self._items)

    async def create(self, *, title: str | None, content: str) -> tuple[str, dict[str, Any]]:
        """Create a share record and return generated share URL metadata.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            title: Text input `title` used for parsing, prompt assembly, or display.
            content: Text content to normalize or persist.
        
        Returns:
            tuple[str, dict[str, Any]]: Computed value returned to the caller.
        """
        if not content.strip():
            raise ValueError("content cannot be empty")

        share_id = uuid.uuid4().hex[:10]
        record = {
            "share_id": share_id,
            "title": title.strip() if title else "",
            "content": content.strip(),
            "created_at": _utc_now_iso(),
        }
        async with self._lock:
            self._items[share_id] = record
            await asyncio.to_thread(self._save_to_file)
        return share_id, record

    async def get(self, share_id: str) -> dict[str, Any] | None:
        """Return one share record by token with expiration checks.
        
        Purpose:
            Document service/API behavior, side effects, and integration expectations for maintainers.
        
        Args:
            share_id: Unique identifier for `share_id` used in lookup/tracing logic.
        
        Returns:
            dict[str, Any] | None: Computed value returned to the caller.
        """
        async with self._lock:
            return self._items.get(share_id)
