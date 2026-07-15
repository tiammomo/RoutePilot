"""Run the unified RoutePilot V1 contract-to-delivery quality gate."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True, slots=True)
class GateCommand:
    """One deterministic command in a named V1 quality area."""

    area: str
    argv: tuple[str, ...]
    cwd: Path = REPOSITORY_ROOT


def report_github_error(*, title: str, message: str) -> None:
    """Emit a safe workflow annotation while preserving normal local output."""

    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    escaped_title = title.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    escaped_message = (
        message.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    )
    print(f"::error title={escaped_title}::{escaped_message}", flush=True)


def build_gate_commands(*, include_web_build: bool = True) -> tuple[GateCommand, ...]:
    """Return the single reviewed command manifest used locally and in CI."""

    python = sys.executable
    commands = [
        GateCommand(
            "contracts",
            (
                python,
                "-m",
                "pytest",
                "-q",
                "tests/contract",
            ),
        ),
        GateCommand(
            "backend",
            (
                python,
                "-m",
                "pytest",
                "-q",
                "tests/test_v1_run_control_plane_unit.py",
                "tests/test_v1_a2a_cancel_propagation_unit.py",
                "tests/test_v1_oidc_auth_unit.py",
                "tests/test_v1_outbox_unit.py",
                "tests/test_v1_external_worker_unit.py",
                "tests/test_v1_replan_resume_unit.py",
                "tests/test_v1_share_service_unit.py",
                "tests/test_v1_execution_lease_postgres_integration.py",
                "tests/test_v1_redis_worker_integration.py",
                "tests/test_v1_artifact_workflow_unit.py",
                "tests/test_v1_artifact_postgres_integration.py",
                "tests/test_v1_error_boundary_unit.py",
                "tests/test_app_bootstrap_unit.py",
                "tests/test_clean_workspace_script_unit.py",
                "tests/test_v1_backup_tool_unit.py",
                "tests/test_v1_quality_gate_script_unit.py",
            ),
        ),
        GateCommand(
            "docs",
            (python, "-m", "pytest", "-q", "tests/test_documentation_gate_unit.py"),
        ),
        GateCommand("docs", (python, "-m", "ruff", "check", "scripts/check_documentation.py")),
        GateCommand("docs", (python, "scripts/check_documentation.py")),
        GateCommand(
            "backend",
            (
                python,
                "-m",
                "ruff",
                "check",
                "backend/moyuan_web",
                "scripts/v1_backup.py",
            ),
        ),
        GateCommand(
            "backend",
            (
                python,
                "-m",
                "mypy",
                "backend/moyuan_web",
                "agent/travel_agent/a2a",
                "agent/travel_agent/providers",
                "agent/travel_agent/rag",
                "agent/travel_agent/runtime_v2",
                "scripts/v1_backup.py",
                "scripts/v1_knowledge_base.py",
                "--config-file",
                "pyproject.toml",
            ),
        ),
        GateCommand("a2a", (python, "-m", "pytest", "-q", "tests/a2a")),
        GateCommand("a2a", (python, "-m", "pytest", "-q", "tests/providers")),
        GateCommand(
            "rag",
            (
                python,
                "-m",
                "pytest",
                "-q",
                "tests/rag/test_rag_core_unit.py",
                "tests/rag/test_embedding_provider_unit.py",
                "tests/rag/test_rag_retrieval_quality_gate.py",
                "tests/rag/test_rag_api_contract.py",
                "tests/rag/test_curated_knowledge_bundle.py",
            ),
        ),
        GateCommand(
            "rag",
            (
                python,
                "-m",
                "ruff",
                "check",
                "agent/travel_agent/rag",
                "scripts/v1_knowledge_base.py",
            ),
        ),
        GateCommand(
            "runtime",
            (
                python,
                "-m",
                "pytest",
                "-q",
                "tests/runtime_v2",
                "tests/test_v1_v2_vertical_slice_unit.py",
            ),
        ),
        GateCommand(
            "web",
            ("npm", "run", "typecheck"),
            REPOSITORY_ROOT / "apps" / "web",
        ),
        GateCommand(
            "web",
            ("npm", "run", "test"),
            REPOSITORY_ROOT / "apps" / "web",
        ),
        GateCommand(
            "security",
            (
                python,
                "-m",
                "pytest",
                "-q",
                "tests/test_v1_oidc_auth_unit.py",
                "tests/test_v1_error_boundary_unit.py",
                "tests/test_app_bootstrap_unit.py",
            ),
        ),
        GateCommand(
            "migration",
            (
                python,
                "-m",
                "pytest",
                "-q",
                "tests/migration_v1",
                "tests/rag/test_rag_migration_contract.py",
            ),
        ),
    ]
    if include_web_build:
        commands.append(
            GateCommand(
                "web",
                ("npm", "run", "build"),
                REPOSITORY_ROOT / "apps" / "web",
            )
        )
    return tuple(commands)


def validate_offline_migration_sql(sql: str) -> list[str]:
    """Return missing safety markers from an Alembic offline SQL rendering."""

    normalized = " ".join(sql.lower().replace('"', "").split())
    required = {
        "trip aggregate": "create table v1_trips",
        "transactional outbox": "create table v1_outbox_events",
        "public event projection": "create table v1_run_public_events",
        "RAG chunks": "create table v1_knowledge_chunks",
        "RLS enablement": "enable row level security",
        "pgvector capability": "create extension if not exists vector",
        "A2A durable tasks": "create table v1_agent_tasks",
        "A2A inbox deduplication": "create table v1_agent_dispatch_inbox",
        "A2A task event replay": "create table v1_agent_task_events",
        "Product Run execution fencing": ("alter table v1_runs add column execution_lease_owner"),
        "A2A Task execution fencing": (
            "alter table v1_agent_tasks add column execution_lease_owner"
        ),
        "A2A typed-input recovery": ("alter table v1_agent_tasks add column execution_input"),
        "Product Run pinned replan": "alter table v1_runs add column base_artifact_id",
        "Product Run typed-input recovery": "alter table v1_runs add column pending_input",
        "secure public shares": "create table v1_shares",
        "immutable share snapshots": "create table v1_share_snapshots",
        "share capability resolver": "create function routepilot_resolve_share_tenant",
        "knowledge document CAS": "alter table v1_knowledge_documents add column version",
        "knowledge lifecycle audit": "create table v1_knowledge_document_commands",
    }
    return [name for name, marker in required.items() if marker not in normalized]


def run_migration_gate() -> bool:
    """Render every migration offline and assert the V1 safety-critical DDL."""

    environment = os.environ.copy()
    environment["MOYUAN_POSTGRES_DSN"] = (
        "postgresql://routepilot_migrator:offline-only@127.0.0.1/routepilot"
    )
    result = subprocess.run(
        (
            sys.executable,
            "-m",
            "alembic",
            "-c",
            "migrations/alembic.ini",
            "upgrade",
            "head",
            "--sql",
        ),
        cwd=REPOSITORY_ROOT / "deploy",
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        sys.stderr.write(result.stderr)
        return False
    missing = validate_offline_migration_sql(result.stdout)
    if missing:
        print(f"[migration] missing offline SQL markers: {', '.join(missing)}", file=sys.stderr)
        return False
    print("[migration] offline SQL rendered and safety markers verified")
    return True


def run_commands(commands: Sequence[GateCommand], selected: set[str]) -> list[str]:
    """Run all selected areas and return names of failed areas."""

    failures: list[str] = []
    for command in commands:
        if command.area not in selected:
            continue
        rendered = " ".join(command.argv)
        print(f"[{command.area}] {rendered}", flush=True)
        result = subprocess.run(command.argv, cwd=command.cwd, check=False)
        if result.returncode:
            failures.append(command.area)
            report_github_error(
                title=f"RoutePilot {command.area} gate failed",
                message=f"Command exited with {result.returncode}: {rendered}",
            )
    if "migration" in selected and not run_migration_gate():
        failures.append("migration")
        report_github_error(
            title="RoutePilot migration rendering failed",
            message="Alembic offline SQL did not satisfy the V1 safety contract.",
        )
    return sorted(set(failures))


def main() -> int:
    """CLI entrypoint for local development and GitHub Actions."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--only",
        action="append",
        choices=(
            "contracts",
            "backend",
            "a2a",
            "rag",
            "runtime",
            "web",
            "security",
            "migration",
            "docs",
        ),
        help="Run only one area; repeat to select multiple areas.",
    )
    parser.add_argument(
        "--skip-web-build",
        action="store_true",
        help="Keep web typecheck/tests but omit the production build (local fast loop only).",
    )
    args = parser.parse_args()
    selected = set(
        args.only
        or (
            "contracts",
            "backend",
            "a2a",
            "rag",
            "runtime",
            "web",
            "security",
            "migration",
            "docs",
        )
    )
    failures = run_commands(
        build_gate_commands(include_web_build=not args.skip_web_build),
        selected,
    )
    if failures:
        print(f"RoutePilot V1 quality gate failed: {', '.join(failures)}", file=sys.stderr)
        report_github_error(
            title="RoutePilot V1 quality gate failed",
            message=f"Failed areas: {', '.join(failures)}",
        )
        return 1
    print("RoutePilot V1 quality gate passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
