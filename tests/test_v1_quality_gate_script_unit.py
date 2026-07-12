"""Unit tests for the unified RoutePilot V1 delivery gate."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def load_gate_module():
    """Load the script as a module without changing package layout."""

    path = Path(__file__).resolve().parents[1] / "scripts" / "v1_quality_gate.py"
    spec = importlib.util.spec_from_file_location("v1_quality_gate", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_gate_manifest_covers_every_v1_quality_area() -> None:
    gate = load_gate_module()
    areas = {command.area for command in gate.build_gate_commands()}
    assert areas == {
        "contracts",
        "backend",
        "a2a",
        "rag",
        "runtime",
        "web",
        "security",
        "migration",
    }
    assert any(command.argv[-1] == "build" for command in gate.build_gate_commands())
    assert not any(
        command.argv[-1] == "build" for command in gate.build_gate_commands(include_web_build=False)
    )
    flattened = " ".join(
        argument for command in gate.build_gate_commands() for argument in command.argv
    )
    assert "tests/providers" in flattened
    assert "test_v1_artifact_workflow_unit.py" in flattened
    assert "test_v1_error_boundary_unit.py" in flattened
    assert "tests/migration_v1" in flattened
    assert "mypy" in flattened


def test_offline_migration_validator_fails_closed() -> None:
    gate = load_gate_module()
    complete = """
      CREATE TABLE v1_trips (); CREATE TABLE v1_outbox_events ();
      CREATE TABLE v1_run_public_events (); CREATE TABLE v1_knowledge_chunks ();
      ALTER TABLE v1_trips ENABLE ROW LEVEL SECURITY;
      CREATE EXTENSION IF NOT EXISTS vector;
      CREATE TABLE v1_agent_tasks (); CREATE TABLE v1_agent_dispatch_inbox ();
      CREATE TABLE v1_agent_task_events ();
      ALTER TABLE v1_runs ADD COLUMN execution_lease_owner VARCHAR(128);
      ALTER TABLE v1_agent_tasks ADD COLUMN execution_input JSONB;
      ALTER TABLE v1_agent_tasks ADD COLUMN execution_lease_owner VARCHAR(128);
      ALTER TABLE v1_runs ADD COLUMN base_artifact_id VARCHAR(96);
      ALTER TABLE v1_runs ADD COLUMN pending_input JSONB;
      CREATE TABLE v1_shares (); CREATE TABLE v1_share_snapshots ();
      CREATE FUNCTION routepilot_resolve_share_tenant() RETURNS TEXT;
    """
    assert gate.validate_offline_migration_sql(complete) == []
    assert "RLS enablement" in gate.validate_offline_migration_sql(
        complete.replace("ENABLE ROW LEVEL SECURITY", "")
    )


def test_offline_migration_validator_recognizes_a2a_revision_tables() -> None:
    gate = load_gate_module()
    sql = """
      -- Running upgrade 20260712_0006 -> 20260712_0007
      CREATE TABLE v1_trips (); CREATE TABLE v1_outbox_events ();
      CREATE TABLE v1_run_public_events (); CREATE TABLE v1_knowledge_chunks ();
      ALTER TABLE v1_trips ENABLE ROW LEVEL SECURITY;
      CREATE EXTENSION IF NOT EXISTS vector;
      CREATE TABLE v1_agent_tasks (); CREATE TABLE v1_agent_dispatch_inbox ();
      CREATE TABLE v1_agent_task_events ();
      ALTER TABLE v1_runs ADD COLUMN execution_lease_owner VARCHAR(128);
      ALTER TABLE v1_agent_tasks ADD COLUMN execution_input JSONB;
      ALTER TABLE v1_agent_tasks ADD COLUMN execution_lease_owner VARCHAR(128);
      ALTER TABLE v1_runs ADD COLUMN base_artifact_id VARCHAR(96);
      ALTER TABLE v1_runs ADD COLUMN pending_input JSONB;
      CREATE TABLE v1_shares (); CREATE TABLE v1_share_snapshots ();
      CREATE FUNCTION routepilot_resolve_share_tenant() RETURNS TEXT;
    """
    assert gate.validate_offline_migration_sql(sql) == []
    assert "A2A inbox deduplication" in gate.validate_offline_migration_sql(
        sql.replace("CREATE TABLE v1_agent_dispatch_inbox ();", "")
    )
    assert "Product Run execution fencing" in gate.validate_offline_migration_sql(
        sql.replace(
            "ALTER TABLE v1_runs ADD COLUMN execution_lease_owner VARCHAR(128);",
            "",
        )
    )
    assert "A2A Task execution fencing" in gate.validate_offline_migration_sql(
        sql.replace(
            "ALTER TABLE v1_agent_tasks ADD COLUMN execution_lease_owner VARCHAR(128);",
            "",
        )
    )
