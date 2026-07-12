"""Static contract for the durable A2A Alembic revision."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "deploy/migrations/versions/20260712_0007_routepilot_a2a_tasks.py"
RECOVERY_MIGRATION = ROOT / "deploy/migrations/versions/20260712_0009_a2a_execution_recovery.py"


def test_a2a_migration_contains_scoped_inbox_cas_events_and_rls():
    source = MIGRATION.read_text(encoding="utf-8")
    assert 'down_revision = "20260712_0006"' in source
    for table_name in (
        "v1_agent_tasks",
        "v1_agent_dispatch_inbox",
        "v1_agent_task_events",
    ):
        assert table_name in source
    assert "uq_v1_agent_tasks_dispatch" in source
    assert "version >= 1" in source
    assert "event_seq" in source
    assert "octet_length(task_proto)" in source
    assert "octet_length(event_proto)" in source
    assert "octet_length(invocation::text)" in source
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "current_setting('routepilot.tenant_id', true)" in source


def test_a2a_recovery_migration_follows_run_lease_and_fences_execution():
    source = RECOVERY_MIGRATION.read_text(encoding="utf-8")
    assert 'down_revision = "20260712_0008"' in source
    for marker in (
        "execution_input",
        "execution_lease_owner",
        "execution_lease_until",
        "execution_attempt",
        "ix_v1_agent_tasks_recoverable_execution",
        "execution_attempt >= 0",
        "execution_input::text",
    ):
        assert marker in source
