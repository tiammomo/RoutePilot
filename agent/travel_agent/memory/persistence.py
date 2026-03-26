"""Disk persistence helpers for session memory snapshots."""

from __future__ import annotations

import json
import os
import tempfile
from typing import Any, Optional


class MemoryPersistenceStore:
    """Best-effort persistence store with primary/backup recovery and atomic writes."""

    def __init__(self, persist_path: Optional[str], *, backup_suffix: str = ".bak") -> None:
        """Store the primary snapshot path and suffix used for hot backups."""
        self.persist_path = persist_path
        self.backup_suffix = backup_suffix

    @property
    def enabled(self) -> bool:
        """Return whether persistence is configured for the current manager instance."""
        return bool(self.persist_path)

    @property
    def backup_path(self) -> Optional[str]:
        """Return the hot-backup path associated with the primary snapshot file."""
        if not self.persist_path:
            return None
        return f"{self.persist_path}{self.backup_suffix}"

    def load_snapshot(self) -> tuple[Optional[dict[str, Any]], bool]:
        """Load the newest usable snapshot, falling back to the hot backup when needed."""
        if not self.persist_path:
            return None, False

        candidates = (
            (self.persist_path, False),
            (self.backup_path, True),
        )
        for path, recovered_from_backup in candidates:
            if not path or not os.path.exists(path):
                continue
            snapshot = self._load_snapshot_from_file(path)
            if snapshot is not None:
                return snapshot, recovered_from_backup
        return None, False

    def write_snapshot(self, payload: dict[str, Any]) -> None:
        """Write the current snapshot to both primary and hot-backup locations."""
        if not self.persist_path:
            return
        self._atomic_write_json(self.persist_path, payload)
        if self.backup_path:
            self._atomic_write_json(self.backup_path, payload)

    def restore_primary(self, payload: dict[str, Any]) -> None:
        """Rewrite the primary file from a recovered snapshot."""
        if not self.persist_path:
            return
        self._atomic_write_json(self.persist_path, payload)

    @staticmethod
    def _load_snapshot_from_file(path: str) -> Optional[dict[str, Any]]:
        """Load one JSON snapshot file and validate top-level shape."""
        try:
            with open(path, "r", encoding="utf-8") as handle:
                raw = json.load(handle)
        except Exception:
            return None
        return raw if isinstance(raw, dict) else None

    @staticmethod
    def _fsync_directory(path: str) -> None:
        """Best-effort directory fsync for stronger rename durability."""
        try:
            dir_fd = os.open(path, os.O_RDONLY)
        except Exception:
            return
        try:
            os.fsync(dir_fd)
        except Exception:
            pass
        finally:
            os.close(dir_fd)

    def _atomic_write_json(self, path: str, payload: dict[str, Any]) -> None:
        """Persist JSON payload atomically via temp file + fsync + os.replace."""
        target_dir = os.path.dirname(path) or "."
        os.makedirs(target_dir, exist_ok=True)
        prefix = f".{os.path.basename(path)}."
        fd, temp_path = tempfile.mkstemp(prefix=prefix, suffix=".tmp", dir=target_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
            self._fsync_directory(target_dir)
        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except Exception:
                    pass


__all__ = ["MemoryPersistenceStore"]
