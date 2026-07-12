"""Core implementation for the repeatable RoutePilot V1 data migration.

The module deliberately has no destructive operation.  It reads immutable legacy
snapshots and inserts deterministic, read-only ``ImportedTripArchive`` records into
the already-expanded V1 schema.  Conflicting target rows are reported instead of
being overwritten.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import json
import os
import re
import tempfile
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from sqlalchemy import MetaData, Table, and_, create_engine, func, inspect, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import IntegrityError


SCHEMA_VERSION = 1
ARCHIVE_MANIFEST_SCHEMA = "routepilot.v1.archive-manifest@1"
INVENTORY_SCHEMA = "routepilot.v1.migration-inventory@1"
VERIFY_SCHEMA = "routepilot.v1.reconciliation-report@1"
STATE_SCHEMA = "routepilot.v1.backfill-state@1"
MAPPING_SCHEMA = "routepilot.v1.owner-mapping@1"
ARTIFACT_TYPE = "ImportedTripArchive"

REQUIRED_TARGET_TABLES = {
    "v1_trips",
    "v1_trip_members",
    "v1_artifacts",
    "v1_artifact_versions",
}
SOURCE_TABLES = {"sessions", "session_messages", "share_links"}

_DENIED_KEYS = re.compile(
    r"(?:reason(?:ing)?|thought|chain.?of.?thought|tool|raw|diagnostic|traceback|"
    r"stack|exception|error|secret|password|passwd|authorization|api.?key|"
    r"token|cookie|html)",
    re.IGNORECASE,
)
_SECRET_PATTERNS = (
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/=-]{8,}"),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"\bAIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bxox[a-z]-[A-Za-z0-9-]{12,}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----[\s\S]*?-----END (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(
        r"(?i)(?:api[_-]?key|secret|password|passwd|token)\s*[:=]\s*"
        r"(?:['\"])?[^\s,'\"&]{6,}"
    ),
    re.compile(r"(?i)([?&](?:key|api[_-]?key|token|secret)=)[^&#\s]+"),
)
_ALLOWED_MESSAGE_ROLES = {"user", "assistant", "system"}
_ALLOWED_PUBLIC_ARTIFACT_KEYS = {
    "title",
    "summary",
    "summary_lines",
    "warnings",
    "itinerary",
    "days",
    "items",
    "routes",
    "budget",
    "currency",
    "destination",
    "start_date",
    "end_date",
    "content",
    "answer",
    "plan_id",
    "planId",
}


class MigrationError(RuntimeError):
    """Expected fail-closed migration error safe to show to an operator."""


@dataclass(frozen=True)
class SourceRecord:
    """One stable unit that maps to one V1 Trip and one legacy Artifact."""

    source_kind: str
    source_id: str
    payload: dict[str, Any]
    origins: tuple[str, ...]

    @property
    def key(self) -> str:
        return f"{self.source_kind}:{self.source_id}"

    @property
    def cursor(self) -> str:
        return self.key

    @property
    def public_content(self) -> dict[str, Any]:
        return build_imported_trip_archive(self)

    @property
    def source_checksum(self) -> str:
        return sha256_json(self.public_content)


@dataclass(frozen=True)
class OwnerMapping:
    """An explicit tenant/owner decision for one legacy source object."""

    tenant_id: str
    owner_id: str
    locale: str = "zh-CN"
    timezone: str = "Asia/Shanghai"


def utc_now() -> datetime:
    """Return an aware UTC timestamp."""

    return datetime.now(timezone.utc)


def iso_now() -> str:
    """Return a canonical UTC timestamp for reports."""

    return utc_now().isoformat().replace("+00:00", "Z")


def canonical_json(value: Any) -> str:
    """Serialize a JSON-compatible value deterministically."""

    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_bytes(value: bytes) -> str:
    """Return a prefixed SHA-256 digest."""

    return f"sha256:{hashlib.sha256(value).hexdigest()}"


def sha256_json(value: Any) -> str:
    """Hash a JSON-compatible value canonically."""

    return sha256_bytes(canonical_json(value).encode("utf-8"))


def read_json(path: Path) -> Any:
    """Read JSON with an operator-safe error."""

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MigrationError(f"required file does not exist: {path}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise MigrationError(f"cannot read valid JSON from: {path}") from exc


def _build_engine(database_url: str, *, source: bool = False) -> Engine:
    """Build a synchronous engine with migration-safe PostgreSQL isolation."""

    try:
        backend = make_url(database_url).get_backend_name()
    except Exception as exc:  # SQLAlchemy raises several URL-specific subclasses.
        raise MigrationError("database URL is invalid") from exc
    options: dict[str, Any] = {"future": True}
    if backend == "postgresql":
        options["isolation_level"] = "REPEATABLE READ" if source else "SERIALIZABLE"
    return create_engine(database_url, **options)


def write_json_atomic(path: Path, value: Any) -> None:
    """Atomically persist one JSON report without following an existing symlink."""

    if path.exists() and path.is_symlink():
        raise MigrationError(f"refusing to replace symlink: {path}")
    path = path.parent.resolve(strict=False) / path.name
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _clean_string(value: Any, *, maximum: int = 200_000) -> str:
    """Project a legacy scalar into bounded plain text and redact common secrets."""

    text = str(value or "")
    text = "".join(char for char in text if char in "\n\t" or ord(char) >= 32)
    for pattern in _SECRET_PATTERNS:
        if pattern.pattern.startswith("(?i)([?&]"):
            text = pattern.sub(r"\1[REDACTED]", text)
        else:
            text = pattern.sub("[REDACTED]", text)
    return html.escape(text[:maximum], quote=False)


def _public_value(value: Any, *, depth: int = 0) -> Any:
    """Recursively retain only an allowlisted public artifact projection."""

    if depth > 8:
        return None
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return _clean_string(value)
    if isinstance(value, list):
        return [_public_value(item, depth=depth + 1) for item in value[:1000]]
    if not isinstance(value, Mapping):
        return _clean_string(value)
    projected: dict[str, Any] = {}
    for raw_key, item in value.items():
        key = str(raw_key)
        if _DENIED_KEYS.search(key):
            continue
        if depth == 0 and key not in _ALLOWED_PUBLIC_ARTIFACT_KEYS:
            continue
        projected[key] = _public_value(item, depth=depth + 1)
    return projected


def _message_projection(message: Any, sequence: int) -> dict[str, Any] | None:
    """Project one legacy message without reasoning, tool output, or diagnostics."""

    if not isinstance(message, Mapping):
        return None
    role = str(message.get("role") or "").lower()
    if role not in _ALLOWED_MESSAGE_ROLES:
        return None
    content = _clean_string(message.get("content"))
    if not content:
        return None
    projected: dict[str, Any] = {
        "source_message_ref": f"message:{sequence}",
        "role": role,
        "content": content,
    }
    timestamp = _clean_string(message.get("timestamp"), maximum=64)
    if timestamp:
        projected["timestamp"] = timestamp
    return projected


def _extract_source_artifact(messages: Sequence[Any], payload: Mapping[str, Any]) -> dict[str, Any]:
    """Extract only public allowlisted plan fields from old diagnostic bundles."""

    candidates: list[Any] = []
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        diagnostics = message.get("diagnostics")
        if isinstance(diagnostics, Mapping):
            candidates.append(diagnostics.get("artifact"))
    delivery = payload.get("delivery_bundle")
    if isinstance(delivery, Mapping):
        candidates.extend((delivery.get("artifact"), delivery.get("share"), delivery.get("descriptor")))
    for candidate in reversed(candidates):
        projected = _public_value(candidate)
        if isinstance(projected, dict) and projected:
            return projected
    return {}


def build_imported_trip_archive(record: SourceRecord) -> dict[str, Any]:
    """Build the only artifact form permitted for legacy migration."""

    payload = record.payload
    raw_messages = payload.get("messages")
    messages = list(raw_messages) if isinstance(raw_messages, list) else []
    projected_messages = [
        projected
        for sequence, message in enumerate(messages, start=1)
        if (projected := _message_projection(message, sequence)) is not None
    ]
    if record.source_kind == "share":
        shared_content = _clean_string(payload.get("content"))
        if shared_content:
            projected_messages = [
                {
                    "source_message_ref": "share:content",
                    "role": "assistant",
                    "content": shared_content,
                }
            ]

    title = _clean_string(payload.get("name") or payload.get("title") or "Legacy trip", maximum=160)
    answer = "\n\n".join(
        str(message["content"])
        for message in projected_messages
        if message.get("role") == "assistant"
    )
    return {
        "schema_version": 1,
        "schema_origin": "legacy",
        "read_only": True,
        "source": {
            "kind": record.source_kind,
            # Do not copy a weak legacy share token or guessable session ID into
            # the user-facing Artifact.  The restricted archive manifest keeps
            # the reversible source-to-target mapping for operators.
            "ref": sha256_bytes(record.key.encode("utf-8")),
        },
        "title": title or "Legacy trip",
        "answer": answer,
        "messages": projected_messages,
        "artifact": _extract_source_artifact(messages, payload),
    }


def _normalize_messages(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, Mapping)]


def _load_snapshot(path: Path, kind: str) -> dict[str, SourceRecord]:
    if not path.exists():
        return {}
    payload = read_json(path)
    if not isinstance(payload, Mapping):
        raise MigrationError(f"legacy snapshot must be a JSON object: {path}")
    records: dict[str, SourceRecord] = {}
    for source_id, raw in payload.items():
        if not isinstance(raw, Mapping):
            raise MigrationError(f"legacy record must be an object: {kind}:{source_id}")
        normalized = dict(raw)
        normalized.setdefault(f"{kind}_id", str(source_id))
        if kind == "session":
            normalized["messages"] = _normalize_messages(normalized.get("messages"))
        record = SourceRecord(kind, str(source_id), normalized, (f"file:{path}",))
        records[record.key] = record
    return records


def _reflect_optional(connection: Connection, table_name: str) -> Table | None:
    if not inspect(connection).has_table(table_name):
        return None
    return Table(table_name, MetaData(), autoload_with=connection)


def _load_sql_records(source_engine: Engine) -> dict[str, SourceRecord]:
    """Read compatibility tables without modifying the source database."""

    records: dict[str, SourceRecord] = {}
    with source_engine.connect() as connection:
        sessions = _reflect_optional(connection, "sessions")
        session_messages = _reflect_optional(connection, "session_messages")
        shares = _reflect_optional(connection, "share_links")
        messages_by_session: dict[str, list[dict[str, Any]]] = defaultdict(list)
        if session_messages is not None:
            rows = connection.execute(
                select(session_messages).order_by(
                    session_messages.c.session_id.asc(), session_messages.c.sequence.asc()
                )
            ).mappings()
            for row in rows:
                message = dict(row)
                messages_by_session[str(message["session_id"])].append(message)
        if sessions is not None:
            session_ids: set[str] = set()
            for row in connection.execute(select(sessions)).mappings():
                normalized = dict(row)
                source_id = str(normalized.get("session_id") or "")
                if not source_id:
                    raise MigrationError("legacy sessions table contains an empty session_id")
                session_ids.add(source_id)
                normalized_messages = messages_by_session.get(source_id)
                if normalized_messages:
                    normalized["messages"] = normalized_messages
                else:
                    normalized["messages"] = _normalize_messages(normalized.get("messages"))
                record = SourceRecord("session", source_id, normalized, ("sql:sessions",))
                records[record.key] = record
            orphan_message_sessions = sorted(set(messages_by_session) - session_ids)
            if orphan_message_sessions:
                raise MigrationError(
                    f"legacy session_messages contains {len(orphan_message_sessions)} orphan session references"
                )
        elif messages_by_session:
            raise MigrationError("legacy session_messages exists without a sessions table")
        if shares is not None:
            for row in connection.execute(select(shares)).mappings():
                normalized = dict(row)
                source_id = str(normalized.get("share_id") or "")
                if not source_id:
                    raise MigrationError("legacy share_links table contains an empty share_id")
                record = SourceRecord("share", source_id, normalized, ("sql:share_links",))
                records[record.key] = record
    return records


def _merge_records(*collections: Mapping[str, SourceRecord]) -> list[SourceRecord]:
    merged: dict[str, SourceRecord] = {}
    for collection in collections:
        for key, incoming in collection.items():
            existing = merged.get(key)
            if existing is None:
                merged[key] = incoming
                continue
            if not hmac.compare_digest(existing.source_checksum, incoming.source_checksum):
                raise MigrationError(f"conflicting legacy copies for {key}")
            merged[key] = SourceRecord(
                existing.source_kind,
                existing.source_id,
                existing.payload,
                tuple(sorted(set(existing.origins + incoming.origins))),
            )
    return sorted(merged.values(), key=lambda item: item.cursor)


def load_sources(
    *,
    sessions_file: Path | None,
    share_links_file: Path | None,
    source_database_url: str | None,
) -> list[SourceRecord]:
    """Load and deduplicate all configured legacy sources."""

    if not sessions_file and not share_links_file and not source_database_url:
        raise MigrationError("at least one legacy source is required")
    sources: list[Mapping[str, SourceRecord]] = []
    engines: list[Engine] = []
    try:
        if sessions_file:
            sources.append(_load_snapshot(sessions_file, "session"))
        if share_links_file:
            sources.append(_load_snapshot(share_links_file, "share"))
        if source_database_url:
            engine = _build_engine(source_database_url, source=True)
            engines.append(engine)
            sources.append(_load_sql_records(engine))
        return _merge_records(*sources)
    finally:
        for engine in engines:
            engine.dispose()


def load_owner_mapping(path: Path | None) -> tuple[dict[str, OwnerMapping], str | None]:
    """Load an explicit, versioned owner mapping; never infer identity."""

    if path is None:
        return {}, None
    payload = read_json(path)
    if not isinstance(payload, Mapping) or payload.get("schema") != MAPPING_SCHEMA:
        raise MigrationError(f"owner mapping must declare schema {MAPPING_SCHEMA}")
    raw_mappings = payload.get("mappings")
    if not isinstance(raw_mappings, Mapping):
        raise MigrationError("owner mapping .mappings must be an object")
    mappings: dict[str, OwnerMapping] = {}
    for key, raw in raw_mappings.items():
        if not isinstance(raw, Mapping):
            raise MigrationError(f"owner mapping must be an object: {key}")
        tenant_id = str(raw.get("tenant_id") or "").strip()
        owner_id = str(raw.get("owner_id") or "").strip()
        if not tenant_id or not owner_id:
            raise MigrationError(f"owner mapping requires tenant_id and owner_id: {key}")
        if len(tenant_id) > 128 or len(owner_id) > 128:
            raise MigrationError(f"owner mapping exceeds V1 identifier limits: {key}")
        mappings[str(key)] = OwnerMapping(
            tenant_id=tenant_id,
            owner_id=owner_id,
            locale=str(raw.get("locale") or "zh-CN")[:32],
            timezone=str(raw.get("timezone") or "Asia/Shanghai")[:64],
        )
    return mappings, sha256_json(payload)


def _file_inventory(paths: Iterable[Path]) -> list[dict[str, Any]]:
    inventory: list[dict[str, Any]] = []
    seen: set[Path] = set()
    for root in paths:
        resolved = root.resolve(strict=False)
        candidates = [resolved] if resolved.is_file() or resolved.is_symlink() else []
        if resolved.is_dir():
            candidates = sorted(item for item in resolved.rglob("*") if item.is_file() or item.is_symlink())
        if not candidates and not resolved.exists():
            inventory.append({"path": str(resolved), "status": "missing"})
            continue
        for path in candidates:
            if path in seen:
                continue
            seen.add(path)
            relative = str(path.relative_to(resolved)) if resolved.is_dir() else path.name
            if path.is_symlink():
                inventory.append({"path": str(path), "relative_path": relative, "status": "symlink_not_followed"})
                continue
            try:
                content = path.read_bytes()
                stat = path.stat()
            except OSError:
                inventory.append({"path": str(path), "relative_path": relative, "status": "unreadable"})
                continue
            inventory.append(
                {
                    "path": str(path),
                    "relative_path": relative,
                    "status": "inventoried",
                    "size_bytes": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                    "checksum": sha256_bytes(content),
                    "decision": "archive_pending_review",
                }
            )
    return inventory


def build_inventory(
    *,
    sessions_file: Path | None = None,
    share_links_file: Path | None = None,
    source_database_url: str | None = None,
    owner_mapping_file: Path | None = None,
    file_data_roots: Sequence[Path] = (),
) -> dict[str, Any]:
    """Scan all legacy data and produce a high-water inventory report."""

    records = load_sources(
        sessions_file=sessions_file,
        share_links_file=share_links_file,
        source_database_url=source_database_url,
    )
    mappings, mapping_checksum = load_owner_mapping(owner_mapping_file)
    record_inventory = [
        {
            "source_key": record.key,
            "source_kind": record.source_kind,
            "source_id": record.source_id,
            "cursor": record.cursor,
            "source_checksum": record.source_checksum,
            "origins": list(record.origins),
            "message_count": len(record.public_content.get("messages", [])),
            "owner_status": "resolved" if record.key in mappings else "unresolved",
            "decision": "migrate" if record.key in mappings else "pending_owner_decision",
        }
        for record in records
    ]
    unresolved = [item["source_key"] for item in record_inventory if item["owner_status"] == "unresolved"]
    source_counts = {
        kind: sum(1 for record in records if record.source_kind == kind)
        for kind in ("session", "share")
    }
    high_water = records[-1].cursor if records else None
    data_fingerprint = sha256_json(
        [{"source_key": item["source_key"], "source_checksum": item["source_checksum"]} for item in record_inventory]
    )
    return {
        "schema": INVENTORY_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_now(),
        "mode": "read_only_inventory",
        "source_tables_scanned": sorted(SOURCE_TABLES),
        "high_water_cursor": high_water,
        "source_counts": source_counts,
        "source_record_count": len(records),
        "source_fingerprint": data_fingerprint,
        "owner_mapping_checksum": mapping_checksum,
        "owner_resolved_count": len(records) - len(unresolved),
        "owner_unresolved_count": len(unresolved),
        "owner_unresolved": unresolved,
        "records": record_inventory,
        "file_data": _file_inventory(file_data_roots),
        "blocking_issues": (["owner_mapping_incomplete"] if unresolved else []),
    }


def _validate_inventory(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict) or payload.get("schema") != INVENTORY_SCHEMA:
        raise MigrationError(f"inventory must declare schema {INVENTORY_SCHEMA}")
    if not isinstance(payload.get("records"), list):
        raise MigrationError("inventory records are missing")
    return payload


def _validate_source_snapshot(records: Sequence[SourceRecord], inventory: Mapping[str, Any]) -> list[SourceRecord]:
    expected_items = inventory.get("records")
    if not isinstance(expected_items, list):
        raise MigrationError("inventory records are missing")
    expected = {
        str(item.get("source_key")): str(item.get("source_checksum"))
        for item in expected_items
        if isinstance(item, Mapping)
    }
    current = {record.key: record for record in records}
    missing = sorted(set(expected) - set(current))
    changed = sorted(
        key
        for key in set(expected) & set(current)
        if not hmac.compare_digest(expected[key], current[key].source_checksum)
    )
    if missing or changed:
        raise MigrationError("legacy source changed at or below the recorded high-water mark")

    # New records belong to the write-through journal/catch-up pass.  The
    # current request migrates exactly the immutable record set in inventory.
    selected = sorted((current[key] for key in expected), key=lambda item: item.cursor)
    fingerprint = sha256_json(
        [{"source_key": record.key, "source_checksum": record.source_checksum} for record in selected]
    )
    if not hmac.compare_digest(str(inventory.get("source_fingerprint") or ""), fingerprint):
        raise MigrationError("inventory fingerprint is internally inconsistent")
    return selected


def _deterministic_id(prefix: str, source_key: str) -> str:
    digest = hashlib.sha256(f"routepilot-v1:{prefix}:{source_key}".encode()).hexdigest()[:48]
    return f"migr_{prefix}_{digest}"


def _parse_datetime(value: Any) -> datetime:
    text = str(value or "").strip()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _target_rows(record: SourceRecord, owner: OwnerMapping) -> dict[str, dict[str, Any]]:
    trip_id = _deterministic_id("trip", record.key)
    artifact_id = _deterministic_id("artifact", record.key)
    public_content = record.public_content
    source_checksum = record.source_checksum
    content = dict(public_content)
    content["migration"] = {
        "source_ref": sha256_bytes(record.key.encode("utf-8")),
        "source_checksum": source_checksum,
        "projection_checksum": sha256_json(public_content),
    }
    created_at = _parse_datetime(record.payload.get("created_at"))
    title = str(public_content.get("title") or "Legacy trip")[:160]
    return {
        "trip": {
            "trip_id": trip_id,
            "tenant_id": owner.tenant_id,
            "owner_id": owner.owner_id,
            "title": title,
            "locale": owner.locale,
            "timezone": owner.timezone,
            "status": "active",
            "version": 1,
            "current_artifact_id": artifact_id,
            "current_artifact_version": 1,
            "created_at": created_at,
            "updated_at": created_at,
        },
        "member": {
            "tenant_id": owner.tenant_id,
            "trip_id": trip_id,
            "user_id": owner.owner_id,
            "role": "owner",
            "version": 1,
            "created_at": created_at,
            "updated_at": created_at,
        },
        "artifact": {
            "artifact_id": artifact_id,
            "trip_id": trip_id,
            "tenant_id": owner.tenant_id,
            "artifact_type": ARTIFACT_TYPE,
            "created_by": owner.owner_id,
            "created_at": created_at,
        },
        "artifact_version": {
            "artifact_id": artifact_id,
            "tenant_id": owner.tenant_id,
            "version": 1,
            "schema_version": 1,
            "status": "published",
            "content": content,
            "parent_version": None,
            "created_at": created_at,
        },
    }


def _reflect_targets(connection: Connection) -> dict[str, Table]:
    inspector = inspect(connection)
    missing = sorted(table for table in REQUIRED_TARGET_TABLES if not inspector.has_table(table))
    if missing:
        raise MigrationError(f"target expand migration is missing tables: {', '.join(missing)}")
    metadata = MetaData()
    return {name: Table(name, metadata, autoload_with=connection) for name in REQUIRED_TARGET_TABLES}


def _same_value(actual: Any, expected: Any) -> bool:
    if isinstance(actual, datetime) and isinstance(expected, datetime):
        if actual.tzinfo is None:
            actual = actual.replace(tzinfo=timezone.utc)
        return actual.astimezone(timezone.utc) == expected.astimezone(timezone.utc)
    if isinstance(actual, (dict, list)) or isinstance(expected, (dict, list)):
        return sha256_json(actual) == sha256_json(expected)
    return actual == expected


def _insert_or_validate(
    connection: Connection,
    table: Table,
    primary_key: Mapping[str, Any],
    expected: Mapping[str, Any],
) -> str:
    """Insert a deterministic row or prove the existing row is identical."""

    predicate = and_(*(table.c[key] == value for key, value in primary_key.items()))
    existing = connection.execute(select(table).where(predicate)).mappings().first()
    if existing is None:
        try:
            connection.execute(table.insert().values(**expected))
            return "inserted"
        except IntegrityError as exc:
            raise MigrationError(f"target uniqueness conflict in {table.name}") from exc
    mismatches = [
        key for key, value in expected.items() if key in existing and not _same_value(existing[key], value)
    ]
    if mismatches:
        raise MigrationError(
            f"refusing to overwrite changed target row {table.name}; fields: {', '.join(sorted(mismatches))}"
        )
    return "already_applied"


def _load_archive(path: Path | None) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "schema": ARCHIVE_MANIFEST_SCHEMA,
            "schema_version": SCHEMA_VERSION,
            "created_at": iso_now(),
            "updated_at": iso_now(),
            "status": "in_progress",
            "entries": [],
        }
    payload = read_json(path)
    if not isinstance(payload, dict) or payload.get("schema") != ARCHIVE_MANIFEST_SCHEMA:
        raise MigrationError(f"archive manifest must declare schema {ARCHIVE_MANIFEST_SCHEMA}")
    if not isinstance(payload.get("entries"), list):
        raise MigrationError("archive manifest entries are missing")
    return payload


def _load_state(path: Path | None, request_hash: str) -> dict[str, Any]:
    if path is None or not path.exists():
        return {
            "schema": STATE_SCHEMA,
            "request_hash": request_hash,
            "last_committed_cursor": None,
            "batches_committed": 0,
            "records_committed": 0,
            "status": "not_started",
        }
    payload = read_json(path)
    if not isinstance(payload, dict) or payload.get("schema") != STATE_SCHEMA:
        raise MigrationError(f"resume state must declare schema {STATE_SCHEMA}")
    if not hmac.compare_digest(str(payload.get("request_hash") or ""), request_hash):
        raise MigrationError("resume state request hash does not match this backfill request")
    return payload


def _archive_entry(record: SourceRecord, rows: Mapping[str, Mapping[str, Any]], status: str) -> dict[str, Any]:
    return {
        "source_key": record.key,
        "source_kind": record.source_kind,
        "source_id": record.source_id,
        "source_checksum": record.source_checksum,
        "target_trip_id": rows["trip"]["trip_id"],
        "target_artifact_id": rows["artifact"]["artifact_id"],
        "target_artifact_version": 1,
        "target_content_checksum": sha256_json(rows["artifact_version"]["content"]),
        "status": status,
        "timestamp": iso_now(),
    }


def backfill(
    *,
    target_database_url: str,
    inventory_file: Path,
    owner_mapping_file: Path,
    sessions_file: Path | None = None,
    share_links_file: Path | None = None,
    source_database_url: str | None = None,
    archive_manifest_file: Path | None = None,
    state_file: Path | None = None,
    batch_size: int = 100,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Backfill high-water records in independently committed, resumable batches."""

    if not target_database_url.strip():
        raise MigrationError("target database URL is required")
    if batch_size < 1 or batch_size > 10_000:
        raise MigrationError("batch_size must be between 1 and 10000")
    inventory = _validate_inventory(read_json(inventory_file))
    records = load_sources(
        sessions_file=sessions_file,
        share_links_file=share_links_file,
        source_database_url=source_database_url,
    )
    selected = _validate_source_snapshot(records, inventory)
    mappings, mapping_checksum = load_owner_mapping(owner_mapping_file)
    if mapping_checksum != inventory.get("owner_mapping_checksum"):
        raise MigrationError("owner mapping changed after inventory; create a new inventory")
    unresolved = [record.key for record in selected if record.key not in mappings]
    if unresolved:
        raise MigrationError(f"owner mapping is incomplete for {len(unresolved)} source records")

    request = {
        "inventory_checksum": sha256_json(inventory),
        "mapping_checksum": mapping_checksum,
        "high_water_cursor": inventory.get("high_water_cursor"),
        "target_schema": sorted(REQUIRED_TARGET_TABLES),
        "projection_schema": "ImportedTripArchive@1-public",
    }
    request_hash = sha256_json(request)
    state = _load_state(state_file, request_hash)
    last_cursor = state.get("last_committed_cursor")
    pending = [record for record in selected if last_cursor is None or record.cursor > str(last_cursor)]
    archive = _load_archive(archive_manifest_file)
    existing_entries = {str(entry.get("source_key")): entry for entry in archive["entries"]}

    result: dict[str, Any] = {
        "schema": "routepilot.v1.backfill-report@1",
        "generated_at": iso_now(),
        "dry_run": dry_run,
        "request_hash": request_hash,
        "high_water_cursor": inventory.get("high_water_cursor"),
        "resume_from_cursor": last_cursor,
        "selected_count": len(selected),
        "pending_count": len(pending),
        "batches_planned": (len(pending) + batch_size - 1) // batch_size,
        "inserted_records": 0,
        "already_applied_records": 0,
        "batches_committed": 0,
        "last_committed_cursor": last_cursor,
        "status": "dry_run" if dry_run else "in_progress",
    }
    if dry_run:
        validation_engine = _build_engine(target_database_url)
        try:
            with validation_engine.connect() as connection:
                _reflect_targets(connection)
        finally:
            validation_engine.dispose()
        result["status"] = "dry_run_ready"
        result["planned_source_keys"] = [record.key for record in pending]
        return result

    engine = _build_engine(target_database_url)
    try:
        with engine.connect() as connection:
            _reflect_targets(connection)
        for offset in range(0, len(pending), batch_size):
            batch = pending[offset : offset + batch_size]
            batch_entries: list[dict[str, Any]] = []
            with engine.begin() as connection:
                tables = _reflect_targets(connection)
                for record in batch:
                    rows = _target_rows(record, mappings[record.key])
                    statuses = (
                        _insert_or_validate(
                            connection,
                            tables["v1_trips"],
                            {"trip_id": rows["trip"]["trip_id"]},
                            rows["trip"],
                        ),
                        _insert_or_validate(
                            connection,
                            tables["v1_trip_members"],
                            {
                                "trip_id": rows["member"]["trip_id"],
                                "user_id": rows["member"]["user_id"],
                            },
                            rows["member"],
                        ),
                        _insert_or_validate(
                            connection,
                            tables["v1_artifacts"],
                            {"artifact_id": rows["artifact"]["artifact_id"]},
                            rows["artifact"],
                        ),
                        _insert_or_validate(
                            connection,
                            tables["v1_artifact_versions"],
                            {"artifact_id": rows["artifact_version"]["artifact_id"], "version": 1},
                            rows["artifact_version"],
                        ),
                    )
                    status = "already_applied" if all(item == "already_applied" for item in statuses) else "migrated"
                    result[f"{'already_applied' if status == 'already_applied' else 'inserted'}_records"] += 1
                    batch_entries.append(_archive_entry(record, rows, status))

            for entry in batch_entries:
                existing_entries[entry["source_key"]] = entry
            archive["entries"] = [existing_entries[key] for key in sorted(existing_entries)]
            archive["updated_at"] = iso_now()
            archive["status"] = "in_progress"
            if archive_manifest_file is not None:
                write_json_atomic(archive_manifest_file, archive)

            committed_cursor = batch[-1].cursor
            state.update(
                {
                    "status": "in_progress",
                    "last_committed_cursor": committed_cursor,
                    "batches_committed": int(state.get("batches_committed") or 0) + 1,
                    "records_committed": int(state.get("records_committed") or 0) + len(batch),
                    "updated_at": iso_now(),
                }
            )
            if state_file is not None:
                write_json_atomic(state_file, state)
            result["batches_committed"] += 1
            result["last_committed_cursor"] = committed_cursor

        state["status"] = "complete"
        state["updated_at"] = iso_now()
        if state_file is not None:
            write_json_atomic(state_file, state)
        archive["status"] = "backfill_complete"
        archive["updated_at"] = iso_now()
        archive["source_fingerprint"] = inventory.get("source_fingerprint")
        archive["request_hash"] = request_hash
        if archive_manifest_file is not None:
            write_json_atomic(archive_manifest_file, archive)
        result["status"] = "complete"
        return result
    finally:
        engine.dispose()


def _query_scalar(connection: Connection, statement: Any) -> int:
    return int(connection.execute(statement).scalar_one())


def verify(
    *,
    target_database_url: str,
    inventory_file: Path,
    owner_mapping_file: Path,
    archive_manifest_file: Path,
    sessions_file: Path | None = None,
    share_links_file: Path | None = None,
    source_database_url: str | None = None,
) -> dict[str, Any]:
    """Reconcile counts, hashes, ownership, tenancy, and all target references."""

    inventory = _validate_inventory(read_json(inventory_file))
    records = _validate_source_snapshot(
        load_sources(
            sessions_file=sessions_file,
            share_links_file=share_links_file,
            source_database_url=source_database_url,
        ),
        inventory,
    )
    mappings, mapping_checksum = load_owner_mapping(owner_mapping_file)
    if mapping_checksum != inventory.get("owner_mapping_checksum"):
        raise MigrationError("owner mapping changed after inventory")
    archive = _load_archive(archive_manifest_file)
    entries = {str(entry.get("source_key")): entry for entry in archive["entries"]}
    issues: list[dict[str, Any]] = []
    expected_keys = {record.key for record in records}
    manifest_keys = set(entries)
    for key in sorted(expected_keys - manifest_keys):
        issues.append({"code": "manifest_entry_missing", "source_key": key})
    for key in sorted(manifest_keys - expected_keys):
        issues.append({"code": "manifest_orphan_entry", "source_key": key})

    counts: dict[str, int] = {"source_records": len(records), "manifest_entries": len(entries)}
    engine = _build_engine(target_database_url)
    try:
        with engine.connect() as connection:
            tables = _reflect_targets(connection)
            trip_ids = [str(entries[key]["target_trip_id"]) for key in expected_keys if key in entries]
            artifact_ids = [str(entries[key]["target_artifact_id"]) for key in expected_keys if key in entries]
            counts["target_trips"] = (
                _query_scalar(connection, select(func.count()).select_from(tables["v1_trips"]).where(tables["v1_trips"].c.trip_id.in_(trip_ids)))
                if trip_ids
                else 0
            )
            counts["target_artifacts"] = (
                _query_scalar(connection, select(func.count()).select_from(tables["v1_artifacts"]).where(tables["v1_artifacts"].c.artifact_id.in_(artifact_ids)))
                if artifact_ids
                else 0
            )
            counts["target_artifact_versions"] = (
                _query_scalar(connection, select(func.count()).select_from(tables["v1_artifact_versions"]).where(and_(tables["v1_artifact_versions"].c.artifact_id.in_(artifact_ids), tables["v1_artifact_versions"].c.version == 1)))
                if artifact_ids
                else 0
            )
            counts["target_owner_memberships"] = (
                _query_scalar(connection, select(func.count()).select_from(tables["v1_trip_members"]).where(and_(tables["v1_trip_members"].c.trip_id.in_(trip_ids), tables["v1_trip_members"].c.role == "owner")))
                if trip_ids
                else 0
            )

            trips = tables["v1_trips"]
            members = tables["v1_trip_members"]
            artifacts = tables["v1_artifacts"]
            versions = tables["v1_artifact_versions"]
            global_integrity = {
                "orphan_trip_members": _query_scalar(
                    connection,
                    select(func.count())
                    .select_from(members.outerjoin(trips, members.c.trip_id == trips.c.trip_id))
                    .where(trips.c.trip_id.is_(None)),
                ),
                "orphan_artifacts": _query_scalar(
                    connection,
                    select(func.count())
                    .select_from(artifacts.outerjoin(trips, artifacts.c.trip_id == trips.c.trip_id))
                    .where(trips.c.trip_id.is_(None)),
                ),
                "orphan_artifact_versions": _query_scalar(
                    connection,
                    select(func.count())
                    .select_from(
                        versions.outerjoin(
                            artifacts,
                            versions.c.artifact_id == artifacts.c.artifact_id,
                        )
                    )
                    .where(artifacts.c.artifact_id.is_(None)),
                ),
                "cross_tenant_members": _query_scalar(
                    connection,
                    select(func.count())
                    .select_from(members.join(trips, members.c.trip_id == trips.c.trip_id))
                    .where(members.c.tenant_id != trips.c.tenant_id),
                ),
                "cross_tenant_artifacts": _query_scalar(
                    connection,
                    select(func.count())
                    .select_from(artifacts.join(trips, artifacts.c.trip_id == trips.c.trip_id))
                    .where(artifacts.c.tenant_id != trips.c.tenant_id),
                ),
                "cross_tenant_artifact_versions": _query_scalar(
                    connection,
                    select(func.count())
                    .select_from(
                        versions.join(
                            artifacts,
                            versions.c.artifact_id == artifacts.c.artifact_id,
                        )
                    )
                    .where(versions.c.tenant_id != artifacts.c.tenant_id),
                ),
                "invalid_current_artifact_refs": _query_scalar(
                    connection,
                    select(func.count())
                    .select_from(
                        trips.outerjoin(
                            versions,
                            and_(
                                trips.c.current_artifact_id == versions.c.artifact_id,
                                trips.c.current_artifact_version == versions.c.version,
                            ),
                        )
                    )
                    .where(
                        and_(
                            trips.c.current_artifact_id.is_not(None),
                            versions.c.artifact_id.is_(None),
                        )
                    ),
                ),
            }
            counts.update(global_integrity)
            for code, count in global_integrity.items():
                if count:
                    issues.append({"code": code, "count": count})

            for record in records:
                entry = entries.get(record.key)
                owner = mappings.get(record.key)
                if entry is None or owner is None:
                    issues.append({"code": "owner_or_manifest_unresolved", "source_key": record.key})
                    continue
                rows = _target_rows(record, owner)
                trip = connection.execute(
                    select(tables["v1_trips"]).where(tables["v1_trips"].c.trip_id == rows["trip"]["trip_id"])
                ).mappings().first()
                member = connection.execute(
                    select(tables["v1_trip_members"]).where(
                        and_(
                            tables["v1_trip_members"].c.trip_id == rows["member"]["trip_id"],
                            tables["v1_trip_members"].c.user_id == rows["member"]["user_id"],
                        )
                    )
                ).mappings().first()
                artifact = connection.execute(
                    select(tables["v1_artifacts"]).where(tables["v1_artifacts"].c.artifact_id == rows["artifact"]["artifact_id"])
                ).mappings().first()
                version = connection.execute(
                    select(tables["v1_artifact_versions"]).where(
                        and_(
                            tables["v1_artifact_versions"].c.artifact_id == rows["artifact_version"]["artifact_id"],
                            tables["v1_artifact_versions"].c.version == 1,
                        )
                    )
                ).mappings().first()
                if trip is None or member is None or artifact is None or version is None:
                    issues.append({"code": "target_reference_missing", "source_key": record.key})
                    continue
                tenant_values = {trip["tenant_id"], member["tenant_id"], artifact["tenant_id"], version["tenant_id"]}
                if tenant_values != {owner.tenant_id}:
                    issues.append({"code": "cross_tenant_reference", "source_key": record.key})
                if trip["owner_id"] != owner.owner_id or member["user_id"] != owner.owner_id or member["role"] != "owner":
                    issues.append({"code": "owner_mismatch", "source_key": record.key})
                if artifact["trip_id"] != trip["trip_id"]:
                    issues.append({"code": "artifact_trip_orphan", "source_key": record.key})
                if trip["current_artifact_id"] != artifact["artifact_id"] or trip["current_artifact_version"] != 1:
                    issues.append({"code": "current_artifact_ref_mismatch", "source_key": record.key})
                if artifact["artifact_type"] != ARTIFACT_TYPE or version["status"] != "published":
                    issues.append({"code": "imported_archive_contract_mismatch", "source_key": record.key})
                actual_content_checksum = sha256_json(version["content"])
                expected_checksum = sha256_json(rows["artifact_version"]["content"])
                if not hmac.compare_digest(actual_content_checksum, expected_checksum):
                    issues.append({"code": "target_content_hash_mismatch", "source_key": record.key})
                if not hmac.compare_digest(str(entry.get("source_checksum") or ""), record.source_checksum):
                    issues.append({"code": "manifest_source_hash_mismatch", "source_key": record.key})
                if not hmac.compare_digest(str(entry.get("target_content_checksum") or ""), actual_content_checksum):
                    issues.append({"code": "manifest_target_hash_mismatch", "source_key": record.key})
    finally:
        engine.dispose()

    if any(value != len(records) for key, value in counts.items() if key.startswith("target_")):
        issues.append({"code": "reconciliation_count_mismatch", "counts": counts})
    report = {
        "schema": VERIFY_SCHEMA,
        "schema_version": SCHEMA_VERSION,
        "generated_at": iso_now(),
        "inventory_checksum": sha256_json(inventory),
        "archive_manifest_checksum": sha256_json(archive),
        "counts": counts,
        "source_fingerprint": inventory.get("source_fingerprint"),
        "issues": issues,
        "blocking_issue_count": len(issues),
        "passed": not issues,
    }
    return report
