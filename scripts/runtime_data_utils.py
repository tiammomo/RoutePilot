"""Shared helpers for runtime data backup, restore, and pruning workflows."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit


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


def _safe_relative_to_project(path: Path, project_root: Path) -> str | None:
    """Return a project-relative path or None when the path is outside the project."""

    try:
        return str(path.resolve().relative_to(project_root.resolve())).replace("\\", "/")
    except Exception:
        return None


def _redact_checkpoint_target(target: str) -> str:
    """Redact checkpoint DSN credentials while preserving routing information."""

    parts = urlsplit(str(target))
    if not parts.scheme:
        return str(target)
    netloc = parts.netloc
    if "@" in netloc:
        credentials, host = netloc.rsplit("@", 1)
        if ":" in credentials:
            username, _password = credentials.split(":", 1)
            netloc = f"{username}:***@{host}"
        else:
            netloc = f"{credentials}@{host}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def resolve_checkpoint_runtime(project_root: Path) -> dict[str, Any]:
    """Resolve current checkpoint backend metadata used by backup/restore manifests."""

    from agent.travel_agent.runtime_sources import resolve_checkpointer_config

    backend_override = os.getenv("AGENT_CHECKPOINT_BACKEND") or None
    dsn_override = os.getenv("AGENT_CHECKPOINT_DSN") or None
    target_override = None
    if backend_override != "postgres" and not dsn_override:
        target_override = os.getenv("AGENT_CHECKPOINT_DB") or str(project_root / "data" / "langgraph_checkpoints.sqlite3")

    config = resolve_checkpointer_config(
        backend_override=backend_override,
        target_override=target_override,
        dsn_override=dsn_override,
    )
    target = str(config.target)
    archived_files: list[str] = []
    archive_contains_checkpoint_data = False
    restore_strategy = "metadata_only"

    if config.backend == "postgres":
        return {
            "backend": "postgres",
            "target": _redact_checkpoint_target(target),
            "archive_contains_checkpoint_data": False,
            "archived_files": archived_files,
            "restore_strategy": "external_snapshot",
        }

    target_path = Path(target)
    relative_target = _safe_relative_to_project(target_path, project_root)
    if relative_target is not None and target_path.exists():
        archived_files = [relative_target]
        archive_contains_checkpoint_data = True
        restore_strategy = "archive_file"
    elif target_path.exists():
        restore_strategy = "external_file"

    return {
        "backend": "sqlite",
        "target": relative_target or str(target_path),
        "archive_contains_checkpoint_data": archive_contains_checkpoint_data,
        "archived_files": archived_files,
        "restore_strategy": restore_strategy,
    }


def build_restore_instructions(checkpoint_runtime: dict[str, Any]) -> list[str]:
    """Build user-facing restore instructions derived from checkpoint runtime metadata."""

    backend = str(checkpoint_runtime.get("backend") or "sqlite")
    target = str(checkpoint_runtime.get("target") or "")
    archive_contains = bool(checkpoint_runtime.get("archive_contains_checkpoint_data"))
    strategy = str(checkpoint_runtime.get("restore_strategy") or "metadata_only")
    if backend == "postgres":
        return [
            "Checkpoint backend is postgres; restore checkpoint tables from an external database snapshot before switching runtime back to postgres.",
            f"Recorded checkpoint target: {target}",
            "This runtime backup archive stores checkpoint backend metadata only and does not export PostgreSQL checkpoint rows.",
        ]
    if archive_contains:
        return [
            "Checkpoint backend is sqlite; the archive contains the checkpoint database file and restore will place it back into the recorded runtime path.",
            f"Recorded checkpoint target: {target}",
        ]
    if strategy == "external_file":
        return [
            "Checkpoint backend is sqlite but the checkpoint file lives outside the project root, so this archive only records metadata.",
            f"Back up and restore the external checkpoint file separately: {target}",
        ]
    return [
        "No checkpoint database file was present at backup time; restore will only recover file-based runtime state included in the archive.",
        f"Recorded checkpoint target: {target}",
    ]


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

    checkpoint_runtime = resolve_checkpoint_runtime(project_root)
    for relative_path in checkpoint_runtime.get("archived_files", []):
        path = project_root / Path(relative_path)
        if not path.exists():
            continue
        results.append(
            {
                "key": "checkpoints",
                "relative_path": relative_path,
                "absolute_path": path,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return results


def build_manifest(project_root: Path, files: list[dict[str, Any]]) -> dict[str, Any]:
    """Build structured manifest stored next to runtime backup contents."""
    checkpoint_runtime = resolve_checkpoint_runtime(project_root)
    archived_paths = {str(item["relative_path"]) for item in files}
    checkpoint_runtime["archived_files"] = [
        str(relative_path)
        for relative_path in checkpoint_runtime.get("archived_files", [])
        if str(relative_path) in archived_paths
    ]
    checkpoint_runtime["archive_contains_checkpoint_data"] = bool(checkpoint_runtime["archived_files"])
    return {
        "schema_version": 2,
        "created_at": utc_now_iso(),
        "project_root": str(project_root),
        "checkpoint_runtime": checkpoint_runtime,
        "restore_instructions": build_restore_instructions(checkpoint_runtime),
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
