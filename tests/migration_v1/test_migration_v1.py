"""Repeatability, resume, redaction, and reconciliation tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Column, ForeignKey, Integer, JSON, MetaData, String, Table, Text, create_engine, func, select
from backend.moyuan_web.v1.sql_tables import (
    artifact_versions_table,
    artifacts_table,
    metadata,
    trip_members_table,
    trips_table,
)
from scripts.migration_v1 import core


# The source schema is deliberately local test data.  Production migration code
# discovers old installations through SQL reflection and must not retain an
# import dependency on the removed application.
legacy_metadata = MetaData()
sessions_table = Table(
    "sessions",
    legacy_metadata,
    Column("session_id", String(128), primary_key=True),
    Column("created_at", String(64), nullable=False),
    Column("last_active", String(64), nullable=False),
    Column("message_count", Integer, nullable=False),
    Column("name", String(120), nullable=False),
    Column("model_id", String(128), nullable=False),
    Column("messages", JSON, nullable=False),
    Column("user_preferences", JSON, nullable=False),
)
session_messages_table = Table(
    "session_messages",
    legacy_metadata,
    Column("message_id", Integer, primary_key=True, autoincrement=True),
    Column("session_id", String(128), ForeignKey("sessions.session_id", ondelete="CASCADE"), nullable=False),
    Column("sequence", Integer, nullable=False),
    Column("role", String(32), nullable=False),
    Column("content", Text, nullable=False),
    Column("reasoning", Text),
    Column("model_content", Text),
    Column("diagnostics", JSON),
    Column("timestamp", String(64), nullable=False),
)
share_links_table = Table(
    "share_links",
    legacy_metadata,
    Column("share_id", String(32), primary_key=True),
    Column("title", String(100), nullable=False),
    Column("content", Text, nullable=False),
    Column("html_content", Text, nullable=False),
    Column("delivery_bundle", JSON),
    Column("created_at", String(64), nullable=False),
)


def _write(path: Path, payload: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _fixtures(tmp_path: Path, *, records: int = 3) -> tuple[Path, Path, Path, str]:
    sessions = {
        f"session-{index}": {
            "session_id": f"session-{index}",
            "created_at": f"2026-07-0{index + 1}T00:00:00+00:00",
            "name": f"北京行程 {index}",
            "messages": [
                {"role": "user", "content": "北京两日游", "reasoning": "private chain"},
                {
                    "role": "assistant",
                    "content": "行程完成 api_key=super-secret-value",
                    "reasoning": "must never migrate",
                    "tool_result": {"raw": "private"},
                    "diagnostics": {
                        "traceback": "private stack",
                        "artifact": {
                            "itinerary": {"plan_id": f"plan-{index}"},
                            "tool_raw_result": "hidden",
                        },
                    },
                },
            ],
        }
        for index in range(records)
    }
    shares = {
        "weak-token-01": {
            "share_id": "weak-token-01",
            "created_at": "2026-07-04T00:00:00+00:00",
            "title": "旧分享",
            "content": "公开行程 Bearer abcdefghijklmnop",
            "html_content": "<script>steal()</script>",
            "delivery_bundle": {
                "artifact": {"itinerary": {"plan_id": "share-plan"}},
                "htmlContent": "<b>not migrated</b>",
            },
        }
    }
    mapping = {
        "schema": core.MAPPING_SCHEMA,
        "mappings": {
            **{
                f"session:session-{index}": {
                    "tenant_id": "tenant-a",
                    "owner_id": "owner-a",
                }
                for index in range(records)
            },
            "share:weak-token-01": {"tenant_id": "tenant-a", "owner_id": "owner-a"},
        },
    }
    sessions_path = _write(tmp_path / "sessions.json", sessions)
    shares_path = _write(tmp_path / "shares.json", shares)
    mapping_path = _write(tmp_path / "owners.json", mapping)
    database_url = f"sqlite:///{tmp_path / 'target.sqlite3'}"
    engine = create_engine(database_url)
    try:
        metadata.create_all(engine)
    finally:
        engine.dispose()
    return sessions_path, shares_path, mapping_path, database_url


def _inventory(
    tmp_path: Path,
    sessions_path: Path,
    shares_path: Path,
    mapping_path: Path,
) -> Path:
    report = core.build_inventory(
        sessions_file=sessions_path,
        share_links_file=shares_path,
        owner_mapping_file=mapping_path,
        file_data_roots=[tmp_path],
    )
    assert report["blocking_issues"] == []
    return _write(tmp_path / "inventory.json", report)


def test_public_projection_removes_reasoning_tool_errors_html_and_secrets(tmp_path: Path) -> None:
    sessions_path, shares_path, mapping_path, _ = _fixtures(tmp_path, records=1)
    records = core.load_sources(
        sessions_file=sessions_path,
        share_links_file=shares_path,
        source_database_url=None,
    )

    serialized = core.canonical_json([record.public_content for record in records])
    lowered = serialized.lower()
    assert "private chain" not in lowered
    assert "must never migrate" not in lowered
    assert "tool_result" not in lowered
    assert "traceback" not in lowered
    assert "<script>" not in lowered
    assert "super-secret-value" not in lowered
    assert "abcdefghijklmnop" not in lowered
    assert "weak-token-01" not in lowered
    assert "[redacted]" in lowered

    inventory = core.build_inventory(
        sessions_file=sessions_path,
        share_links_file=shares_path,
        owner_mapping_file=mapping_path,
    )
    assert inventory["source_counts"] == {"session": 1, "share": 1}


def test_backfill_is_idempotent_and_verify_reconciles_sqlite(tmp_path: Path) -> None:
    sessions_path, shares_path, mapping_path, database_url = _fixtures(tmp_path)
    inventory_path = _inventory(tmp_path, sessions_path, shares_path, mapping_path)
    archive_path = tmp_path / "archive.json"
    state_path = tmp_path / "state.json"

    dry_run = core.backfill(
        target_database_url=database_url,
        inventory_file=inventory_path,
        owner_mapping_file=mapping_path,
        sessions_file=sessions_path,
        share_links_file=shares_path,
        archive_manifest_file=archive_path,
        state_file=state_path,
        batch_size=2,
    )
    assert dry_run["status"] == "dry_run_ready"
    assert not archive_path.exists()
    assert not state_path.exists()

    applied = core.backfill(
        target_database_url=database_url,
        inventory_file=inventory_path,
        owner_mapping_file=mapping_path,
        sessions_file=sessions_path,
        share_links_file=shares_path,
        archive_manifest_file=archive_path,
        state_file=state_path,
        batch_size=2,
        dry_run=False,
    )
    assert applied["status"] == "complete"
    assert applied["inserted_records"] == 4
    assert applied["batches_committed"] == 2

    repeated = core.backfill(
        target_database_url=database_url,
        inventory_file=inventory_path,
        owner_mapping_file=mapping_path,
        sessions_file=sessions_path,
        share_links_file=shares_path,
        archive_manifest_file=archive_path,
        state_file=state_path,
        batch_size=1,
        dry_run=False,
    )
    assert repeated["pending_count"] == 0
    assert repeated["inserted_records"] == 0

    engine = create_engine(database_url)
    try:
        with engine.connect() as connection:
            assert connection.execute(select(func.count()).select_from(trips_table)).scalar_one() == 4
            assert connection.execute(select(func.count()).select_from(trip_members_table)).scalar_one() == 4
            assert connection.execute(select(func.count()).select_from(artifacts_table)).scalar_one() == 4
            assert connection.execute(select(func.count()).select_from(artifact_versions_table)).scalar_one() == 4
            contents = connection.execute(select(artifact_versions_table.c.content)).scalars().all()
    finally:
        engine.dispose()
    serialized = core.canonical_json(contents).lower()
    assert "super-secret-value" not in serialized
    assert "reasoning" not in serialized
    assert "tool_result" not in serialized
    assert "weak-token-01" not in serialized

    report = core.verify(
        target_database_url=database_url,
        inventory_file=inventory_path,
        owner_mapping_file=mapping_path,
        archive_manifest_file=archive_path,
        sessions_file=sessions_path,
        share_links_file=shares_path,
    )
    assert report["passed"] is True
    assert report["counts"]["source_records"] == 4
    assert report["blocking_issue_count"] == 0


def test_backfill_resumes_after_a_committed_batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    sessions_path, shares_path, mapping_path, database_url = _fixtures(tmp_path, records=2)
    inventory_path = _inventory(tmp_path, sessions_path, shares_path, mapping_path)
    archive_path = tmp_path / "archive.json"
    state_path = tmp_path / "state.json"
    original = core._insert_or_validate
    calls = 0

    def fail_after_first_record(*args: Any, **kwargs: Any) -> str:
        nonlocal calls
        calls += 1
        if calls == 5:
            raise core.MigrationError("injected second-batch failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(core, "_insert_or_validate", fail_after_first_record)
    with pytest.raises(core.MigrationError, match="injected"):
        core.backfill(
            target_database_url=database_url,
            inventory_file=inventory_path,
            owner_mapping_file=mapping_path,
            sessions_file=sessions_path,
            share_links_file=shares_path,
            archive_manifest_file=archive_path,
            state_file=state_path,
            batch_size=1,
            dry_run=False,
        )
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["records_committed"] == 1
    committed_cursor = state["last_committed_cursor"]

    monkeypatch.setattr(core, "_insert_or_validate", original)
    resumed = core.backfill(
        target_database_url=database_url,
        inventory_file=inventory_path,
        owner_mapping_file=mapping_path,
        sessions_file=sessions_path,
        share_links_file=shares_path,
        archive_manifest_file=archive_path,
        state_file=state_path,
        batch_size=1,
        dry_run=False,
    )
    assert resumed["resume_from_cursor"] == committed_cursor
    assert resumed["status"] == "complete"
    assert json.loads(state_path.read_text(encoding="utf-8"))["status"] == "complete"


def test_unresolved_owner_and_changed_snapshot_fail_closed(tmp_path: Path) -> None:
    sessions_path, shares_path, mapping_path, database_url = _fixtures(tmp_path, records=1)
    incomplete_mapping = {
        "schema": core.MAPPING_SCHEMA,
        "mappings": {"session:session-0": {"tenant_id": "tenant-a", "owner_id": "owner-a"}},
    }
    incomplete_path = _write(tmp_path / "incomplete.json", incomplete_mapping)
    unresolved = core.build_inventory(
        sessions_file=sessions_path,
        share_links_file=shares_path,
        owner_mapping_file=incomplete_path,
    )
    assert unresolved["owner_unresolved"] == ["share:weak-token-01"]

    inventory_path = _inventory(tmp_path, sessions_path, shares_path, mapping_path)
    payload = json.loads(sessions_path.read_text(encoding="utf-8"))
    payload["session-0"]["messages"][1]["content"] = "source changed"
    _write(sessions_path, payload)
    with pytest.raises(core.MigrationError, match="high-water"):
        core.backfill(
            target_database_url=database_url,
            inventory_file=inventory_path,
            owner_mapping_file=mapping_path,
            sessions_file=sessions_path,
            share_links_file=shares_path,
            archive_manifest_file=tmp_path / "archive.json",
            state_file=tmp_path / "state.json",
        )


def test_inventory_scans_normalized_legacy_sql_tables(tmp_path: Path) -> None:
    source_url = f"sqlite:///{tmp_path / 'legacy.sqlite3'}"
    engine = create_engine(source_url)
    try:
        legacy_metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                sessions_table.insert().values(
                    session_id="sql-session",
                    created_at="2026-07-01T00:00:00+00:00",
                    last_active="2026-07-01T00:00:00+00:00",
                    message_count=1,
                    name="SQL legacy",
                    model_id="legacy",
                    messages=[],
                    user_preferences={},
                )
            )
            connection.execute(
                session_messages_table.insert().values(
                    session_id="sql-session",
                    sequence=1,
                    role="assistant",
                    content="normalized public answer",
                    reasoning="hidden reasoning",
                    model_content="hidden raw model output",
                    diagnostics={"tool_result": "hidden"},
                    timestamp="2026-07-01T00:01:00+00:00",
                )
            )
            connection.execute(
                share_links_table.insert().values(
                    share_id="sql-weak-token",
                    title="SQL share",
                    content="public share",
                    html_content="<script>hidden</script>",
                    delivery_bundle={},
                    created_at="2026-07-01T00:02:00+00:00",
                )
            )
    finally:
        engine.dispose()

    mapping_path = _write(
        tmp_path / "sql-owner.json",
        {
            "schema": core.MAPPING_SCHEMA,
            "mappings": {
                "session:sql-session": {"tenant_id": "tenant-sql", "owner_id": "owner-sql"},
                "share:sql-weak-token": {"tenant_id": "tenant-sql", "owner_id": "owner-sql"},
            },
        },
    )
    inventory = core.build_inventory(
        source_database_url=source_url,
        owner_mapping_file=mapping_path,
    )
    records = core.load_sources(
        sessions_file=None,
        share_links_file=None,
        source_database_url=source_url,
    )

    assert inventory["source_counts"] == {"session": 1, "share": 1}
    serialized = core.canonical_json([record.public_content for record in records]).lower()
    assert "normalized public answer" in serialized
    assert "hidden reasoning" not in serialized
    assert "hidden raw model output" not in serialized
    assert "sql-weak-token" not in serialized
