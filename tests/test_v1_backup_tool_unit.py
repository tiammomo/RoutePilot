"""Tests for atomic, private RoutePilot backup artifacts."""

from __future__ import annotations

import json
import stat
from datetime import UTC, datetime
from pathlib import Path

import pytest

from scripts import v1_backup


def test_backup_creation_is_atomic_private_and_manifest_bound(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    env_file = tmp_path / "compose.env"
    compose_file = tmp_path / "compose.yaml"
    env_file.write_text("SECRET=not-read-by-test\n", encoding="utf-8")
    compose_file.write_text("services: {}\n", encoding="utf-8")
    output_dir = tmp_path / "backups"

    def fake_dump(command, stream) -> None:
        assert "pg_dump" in command
        stream.write(b"PGDMP-test-archive")

    def fake_verify(command, backup: Path) -> None:
        assert "pg_restore" in command
        assert backup.read_bytes().startswith(b"PGDMP")

    def fake_text(command) -> str:
        if "psql" in command:
            return "20260713_0011"
        if "images" in command:
            return "sha256:postgres-test"
        return "a" * 40

    monkeypatch.setattr(v1_backup, "_dump", fake_dump)
    monkeypatch.setattr(v1_backup, "_verify_archive", fake_verify)
    monkeypatch.setattr(v1_backup, "_run_text", fake_text)
    now = datetime(2026, 7, 13, 8, 30, tzinfo=UTC)

    backup = v1_backup.create_backup(
        output_dir=output_dir,
        env_file=env_file,
        compose_file=compose_file,
        project_name="routepilot-v1",
        now=now,
    )

    assert backup.name == "routepilot-20260713T083000Z.dump"
    assert stat.S_IMODE(output_dir.stat().st_mode) == 0o700
    for artifact in (
        backup,
        backup.with_suffix(".dump.sha256"),
        backup.with_suffix(".dump.manifest.json"),
    ):
        assert stat.S_IMODE(artifact.stat().st_mode) == 0o600
    manifest = json.loads(
        backup.with_suffix(".dump.manifest.json").read_text(encoding="utf-8")
    )
    assert manifest["alembic_revision"] == "20260713_0011"
    assert manifest["sha256"] == v1_backup.sha256_file(backup)
    assert not backup.with_suffix(".dump.partial").exists()

    verified = v1_backup.verify_backup(
        backup=backup,
        env_file=env_file,
        compose_file=compose_file,
        project_name="routepilot-v1",
    )
    assert verified["backup_file"] == backup.name


def test_backup_rejects_broad_permissions_and_tampering(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    insecure = tmp_path / "insecure"
    insecure.mkdir(mode=0o755)
    with pytest.raises(v1_backup.BackupError, match="group/other"):
        v1_backup.ensure_secure_directory(insecure)

    secure = tmp_path / "secure"
    secure.mkdir(mode=0o700)
    backup = secure / "routepilot.dump"
    backup.write_bytes(b"archive")
    backup.chmod(0o600)
    digest = v1_backup.sha256_file(backup)
    backup.with_suffix(".dump.sha256").write_text(
        f"{digest}  {backup.name}\n",
        encoding="utf-8",
    )
    backup.with_suffix(".dump.manifest.json").write_text(
        json.dumps(
            {
                "backup_file": backup.name,
                "size_bytes": backup.stat().st_size,
                "sha256": digest,
            }
        ),
        encoding="utf-8",
    )
    backup.write_bytes(b"tampered")
    monkeypatch.setattr(v1_backup, "_verify_archive", lambda *_: None)

    with pytest.raises(v1_backup.BackupError, match="checksum"):
        v1_backup.verify_backup(
            backup=backup,
            env_file=tmp_path / "unused.env",
            compose_file=tmp_path / "unused.yaml",
            project_name="routepilot-v1",
        )
