"""Cross-platform bootstrap helper for the local development environment."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_ROOT = REPO_ROOT / "frontend"
DEFAULT_PYTHON_VERSION = "3.13"


def log_step(message: str) -> None:
    """Print a consistently prefixed bootstrap progress line."""

    print(f"[bootstrap] {message}")


def run_command(command: list[str], *, cwd: Path | None = None) -> None:
    """Run a subprocess from the repository and fail loudly when it errors."""

    subprocess.run(command, check=True, cwd=str(cwd or REPO_ROOT))


def find_uv() -> str:
    """Locate a usable uv executable for environment setup."""

    uv_path = shutil.which("uv")
    if uv_path:
        return uv_path
    fallback = Path.home() / ".local" / "bin" / "uv.exe"
    if fallback.exists():
        return str(fallback)
    raise SystemExit("uv not found. Install uv or add it to PATH before bootstrapping.")


def venv_python_path() -> Path:
    """Return the expected virtualenv interpreter path for the current platform."""

    if sys.platform.startswith("win"):
        return REPO_ROOT / ".venv" / "Scripts" / "python.exe"
    return REPO_ROOT / ".venv" / "bin" / "python"


def current_venv_version(python_path: Path) -> str | None:
    """Return the major.minor version for the existing virtualenv interpreter."""

    if not python_path.exists():
        return None
    output = subprocess.check_output(
        [str(python_path), "-c", "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"],
        cwd=str(REPO_ROOT),
        text=True,
    )
    return output.strip()


def ensure_virtualenv(uv_path: str, python_version: str) -> Path:
    """Create or recreate the local virtualenv when the Python version drifts."""

    python_path = venv_python_path()
    existing = current_venv_version(python_path)
    if existing == python_version:
        return python_path

    if existing is None:
        log_step(f"Create .venv with Python {python_version}")
    else:
        log_step(
            f"Recreate .venv because it uses Python {existing} instead of {python_version}"
        )
    run_command([uv_path, "venv", ".venv", "--python", python_version, "--clear"])
    if not python_path.exists():
        raise SystemExit(f"Failed to create .venv at {python_path}")
    return python_path


def ensure_config_from_example(filename: str) -> None:
    """Seed a config file from its example template when needed."""

    config_path = REPO_ROOT / "config" / filename
    example_path = REPO_ROOT / "config" / f"{filename}.example"
    if config_path.exists():
        log_step(f"Config check passed: config/{filename} exists")
        return
    if not example_path.exists():
        print(
            f"[bootstrap] Warning: missing config/{filename} and its example template.",
            file=sys.stderr,
        )
        return
    config_path.write_text(example_path.read_text(encoding="utf-8"), encoding="utf-8")
    log_step(f"Created config/{filename} from template.")


def build_parser() -> argparse.ArgumentParser:
    """Build the bootstrap CLI parser."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--python-version", default=DEFAULT_PYTHON_VERSION)
    parser.add_argument("--skip-frontend", action="store_true")
    return parser


def main() -> int:
    """Bootstrap the local Python, frontend, and config prerequisites."""

    parser = build_parser()
    args = parser.parse_args()

    uv_path = find_uv()
    log_step(f"Using uv at: {uv_path}")
    run_command([uv_path, "--version"])

    log_step(f"Ensure Python {args.python_version} is installed")
    run_command([uv_path, "python", "install", args.python_version])

    python_path = ensure_virtualenv(uv_path, args.python_version)

    log_step("Install Python dependencies")
    run_command([uv_path, "pip", "install", "--python", str(python_path), "-r", "requirements-dev.txt"])

    if not args.skip_frontend:
        log_step("Install frontend dependencies")
        run_command(["npm", "install"], cwd=FRONTEND_ROOT)

    ensure_config_from_example("llm_config.yaml")
    ensure_config_from_example("server_config.yaml")

    log_step("Bootstrap complete")
    print("Next step: python scripts/dev.py help")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
