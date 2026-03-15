"""Shared helpers for runtime data backup, restore, and pruning workflows."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BACKUP_DIR = ROOT / "artifacts" / "runtime_backups"


@dataclass(frozen=True)
class RuntimeFileSpec:
    """Describe one runtime file that belongs to the operational data set."""

    key: str
    relative_path: str
    required: bool = False


RUNTIME_FILE_SPECS: tuple[RuntimeFileSpec, ...] = (
    RuntimeFileSpec("sessions", "data/sessions/sessions.json"),
    RuntimeFileSpec("sessions_backup", "data/sessions/sessions.json.bak"),
    RuntimeFileSpec("agent_memory", "data/agent_memory.json"),
    RuntimeFileSpec("agent_memory_backup", "data/agent_memory.json.bak"),
    RuntimeFileSpec("checkpoints", "data/langgraph_checkpoints.sqlite3"),
    RuntimeFileSpec("share_links", "data/share_links.json"),
    RuntimeFileSpec("share_links_backup", "data/share_links.json.bak"),
    RuntimeFileSpec("runtime_failures", "data/runtime_failure_clusters.jsonl"),
)


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def snapshot_timestamp_slug() -> str:
    """Return a filesystem-safe UTC timestamp used in archive filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    """Return sha256 hex digest for one file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def discover_runtime_files(project_root: Path) -> list[dict[str, Any]]:
    """Return metadata for runtime files that currently exist under the project root."""
    results: list[dict[str, Any]] = []
    for spec in RUNTIME_FILE_SPECS:
        path = project_root / Path(spec.relative_path)
        if not path.exists():
            if spec.required:
                raise FileNotFoundError(f"Required runtime file is missing: {spec.relative_path}")
            continue
        results.append(
            {
                "key": spec.key,
                "relative_path": spec.relative_path.replace("\\", "/"),
                "absolute_path": path,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return results


def build_manifest(project_root: Path, files: list[dict[str, Any]]) -> dict[str, Any]:
    """Build structured manifest stored next to runtime backup contents."""
    return {
        "schema_version": 1,
        "created_at": utc_now_iso(),
        "project_root": str(project_root),
        "files": [
            {
                "key": item["key"],
                "relative_path": item["relative_path"],
                "size_bytes": item["size_bytes"],
                "sha256": item["sha256"],
            }
            for item in files
        ],
    }


def load_json_file(path: Path, default: Any) -> Any:
    """Load JSON file when it exists, otherwise return provided default."""
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def parse_utc_iso(value: Any) -> datetime | None:
    """Parse UTC-ish ISO timestamp and normalize to timezone-aware datetime."""
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def ensure_relative_path(relative_path: str) -> Path:
    """Validate one relative archive path and reject traversal segments."""
    candidate = Path(relative_path)
    if candidate.is_absolute():
        raise ValueError(f"Backup manifest path must be relative: {relative_path}")
    if any(part == ".." for part in candidate.parts):
        raise ValueError(f"Backup manifest path cannot contain '..': {relative_path}")
    return candidate
