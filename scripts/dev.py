"""Cross-platform local task entrypoint for development and infra checks."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, UTC
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPO_ROOT / "frontend"
DEFAULT_BASE_URL = "http://localhost:38000"
DEFAULT_GIT_SHA = "local"
DEFAULT_GIT_REF = "refs/heads/main"
DEFAULT_OWNER = "local"
DEFAULT_PYTHON_BASE_IMAGE = "python:3.13-slim"
DEFAULT_NODE_BASE_IMAGE = "node:22-alpine"
STATIC_TARGETS = (
    "scripts/dev.py",
    "scripts/bootstrap.py",
    "scripts/export_openapi_snapshot.py",
    "scripts/export_release_manifest.py",
    "scripts/release_harness_scorecard.py",
    "scripts/export_support_bundle.py",
    "scripts/export_sse_contract_snapshot.py",
    "scripts/runtime_backup.py",
    "scripts/runtime_data_utils.py",
    "scripts/runtime_doctor.py",
    "scripts/runtime_prune.py",
    "scripts/runtime_restore.py",
    "web/moyuan_web/app_meta.py",
    "web/moyuan_web/main.py",
    "web/moyuan_web/middleware/__init__.py",
    "web/moyuan_web/observability.py",
    "web/moyuan_web/routes/chat.py",
    "web/moyuan_web/routes/health.py",
    "web/moyuan_web/services/share_service.py",
    "web/moyuan_web/startup_checks.py",
)
HELP_TEXT = """Usage:
  python scripts/dev.py <task> [options]

Tasks:
  help                   Show this help.
  backend-unit           Run backend unit tests.
  backend-local          Run backend local smoke tests.
  frontend-lint          Run frontend type/lint checks.
  frontend-test          Run frontend unit tests.
  frontend-build         Build the frontend.
  test                   Run backend + frontend verification slices.
  ruff                   Run local Ruff checks on infra/runtime targets.
  mypy                   Run local mypy checks on infra/runtime targets.
  docstring              Run Python docstring audit.
  complexity             Run hotspot complexity budget gate.
  decision-records       Run ADR / RFC / design-review audit.
  snapshots              Export OpenAPI and SSE contract snapshots.
  release-manifest       Export a local release manifest.
  support-bundle         Export a runtime support bundle.
  infra-check            Run local infra-quality checks, exports, and compose validation when Docker is available.
  backend-image-smoke    Build the backend image locally.
  frontend-image-smoke   Build the frontend image locally.
  container-smoke        Build both backend and frontend images locally.
  compose-up             Run docker compose up --build.
  compose-observability  Run docker compose with the observability profile.
  compose-config         Render compose config for default and observability profiles.

Options:
  --base-url            Base URL used by support-bundle. Default: http://localhost:38000
  --git-sha             Git SHA used by release-manifest. Default: local
  --git-ref             Git ref used by release-manifest. Default: refs/heads/main
  --owner               Image owner used by release-manifest. Default: local
  --python-base-image   Base image used by backend compose/build tasks. Default: python:3.13-slim
  --node-base-image     Base image used by frontend compose/build tasks. Default: node:22-alpine
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


def run_frontend_command(arguments: Sequence[str]) -> None:
    """Run an npm command from the frontend workspace."""

    run_command(["npm", *arguments], cwd=FRONTEND_ROOT, env=npm_environment())


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
            "--config",
            "ruff.toml",
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
            "--config-file",
            "mypy.ini",
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


def run_snapshots(python_executable: str) -> None:
    """Refresh OpenAPI and SSE contract snapshots."""

    run_command([python_executable, "scripts/export_openapi_snapshot.py"])
    run_command([python_executable, "scripts/export_sse_contract_snapshot.py"])


def run_release_manifest(python_executable: str, args: argparse.Namespace) -> None:
    """Export the local release manifest with caller-supplied metadata."""

    run_command(
        [
            python_executable,
            "scripts/export_release_manifest.py",
            "--git-sha",
            args.git_sha,
            "--git-ref",
            args.git_ref,
            "--owner",
            args.owner,
        ]
    )


def run_release_harness_scorecard(python_executable: str) -> None:
    """Generate and validate the release harness scorecard."""

    run_command([python_executable, "scripts/release_harness_scorecard.py", "--strict"])


def run_support_bundle(python_executable: str, args: argparse.Namespace) -> None:
    """Export a runtime support bundle against the configured base URL."""

    run_command(
        [python_executable, "scripts/export_support_bundle.py", "--base-url", args.base_url]
    )


def run_compose(arguments: Sequence[str], args: argparse.Namespace) -> None:
    """Run a docker compose command with shared base-image overrides."""

    run_command(["docker", "compose", *arguments], env=docker_environment(args))


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
            "Dockerfile.backend",
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
            "frontend/Dockerfile",
            "--build-arg",
            f"NODE_BASE_IMAGE={args.node_base_image}",
            "--build-arg",
            "NEXT_PUBLIC_API_BASE=http://localhost:38000",
            "--build-arg",
            "INTERNAL_API_BASE=http://backend:38000",
            "--build-arg",
            f"APP_BUILD_SHA={args.git_sha}",
            "--build-arg",
            f"APP_BUILD_CREATED_AT={build_created_at()}",
            "--tag",
            "moyuan-frontend:local",
            "./frontend",
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for local development orchestration tasks."""

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("task", nargs="?", default="help")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--git-sha", default=DEFAULT_GIT_SHA)
    parser.add_argument("--git-ref", default=DEFAULT_GIT_REF)
    parser.add_argument("--owner", default=DEFAULT_OWNER)
    parser.add_argument("--python-base-image", default=DEFAULT_PYTHON_BASE_IMAGE)
    parser.add_argument("--node-base-image", default=DEFAULT_NODE_BASE_IMAGE)
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

    if task == "backend-unit":
        run_command(
            [
                python_executable,
                "-m",
                "pytest",
                "tests",
                "-m",
                "unit and not local and not external_api",
                "-q",
            ]
        )
    elif task == "backend-local":
        run_command(
            [
                python_executable,
                "-m",
                "pytest",
                "tests",
                "-m",
                "local and not external_api",
                "-q",
            ]
        )
    elif task == "frontend-lint":
        run_frontend_command(["run", "lint"])
    elif task == "frontend-test":
        run_frontend_command(["run", "test:run"])
    elif task == "frontend-build":
        run_frontend_command(["run", "build"])
    elif task == "test":
        run_command(
            [
                python_executable,
                "-m",
                "pytest",
                "tests",
                "-m",
                "unit and not local and not external_api",
                "-q",
            ]
        )
        run_command(
            [
                python_executable,
                "-m",
                "pytest",
                "tests",
                "-m",
                "local and not external_api",
                "-q",
            ]
        )
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
    elif task == "snapshots":
        run_snapshots(python_executable)
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
        run_command([python_executable, "scripts/runtime_doctor.py", "--json"])
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
