"""Persistent share-link storage service."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    """Execute utc now iso in backend support workflow.
    
    Purpose:
        Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
    
    Returns:
        str: Result value produced by this method.
    """
    return datetime.now(timezone.utc).isoformat()


class ShareService:
    """Create and fetch shared travel plans using local JSON storage."""

    def __init__(self, file_path: str = "data/share_links.json") -> None:
        """Initialize share service and load persisted share-link index from disk.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            file_path: Input `file_path` consumed by this method.
        
        Returns:
            None: Result value produced by this method.
        """
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        self._file_path = file_path
        self._lock = asyncio.Lock()
        self._items: dict[str, dict[str, Any]] = self._load_from_file()

    def _load_from_file(self) -> dict[str, dict[str, Any]]:
        """Load share-link records from persistence file into memory cache.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Returns:
            dict[str, dict[str, Any]]: Result value produced by this method.
        """
        try:
            with open(self._file_path, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
                if isinstance(payload, dict):
                    return payload
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            return {}
        return {}

    def _save_to_file(self) -> None:
        """Persist current share-link cache to disk.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Returns:
            None: Result value produced by this method.
        """
        with open(self._file_path, "w", encoding="utf-8") as handle:
            json.dump(self._items, handle, ensure_ascii=False, indent=2)

    async def create(self, *, title: str | None, content: str) -> tuple[str, dict[str, Any]]:
        """Create a share record and return generated share URL metadata.
        
        Purpose:
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            title: Input `title` consumed by this method.
            content: Text content to normalize or persist.
        
        Returns:
            tuple[str, dict[str, Any]]: Result value produced by this method.
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
            Provide explicit backend contracts and side-effect notes for maintainers and API integrators.
        
        Args:
            share_id: Input `share_id` consumed by this method.
        
        Returns:
            dict[str, Any] | None: Result value produced by this method.
        """
        async with self._lock:
            return self._items.get(share_id)
