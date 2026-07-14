"""Create and verify restricted RoutePilot V1 PostgreSQL logical backups."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPOSE_FILE = REPOSITORY_ROOT / "deploy/compose/v1.yaml"


class BackupError(RuntimeError):
    """Safe operator-facing backup failure without captured command output."""


def sha256_file(path: Path) -> str:
    """Hash a potentially large dump without loading it into memory."""

    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ensure_secure_directory(path: Path) -> None:
    """Create a 0700 directory or reject an existing broadly-readable path."""

    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    mode = stat.S_IMODE(path.stat().st_mode)
    if mode & 0o077:
        raise BackupError(f"backup directory must not grant group/other access: {path}")


def compose_prefix(*, env_file: Path, compose_file: Path, project_name: str) -> list[str]:
    return [
        "docker",
        "compose",
        "--project-name",
        project_name,
        "--env-file",
        str(env_file),
        "--file",
        str(compose_file),
    ]


def _run_text(command: Sequence[str]) -> str:
    result = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        raise BackupError("backup metadata command failed; inspect restricted container logs")
    return result.stdout.strip()


def _dump(command: Sequence[str], stream: BinaryIO) -> None:
    result = subprocess.run(
        command,
        cwd=REPOSITORY_ROOT,
        stdin=subprocess.DEVNULL,
        stdout=stream,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if result.returncode:
        raise BackupError("pg_dump failed; inspect restricted PostgreSQL logs")


def _verify_archive(command: Sequence[str], dump_path: Path) -> None:
    with dump_path.open("rb") as stream:
        result = subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            stdin=stream,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    if result.returncode:
        raise BackupError("pg_restore could not read the backup archive")


def _write_private(path: Path, content: str) -> None:
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        stream.write(content)
        stream.flush()
        os.fsync(stream.fileno())


def create_backup(
    *,
    output_dir: Path,
    env_file: Path,
    compose_file: Path,
    project_name: str,
    now: datetime | None = None,
) -> Path:
    """Create, structurally validate, checksum, and manifest one atomic dump."""

    ensure_secure_directory(output_dir)
    if not env_file.is_file():
        raise BackupError(f"env file does not exist: {env_file}")
    if not compose_file.is_file():
        raise BackupError(f"compose file does not exist: {compose_file}")
    timestamp = (now or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    backup = output_dir / f"routepilot-{timestamp}.dump"
    partial = backup.with_suffix(".dump.partial")
    for candidate in (backup, partial, backup.with_suffix(".dump.sha256")):
        if candidate.exists():
            raise BackupError(f"refusing to overwrite existing backup file: {candidate}")
    prefix = compose_prefix(
        env_file=env_file,
        compose_file=compose_file,
        project_name=project_name,
    )
    dump_command = [
        *prefix,
        "exec",
        "--no-TTY",
        "postgres",
        "pg_dump",
        "--username",
        "routepilot_admin",
        "--dbname",
        "routepilot",
        "--format=custom",
        "--no-owner",
        "--no-acl",
    ]
    try:
        descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "wb") as stream:
            _dump(dump_command, stream)
            stream.flush()
            os.fsync(stream.fileno())
        if partial.stat().st_size <= 0:
            raise BackupError("pg_dump produced an empty archive")
        os.replace(partial, backup)
        _verify_archive(
            [*prefix, "exec", "--no-TTY", "postgres", "pg_restore", "--list"],
            backup,
        )
        digest = sha256_file(backup)
        checksum = backup.with_suffix(".dump.sha256")
        _write_private(checksum, f"{digest}  {backup.name}\n")
        alembic_revision = _run_text(
            [
                *prefix,
                "exec",
                "--no-TTY",
                "postgres",
                "psql",
                "--username",
                "routepilot_admin",
                "--dbname",
                "routepilot",
                "--tuples-only",
                "--no-align",
                "--command",
                "SELECT version_num FROM alembic_version",
            ]
        )
        image_id = _run_text([*prefix, "images", "--quiet", "postgres"])
        commit = _run_text(["git", "rev-parse", "HEAD"])
        manifest = {
            "schema_version": 1,
            "created_at": (now or datetime.now(UTC)).astimezone(UTC).isoformat(),
            "backup_file": backup.name,
            "size_bytes": backup.stat().st_size,
            "sha256": digest,
            "git_commit": commit,
            "alembic_revision": alembic_revision,
            "postgres_image_id": image_id,
            "compose_project": project_name,
        }
        _write_private(
            backup.with_suffix(".dump.manifest.json"),
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        )
        return backup
    except Exception:
        partial.unlink(missing_ok=True)
        if backup.exists() and not backup.with_suffix(".dump.manifest.json").exists():
            backup.unlink(missing_ok=True)
            backup.with_suffix(".dump.sha256").unlink(missing_ok=True)
        raise


def verify_backup(
    *,
    backup: Path,
    env_file: Path,
    compose_file: Path,
    project_name: str,
) -> dict[str, object]:
    """Verify permissions, checksum, manifest binding, and archive structure."""

    if not backup.is_file() or backup.stat().st_size <= 0:
        raise BackupError(f"backup archive is missing or empty: {backup}")
    if stat.S_IMODE(backup.stat().st_mode) & 0o077:
        raise BackupError("backup archive must not grant group/other access")
    manifest_path = backup.with_suffix(".dump.manifest.json")
    checksum_path = backup.with_suffix(".dump.sha256")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        expected_checksum = checksum_path.read_text(encoding="utf-8").split()[0]
    except (OSError, ValueError, IndexError, json.JSONDecodeError) as exc:
        raise BackupError("backup manifest or checksum is missing or invalid") from exc
    actual_checksum = sha256_file(backup)
    if expected_checksum != actual_checksum or manifest.get("sha256") != actual_checksum:
        raise BackupError("backup checksum does not match archive and manifest")
    if manifest.get("backup_file") != backup.name or manifest.get("size_bytes") != backup.stat().st_size:
        raise BackupError("backup manifest does not describe this archive")
    prefix = compose_prefix(
        env_file=env_file,
        compose_file=compose_file,
        project_name=project_name,
    )
    _verify_archive(
        [*prefix, "exec", "--no-TTY", "postgres", "pg_restore", "--list"],
        backup,
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--compose-file", type=Path, default=DEFAULT_COMPOSE_FILE)
    parser.add_argument("--project-name", default="routepilot-v1")
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--output-dir", type=Path, required=True)
    verify = subparsers.add_parser("verify")
    verify.add_argument("backup", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "create":
            backup = create_backup(
                output_dir=args.output_dir,
                env_file=args.env_file,
                compose_file=args.compose_file,
                project_name=args.project_name,
            )
            print(f"backup created and verified: {backup}")
        else:
            manifest = verify_backup(
                backup=args.backup,
                env_file=args.env_file,
                compose_file=args.compose_file,
                project_name=args.project_name,
            )
            print(
                "backup verified: "
                f"{args.backup} revision={manifest.get('alembic_revision', 'unknown')}"
            )
    except BackupError as exc:
        parser.exit(1, f"backup error: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
