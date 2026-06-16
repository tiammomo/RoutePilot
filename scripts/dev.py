"""Cross-platform local task entrypoint for development and infra checks."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Sequence, TypedDict

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPO_ROOT / "frontend"
BACKEND_ROOT = REPO_ROOT / "backend"
COMPOSE_FILE = REPO_ROOT / "deploy" / "compose" / "compose.yaml"
BACKEND_DOCKERFILE = REPO_ROOT / "deploy" / "docker" / "backend.Dockerfile"
FRONTEND_DOCKERFILE = REPO_ROOT / "deploy" / "docker" / "frontend.Dockerfile"
DEFAULT_BASE_URL = "http://localhost:38083"
DEFAULT_GIT_SHA = "local"
DEFAULT_GIT_REF = "refs/heads/main"
DEFAULT_OWNER = "local"
DEFAULT_PYTHON_BASE_IMAGE = "python:3.13-slim"
DEFAULT_NODE_BASE_IMAGE = "node:22-alpine"
DEFAULT_BACKEND_HOST = "0.0.0.0"
DEFAULT_BACKEND_PORT = 38083
DEFAULT_BENCHMARK_OUTPUT_DIR = "docs/benchmarks"
DEFAULT_GOLDEN_DATASET = "tests/golden/agent_react_golden.json"
DEFAULT_GOLDEN_REPORT = "docs/benchmarks/agent_golden_eval_latest.json"
DEFAULT_BENCHMARK_REPORT = "docs/benchmarks/agent_benchmark_latest.json"
DEFAULT_BENCHMARK_BASELINE_REPORT = "docs/benchmarks/agent_benchmark_baseline.json"
DEFAULT_BENCHMARK_TREND_REPORT = "docs/benchmarks/agent_benchmark_trend_latest.md"
DEFAULT_MIN_GOLDEN_PASS_RATE = "0.0"
DEFAULT_MAX_GOLDEN_HALLUCINATION_RATE = "0.05"
DEFAULT_MIN_BENCHMARK_SUCCESS_RATE = "0.60"
DEFAULT_MAX_BENCHMARK_HALLUCINATION_RATE = "0.05"
DEFAULT_MAX_BENCHMARK_FALLBACK_STEPS_TOTAL = "5"
DEFAULT_MAX_SUCCESS_RATE_REGRESSION = "0.05"
DEFAULT_MAX_HALLUCINATION_RATE_REGRESSION = "0.02"
DEFAULT_MAX_FALLBACK_STEPS_REGRESSION = "2"
BACKEND_RUNTIME_TEST_TARGETS = (
    "tests/test_agent_runtime_phase1_unit.py",
    "tests/test_agent_subagent_phase2_unit.py",
    "tests/test_runtime_flow_contract_unit.py",
    "tests/test_runtime_source_adapters_unit.py",
    "tests/test_runtime_event_emitters_unit.py",
    "tests/test_runtime_contract_audit_script_unit.py",
    "tests/test_chat_stream_local.py",
    "tests/test_chat_service_health_metrics_unit.py",
    "tests/test_langchain_1x_agent_unit.py",
)
BACKEND_OPS_TEST_TARGETS = (
    "tests/test_runtime_data_lifecycle_unit.py",
    "tests/test_runtime_doctor_unit.py",
    "tests/test_runtime_ops_contracts_unit.py",
    "tests/test_export_openapi_snapshot_script_unit.py",
    "tests/test_export_sse_contract_snapshot_script_unit.py",
    "tests/test_export_runtime_doctor_snapshot_script_unit.py",
    "tests/test_export_release_manifest_script_unit.py",
    "tests/test_release_harness_scorecard_script_unit.py",
    "tests/test_export_support_bundle_script_unit.py",
    "tests/test_observability_assets_unit.py",
)


class BackendTestSlice(TypedDict):
    """Static pytest slice definition used by the local dev entrypoint."""

    targets: tuple[str, ...]
    marker: str | None


BACKEND_TEST_SLICES: dict[str, BackendTestSlice] = {
    "unit": {
        "targets": ("tests",),
        "marker": "unit and not local and not external_api",
    },
    "local": {
        "targets": ("tests",),
        "marker": "local and not external_api",
    },
    "runtime": {
        "targets": BACKEND_RUNTIME_TEST_TARGETS,
        "marker": None,
    },
    "ops": {
        "targets": BACKEND_OPS_TEST_TARGETS,
        "marker": None,
    },
    "all": {
        "targets": ("tests",),
        "marker": None,
    },
}
STATIC_TARGETS = (
    "scripts/dev.py",
    "scripts/bootstrap.py",
    "scripts/export_openapi_snapshot.py",
    "scripts/export_runtime_doctor_snapshot.py",
    "scripts/export_release_manifest.py",
    "scripts/release_harness_scorecard.py",
    "scripts/runtime_contract_audit.py",
    "scripts/runtime_ops_contracts.py",
    "scripts/skills_market_audit.py",
    "scripts/export_support_bundle.py",
    "scripts/export_sse_contract_snapshot.py",
    "scripts/runtime_backup.py",
    "scripts/runtime_data_utils.py",
    "scripts/runtime_doctor.py",
    "scripts/runtime_prune.py",
    "scripts/runtime_restore.py",
    "backend/moyuan_web/app_meta.py",
    "backend/moyuan_web/main.py",
    "backend/moyuan_web/middleware/__init__.py",
    "backend/moyuan_web/observability.py",
    "backend/moyuan_web/routes/chat.py",
    "backend/moyuan_web/routes/health.py",
    "backend/moyuan_web/services/share_service.py",
    "backend/moyuan_web/startup_checks.py",
)
HELP_TEXT = """Usage:
  python scripts/dev.py <task> [options]

Tasks:
  help                   Show this help.
  backend-dev            Run the FastAPI app locally with repo Python.
  backend-test           Run a controlled backend pytest slice or explicit tests/ paths.
  backend-unit           Run backend unit tests.
  backend-local          Run backend local smoke tests.
  frontend-dev           Run the frontend dev server from the repo root.
  frontend-lint          Run frontend type/lint checks.
  frontend-test          Run frontend unit tests.
  frontend-build         Build the frontend.
  test                   Run backend + frontend verification slices.
  ruff                   Run local Ruff checks on infra/runtime targets.
  mypy                   Run local mypy checks on infra/runtime targets.
  docstring              Run Python docstring audit.
  complexity             Run hotspot complexity budget gate.
  decision-records       Run ADR / RFC / design-review audit.
  skills-market          Run the governed skills market audit.
  runtime-contracts      Run the typed runtime seam audit.
  runtime-doctor         Run runtime diagnostics with optional JSON/strict modes.
  runtime-backup         Create a runtime backup archive with controlled options.
  runtime-restore        Restore runtime data from a backup archive.
  runtime-prune          Prune runtime data and checkpoint maintenance artifacts.
  agent-replay           Replay an agent session from checkpoint storage.
  runtime-maintenance    Run backup, runtime-doctor, and runtime-prune as one flow.
  checkpoint-maintenance Run checkpoint prune/replay/doctor as one flow.
  snapshots              Export OpenAPI, SSE, and runtime-doctor contract snapshots.
  benchmark-report       Export the default backend benchmark reports.
  golden-report          Export the default golden evaluation report.
  benchmark-trend        Export the default benchmark trend report.
  quality-gate           Run the default backend quality gate thresholds.
  release-scorecard      Export the strict release harness scorecard.
  release-manifest       Export a local release manifest.
  support-bundle         Export a runtime support bundle.
  infra-check            Run local infra-quality checks, exports, and compose validation when Docker is available.
  backend-image-smoke    Build the backend image locally.
  frontend-image-smoke   Build the frontend image locally.
  container-smoke        Build both backend and frontend images locally.
  compose-up             Run docker compose up --build with deploy/compose/compose.yaml.
  compose-observability  Run docker compose with the observability profile from deploy/compose/compose.yaml.
  compose-config         Render compose config for default and observability profiles from deploy/compose/compose.yaml.

Options:
  --base-url            Base URL used by support-bundle and optional runtime-doctor probes. Support-bundle default: http://localhost:38083
  --git-sha             Git SHA used by release-manifest. Default: local
  --git-ref             Git ref used by release-manifest. Default: refs/heads/main
  --release-tag         Optional release tag used by release-manifest.
  --owner               Image owner used by release-manifest. Default: local
  --python-base-image   Base image used by backend compose/build tasks. Default: python:3.13-slim
  --node-base-image     Base image used by frontend compose/build tasks. Default: node:22-alpine
  --backend-host        Host used by backend-dev. Default: 0.0.0.0
  --backend-port        Port used by backend-dev. Default: 38083
  --backend-reload      Enable uvicorn reload for backend-dev.
  --runtime-doctor-json Print runtime-doctor output as JSON.
  --runtime-doctor-strict Fail runtime-doctor when any check is degraded or not ready.
  --backup-label        Optional label used by runtime-backup.
  --backup-output-dir   Optional output dir used by runtime-backup.
  --restore-archive     Backup archive path used by runtime-restore.
  --restore-no-safety-backup Skip the automatic pre-restore safety backup.
  --restore-safety-output-dir Optional directory for restore safety backups.
  --prune-backups-dir   Optional backups dir used by runtime-prune.
  --prune-keep-latest-backups Always keep at least this many newest backups.
  --prune-max-backup-age-days Delete backups older than this age in days.
  --prune-max-session-age-seconds Delete sessions older than this many seconds.
  --prune-max-failure-age-days Delete failure clusters older than this many days.
  --prune-vacuum-checkpoints Run checkpoint maintenance during runtime-prune.
  --prune-checkpoint-backend Override prune checkpoint backend. Choices: sqlite, postgres
  --prune-checkpoint-db Override prune checkpoint SQLite path or PostgreSQL DSN.
  --replay-session-id   Session ID used by agent-replay.
  --replay-db           Override agent-replay checkpoint SQLite path or PostgreSQL DSN.
  --replay-checkpoint-backend Override agent-replay checkpoint backend. Choices: sqlite, postgres
  --replay-checkpoint-id Specific checkpoint ID used by agent-replay.
  --replay-checkpoint-ns Checkpoint namespace used by agent-replay.
  --replay-dry-run      Only export the checkpoint snapshot during agent-replay.
  --pytest-slice        Backend slice for backend-test. Choices: unit, local, runtime, ops, all. Default: unit
  --pytest-path         Repeatable tests/ path for backend-test. Must stay under tests/
"""


def resolve_repo_python() -> str:
    """Prefer the project virtualenv interpreter and fall back to the current one."""

    candidates = (
        REPO_ROOT / ".venv" / "Scripts" / "python.exe",
        REPO_ROOT / ".venv" / "bin" / "python",
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def run_command(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    """Run a command from the repository context and fail loudly on errors."""

    subprocess.run(
        list(command),
        check=True,
        cwd=str(cwd or REPO_ROOT),
        env=env,
    )


def python_module_exists(python_executable: str, module_name: str) -> bool:
    """Return whether the selected interpreter can import the given module."""

    check = subprocess.run(
        [
            python_executable,
            "-c",
            (
                "import importlib.util, sys; "
                f"sys.exit(0 if importlib.util.find_spec({module_name!r}) else 1)"
            ),
        ],
        cwd=str(REPO_ROOT),
    )
    return check.returncode == 0


def ensure_python_module(
    python_executable: str,
    module_name: str,
    package_name: str | None = None,
) -> None:
    """Fail with a clear message when the local interpreter misses a required package."""

    if python_module_exists(python_executable, module_name):
        return
    missing = package_name or module_name
    raise SystemExit(
        f"Missing Python module '{missing}'. "
        "Run 'python scripts/bootstrap.py' or install dev dependencies first."
    )


def npm_environment() -> dict[str, str]:
    """Return a frontend-friendly environment with a Node memory safety margin."""

    env = os.environ.copy()
    env.setdefault("NODE_OPTIONS", "--max-old-space-size=4096")
    return env


def resolve_npm_command() -> str:
    """Resolve a cross-platform npm executable path."""

    candidates = ("npm.cmd", "npm", "npm.exe")
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise SystemExit("npm executable not found. Install Node.js/npm and ensure it is on PATH.")


def run_frontend_command(arguments: Sequence[str]) -> None:
    """Run an npm command from the frontend workspace."""

    run_command([resolve_npm_command(), *arguments], cwd=FRONTEND_ROOT, env=npm_environment())


def run_backend_dev(python_executable: str, args: argparse.Namespace) -> None:
    """Run the FastAPI app locally with the repository Python interpreter."""

    ensure_python_module(python_executable, "uvicorn")
    command = [
        python_executable,
        "-m",
        "uvicorn",
        "moyuan_web.main:app",
        "--host",
        str(args.backend_host),
        "--port",
        str(args.backend_port),
        "--app-dir",
        str(BACKEND_ROOT),
    ]
    if args.backend_reload:
        command.append("--reload")
    run_command(command)


def validate_pytest_path(raw_value: str) -> str:
    """Validate that backend-test paths stay inside tests/ and are file-or-dir targets."""

    candidate = Path(raw_value)
    resolved = candidate if candidate.is_absolute() else (REPO_ROOT / candidate)
    resolved = resolved.resolve()
    try:
        relative = resolved.relative_to(REPO_ROOT)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "--pytest-path must stay within the repository root."
        ) from exc

    if not relative.parts or relative.parts[0] != "tests":
        raise argparse.ArgumentTypeError("--pytest-path only accepts paths under tests/.")
    if not resolved.exists():
        raise argparse.ArgumentTypeError(
            "--pytest-path must reference an existing tests/ directory or test file."
        )
    if resolved.is_dir():
        return relative.as_posix()
    if resolved.suffix != ".py":
        raise argparse.ArgumentTypeError(
            "--pytest-path must reference a tests/ directory or Python test file."
        )
    return relative.as_posix()


def build_backend_test_command(
    python_executable: str,
    args: argparse.Namespace,
    *,
    slice_name: str | None = None,
) -> list[str]:
    """Build the backend pytest command for a named slice plus explicit test paths."""

    ensure_python_module(python_executable, "pytest")
    selected_slice = slice_name or str(args.pytest_slice)
    slice_config = BACKEND_TEST_SLICES[selected_slice]
    targets = list(slice_config["targets"] or ())
    targets.extend(args.pytest_path)
    deduped_targets = list(dict.fromkeys(targets))

    command = [python_executable, "-m", "pytest", *deduped_targets]
    marker = slice_config["marker"]
    if marker:
        command.extend(["-m", marker])
    command.append("-q")
    return command


def run_backend_test(
    python_executable: str,
    args: argparse.Namespace,
    *,
    slice_name: str | None = None,
) -> None:
    """Run backend pytest through the controlled slice-based entrypoint."""

    run_command(build_backend_test_command(python_executable, args, slice_name=slice_name))


def docker_available() -> bool:
    """Return whether Docker is available on the current machine."""

    return shutil.which("docker") is not None


def docker_environment(args: argparse.Namespace) -> dict[str, str]:
    """Build environment overrides for docker compose and docker build commands."""

    env = os.environ.copy()
    env["PYTHON_BASE_IMAGE"] = args.python_base_image
    env["NODE_BASE_IMAGE"] = args.node_base_image
    return env


def build_created_at() -> str:
    """Return the UTC timestamp used for image build metadata."""

    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_ruff(python_executable: str) -> None:
    """Run Ruff on the curated infra/runtime target set."""

    ensure_python_module(python_executable, "ruff")
    run_command(
        [
            python_executable,
            "-m",
            "ruff",
            "check",
            *STATIC_TARGETS,
        ]
    )


def run_mypy(python_executable: str) -> None:
    """Run mypy on the curated infra/runtime target set."""

    ensure_python_module(python_executable, "mypy")
    run_command(
        [
            python_executable,
            "-m",
            "mypy",
            *STATIC_TARGETS,
        ]
    )


def run_docstring_audit(python_executable: str) -> None:
    """Execute the strict docstring governance check."""

    run_command([python_executable, "scripts/docstring_audit.py", "--strict"])


def run_complexity_budget(python_executable: str) -> None:
    """Execute the strict hotspot complexity budget gate."""

    run_command([python_executable, "scripts/complexity_budget.py", "--strict"])


def run_decision_records(python_executable: str) -> None:
    """Execute the strict ADR/RFC/design-review structure audit."""

    run_command([python_executable, "scripts/decision_record_audit.py", "--strict"])


def run_skills_market_audit(python_executable: str) -> None:
    """Execute the strict governed skills-market audit."""

    run_command([python_executable, "scripts/skills_market_audit.py", "--strict"])


def run_runtime_contract_audit(python_executable: str) -> None:
    """Execute the strict runtime seam contract audit."""

    run_command([python_executable, "scripts/runtime_contract_audit.py", "--strict"])


def run_runtime_doctor(python_executable: str, args: argparse.Namespace) -> None:
    """Run runtime diagnostics through the shared local dev entrypoint."""

    command = [python_executable, "scripts/runtime_doctor.py"]
    if args.base_url:
        command.extend(["--base-url", args.base_url])
    if args.runtime_doctor_json:
        command.append("--json")
    if args.runtime_doctor_strict:
        command.append("--strict")
    run_command(command)


def require_task_option(value: str | None, option_name: str, task_name: str) -> str:
    """Return the given option value or fail with a task-specific message."""

    if value:
        return value
    raise SystemExit(
        f"Task '{task_name}' requires '{option_name}'. "
        "Run 'python scripts/dev.py help' for the supported options."
    )


def run_runtime_backup_task(python_executable: str, args: argparse.Namespace) -> None:
    """Run runtime backup through the shared local dev entrypoint."""

    command = [python_executable, "scripts/runtime_backup.py"]
    if args.backup_output_dir:
        command.extend(["--output-dir", args.backup_output_dir])
    if args.backup_label:
        command.extend(["--label", args.backup_label])
    run_command(command)


def run_runtime_restore_task(python_executable: str, args: argparse.Namespace) -> None:
    """Run runtime restore through the shared local dev entrypoint."""

    command = [
        python_executable,
        "scripts/runtime_restore.py",
        "--archive",
        require_task_option(args.restore_archive, "--restore-archive", "runtime-restore"),
    ]
    if args.restore_no_safety_backup:
        command.append("--no-safety-backup")
    if args.restore_safety_output_dir:
        command.extend(["--safety-output-dir", args.restore_safety_output_dir])
    run_command(command)


def run_runtime_prune_task(python_executable: str, args: argparse.Namespace) -> None:
    """Run runtime prune through the shared local dev entrypoint."""

    command = [python_executable, "scripts/runtime_prune.py"]
    if args.prune_backups_dir:
        command.extend(["--backups-dir", args.prune_backups_dir])
    if args.prune_keep_latest_backups is not None:
        command.extend(["--keep-latest-backups", str(args.prune_keep_latest_backups)])
    if args.prune_max_backup_age_days is not None:
        command.extend(["--max-backup-age-days", str(args.prune_max_backup_age_days)])
    if args.prune_max_session_age_seconds is not None:
        command.extend(["--max-session-age-seconds", str(args.prune_max_session_age_seconds)])
    if args.prune_max_failure_age_days is not None:
        command.extend(["--max-failure-age-days", str(args.prune_max_failure_age_days)])
    if args.prune_vacuum_checkpoints:
        command.append("--vacuum-checkpoints")
    if args.prune_checkpoint_backend:
        command.extend(["--checkpoint-backend", args.prune_checkpoint_backend])
    if args.prune_checkpoint_db:
        command.extend(["--checkpoint-db", args.prune_checkpoint_db])
    run_command(command)


def run_agent_replay_task(python_executable: str, args: argparse.Namespace) -> None:
    """Run agent replay through the shared local dev entrypoint."""

    command = [
        python_executable,
        "scripts/agent_replay.py",
        "--session-id",
        require_task_option(args.replay_session_id, "--replay-session-id", "agent-replay"),
    ]
    if args.replay_db:
        command.extend(["--db", args.replay_db])
    if args.replay_checkpoint_backend:
        command.extend(["--checkpoint-backend", args.replay_checkpoint_backend])
    if args.replay_checkpoint_id:
        command.extend(["--checkpoint-id", args.replay_checkpoint_id])
    if args.replay_checkpoint_ns is not None:
        command.extend(["--checkpoint-ns", args.replay_checkpoint_ns])
    if args.replay_dry_run:
        command.append("--dry-run")
    run_command(command)


def run_runtime_maintenance_task(python_executable: str, args: argparse.Namespace) -> None:
    """Run the standard runtime maintenance workflow."""

    maintenance_args = argparse.Namespace(**vars(args))
    maintenance_args.runtime_doctor_json = True
    run_runtime_backup_task(python_executable, maintenance_args)
    run_runtime_doctor(python_executable, maintenance_args)
    run_runtime_prune_task(python_executable, maintenance_args)


def run_checkpoint_maintenance_task(python_executable: str, args: argparse.Namespace) -> None:
    """Run the checkpoint-focused maintenance workflow."""

    maintenance_args = argparse.Namespace(**vars(args))
    maintenance_args.runtime_doctor_json = True
    maintenance_args.prune_vacuum_checkpoints = True
    if maintenance_args.replay_session_id:
        maintenance_args.replay_dry_run = True

    run_runtime_prune_task(python_executable, maintenance_args)
    if maintenance_args.replay_session_id:
        run_agent_replay_task(python_executable, maintenance_args)
    run_runtime_doctor(python_executable, maintenance_args)


def run_snapshots(python_executable: str) -> None:
    """Refresh OpenAPI, SSE, and runtime-doctor contract snapshots."""

    run_command([python_executable, "scripts/export_openapi_snapshot.py"])
    run_command([python_executable, "scripts/export_sse_contract_snapshot.py"])
    run_command([python_executable, "scripts/export_runtime_doctor_snapshot.py"])


def run_release_manifest(python_executable: str, args: argparse.Namespace) -> None:
    """Export the local release manifest with caller-supplied metadata."""

    command = [
        python_executable,
        "scripts/export_release_manifest.py",
        "--git-sha",
        args.git_sha,
        "--git-ref",
        args.git_ref,
        "--owner",
        args.owner,
    ]
    if args.release_tag:
        command.extend(["--release-tag", args.release_tag])
    run_command(command)


def run_benchmark_report(python_executable: str) -> None:
    """Export the default benchmark reports used by local and CI workflows."""

    run_command(
        [
            python_executable,
            "scripts/agent_benchmark.py",
            "--output-dir",
            DEFAULT_BENCHMARK_OUTPUT_DIR,
        ]
    )


def run_golden_report(python_executable: str) -> None:
    """Export the default golden-eval report used by local and CI workflows."""

    run_command(
        [
            python_executable,
            "scripts/agent_golden_eval.py",
            "--dataset",
            DEFAULT_GOLDEN_DATASET,
            "--report",
            DEFAULT_GOLDEN_REPORT,
            "--min-pass-rate",
            DEFAULT_MIN_GOLDEN_PASS_RATE,
        ]
    )


def run_benchmark_trend_report(python_executable: str) -> None:
    """Export the default benchmark trend report used by local and CI workflows."""

    run_command(
        [
            python_executable,
            "scripts/agent_benchmark_trend.py",
            "--current",
            DEFAULT_BENCHMARK_REPORT,
            "--baseline",
            DEFAULT_BENCHMARK_BASELINE_REPORT,
            "--output",
            DEFAULT_BENCHMARK_TREND_REPORT,
        ]
    )


def run_quality_gate(python_executable: str) -> None:
    """Run the default backend quality gate with the CI threshold contract."""

    run_command(
        [
            python_executable,
            "scripts/agent_quality_gate.py",
            "--golden-report",
            DEFAULT_GOLDEN_REPORT,
            "--benchmark-report",
            DEFAULT_BENCHMARK_REPORT,
            "--baseline-benchmark-report",
            DEFAULT_BENCHMARK_BASELINE_REPORT,
            "--min-golden-pass-rate",
            "0.96",
            "--max-golden-hallucination-rate",
            DEFAULT_MAX_GOLDEN_HALLUCINATION_RATE,
            "--min-benchmark-success-rate",
            DEFAULT_MIN_BENCHMARK_SUCCESS_RATE,
            "--max-benchmark-hallucination-rate",
            DEFAULT_MAX_BENCHMARK_HALLUCINATION_RATE,
            "--max-benchmark-fallback-steps-total",
            DEFAULT_MAX_BENCHMARK_FALLBACK_STEPS_TOTAL,
            "--max-success-rate-regression",
            DEFAULT_MAX_SUCCESS_RATE_REGRESSION,
            "--max-hallucination-rate-regression",
            DEFAULT_MAX_HALLUCINATION_RATE_REGRESSION,
            "--max-fallback-steps-regression",
            DEFAULT_MAX_FALLBACK_STEPS_REGRESSION,
        ]
    )


def run_release_harness_scorecard(python_executable: str) -> None:
    """Generate and validate the release harness scorecard."""

    run_command(
        [
            python_executable,
            "scripts/release_harness_scorecard.py",
            "--output-dir",
            DEFAULT_BENCHMARK_OUTPUT_DIR,
            "--strict",
        ]
    )


def run_support_bundle(python_executable: str, args: argparse.Namespace) -> None:
    """Export a runtime support bundle against the configured base URL."""

    run_command(
        [
            python_executable,
            "scripts/export_support_bundle.py",
            "--base-url",
            args.base_url or DEFAULT_BASE_URL,
        ]
    )


def run_compose(arguments: Sequence[str], args: argparse.Namespace) -> None:
    """Run a docker compose command with shared base-image overrides."""

    run_command(
        ["docker", "compose", "--file", str(COMPOSE_FILE), *arguments],
        env=docker_environment(args),
    )


def run_compose_config(args: argparse.Namespace) -> None:
    """Render both default and observability compose configurations."""

    run_compose(["config"], args)
    run_compose(["--profile", "observability", "config"], args)


def run_backend_image_smoke(args: argparse.Namespace) -> None:
    """Build the backend image with local metadata overrides."""

    run_command(
        [
            "docker",
            "build",
            "--file",
            str(BACKEND_DOCKERFILE),
            "--build-arg",
            f"PYTHON_BASE_IMAGE={args.python_base_image}",
            "--build-arg",
            f"APP_BUILD_SHA={args.git_sha}",
            "--build-arg",
            f"APP_BUILD_CREATED_AT={build_created_at()}",
            "--tag",
            "moyuan-backend:local",
            ".",
        ]
    )


def run_frontend_image_smoke(args: argparse.Namespace) -> None:
    """Build the frontend image with local metadata overrides."""

    run_command(
        [
            "docker",
            "build",
            "--file",
            str(FRONTEND_DOCKERFILE),
            "--build-arg",
            f"NODE_BASE_IMAGE={args.node_base_image}",
            "--build-arg",
            "NEXT_PUBLIC_API_BASE=http://localhost:38083",
            "--build-arg",
            "INTERNAL_API_BASE=http://backend:38083",
            "--build-arg",
            f"APP_BUILD_SHA={args.git_sha}",
            "--build-arg",
            f"APP_BUILD_CREATED_AT={build_created_at()}",
            "--tag",
            "moyuan-frontend:local",
            ".",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for local development orchestration tasks."""

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("task", nargs="?", default="help")
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--git-sha", default=DEFAULT_GIT_SHA)
    parser.add_argument("--git-ref", default=DEFAULT_GIT_REF)
    parser.add_argument("--release-tag", default=None)
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--python-base-image", default=DEFAULT_PYTHON_BASE_IMAGE)
    parser.add_argument("--node-base-image", default=DEFAULT_NODE_BASE_IMAGE)
    parser.add_argument("--backend-host", default=DEFAULT_BACKEND_HOST)
    parser.add_argument("--backend-port", type=int, default=DEFAULT_BACKEND_PORT)
    parser.add_argument("--backend-reload", action="store_true")
    parser.add_argument("--runtime-doctor-json", action="store_true")
    parser.add_argument("--runtime-doctor-strict", action="store_true")
    parser.add_argument("--backup-label", default=None)
    parser.add_argument("--backup-output-dir", default=None)
    parser.add_argument("--restore-archive", default=None)
    parser.add_argument("--restore-no-safety-backup", action="store_true")
    parser.add_argument("--restore-safety-output-dir", default=None)
    parser.add_argument("--prune-backups-dir", default=None)
    parser.add_argument("--prune-keep-latest-backups", type=int, default=None)
    parser.add_argument("--prune-max-backup-age-days", type=int, default=None)
    parser.add_argument("--prune-max-session-age-seconds", type=int, default=None)
    parser.add_argument("--prune-max-failure-age-days", type=int, default=None)
    parser.add_argument("--prune-vacuum-checkpoints", action="store_true")
    parser.add_argument(
        "--prune-checkpoint-backend",
        choices=("sqlite", "postgres"),
        default=None,
    )
    parser.add_argument("--prune-checkpoint-db", default=None)
    parser.add_argument("--replay-session-id", default=None)
    parser.add_argument("--replay-db", default=None)
    parser.add_argument(
        "--replay-checkpoint-backend",
        choices=("sqlite", "postgres"),
        default=None,
    )
    parser.add_argument("--replay-checkpoint-id", default=None)
    parser.add_argument("--replay-checkpoint-ns", default=None)
    parser.add_argument("--replay-dry-run", action="store_true")
    parser.add_argument(
        "--pytest-slice",
        choices=tuple(BACKEND_TEST_SLICES),
        default="unit",
    )
    parser.add_argument(
        "--pytest-path",
        action="append",
        default=[],
        type=validate_pytest_path,
    )
    parser.add_argument("-h", "--help", action="store_true")
    return parser


def main() -> int:
    """Dispatch the selected task and return a process exit code."""

    parser = build_parser()
    args = parser.parse_args()
    if args.help or args.task == "help":
        print(HELP_TEXT)
        return 0

    task = str(args.task).lower()
    python_executable = resolve_repo_python()

    if task == "backend-dev":
        run_backend_dev(python_executable, args)
    elif task == "backend-test":
        run_backend_test(python_executable, args)
    elif task == "backend-unit":
        run_backend_test(python_executable, args, slice_name="unit")
    elif task == "backend-local":
        run_backend_test(python_executable, args, slice_name="local")
    elif task == "frontend-dev":
        run_frontend_command(["run", "dev"])
    elif task == "frontend-lint":
        run_frontend_command(["run", "lint"])
    elif task == "frontend-test":
        run_frontend_command(["run", "test:run"])
    elif task == "frontend-build":
        run_frontend_command(["run", "build"])
    elif task == "test":
        run_backend_test(python_executable, args, slice_name="unit")
        run_backend_test(python_executable, args, slice_name="local")
        run_frontend_command(["run", "lint"])
        run_frontend_command(["run", "test:run"])
        run_frontend_command(["run", "build"])
    elif task == "ruff":
        run_ruff(python_executable)
    elif task == "mypy":
        run_mypy(python_executable)
    elif task == "docstring":
        run_docstring_audit(python_executable)
    elif task == "complexity":
        run_complexity_budget(python_executable)
    elif task == "decision-records":
        run_decision_records(python_executable)
    elif task == "skills-market":
        run_skills_market_audit(python_executable)
    elif task == "runtime-contracts":
        run_runtime_contract_audit(python_executable)
    elif task == "runtime-doctor":
        run_runtime_doctor(python_executable, args)
    elif task == "runtime-backup":
        run_runtime_backup_task(python_executable, args)
    elif task == "runtime-restore":
        run_runtime_restore_task(python_executable, args)
    elif task == "runtime-prune":
        run_runtime_prune_task(python_executable, args)
    elif task == "agent-replay":
        run_agent_replay_task(python_executable, args)
    elif task == "runtime-maintenance":
        run_runtime_maintenance_task(python_executable, args)
    elif task == "checkpoint-maintenance":
        run_checkpoint_maintenance_task(python_executable, args)
    elif task == "snapshots":
        run_snapshots(python_executable)
    elif task == "benchmark-report":
        run_benchmark_report(python_executable)
    elif task == "golden-report":
        run_golden_report(python_executable)
    elif task == "benchmark-trend":
        run_benchmark_trend_report(python_executable)
    elif task == "quality-gate":
        run_quality_gate(python_executable)
    elif task == "release-scorecard":
        run_release_harness_scorecard(python_executable)
    elif task == "release-manifest":
        run_release_manifest(python_executable, args)
    elif task == "support-bundle":
        run_support_bundle(python_executable, args)
    elif task == "infra-check":
        run_ruff(python_executable)
        run_mypy(python_executable)
        run_docstring_audit(python_executable)
        run_complexity_budget(python_executable)
        run_decision_records(python_executable)
        run_skills_market_audit(python_executable)
        run_runtime_contract_audit(python_executable)
        args.runtime_doctor_json = True
        run_runtime_doctor(python_executable, args)
        run_snapshots(python_executable)
        run_release_harness_scorecard(python_executable)
        run_release_manifest(python_executable, args)
        if docker_available():
            run_compose_config(args)
        else:
            print(
                "Warning: Docker is not available. "
                "Skipping compose validation during infra-check.",
                file=sys.stderr,
            )
    elif task == "backend-image-smoke":
        run_backend_image_smoke(args)
    elif task == "frontend-image-smoke":
        run_frontend_image_smoke(args)
    elif task == "container-smoke":
        run_backend_image_smoke(args)
        run_frontend_image_smoke(args)
    elif task == "compose-up":
        run_compose(["up", "--build"], args)
    elif task == "compose-observability":
        run_compose(["--profile", "observability", "up", "--build"], args)
    elif task == "compose-config":
        run_compose_config(args)
    else:
        parser.exit(2, f"Unknown task '{args.task}'. Run 'python scripts/dev.py help'.\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
