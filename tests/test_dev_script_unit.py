from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def load_module(module_name: str, relative_path: str):
    module_path = PROJECT_ROOT / relative_path
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Unable to load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_parser_accepts_cross_platform_image_flags():
    dev_module = load_module("test_dev_script_unit_dev", "scripts/dev.py")

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "compose-up",
            "--python-base-image",
            "python:test",
            "--node-base-image",
            "node:test",
        ]
    )

    assert args.task == "compose-up"
    assert args.python_base_image == "python:test"
    assert args.node_base_image == "node:test"


def test_build_parser_accepts_backend_dev_flags():
    dev_module = load_module("test_dev_script_unit_dev_backend", "scripts/dev.py")

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "backend-dev",
            "--backend-host",
            "127.0.0.1",
            "--backend-port",
            "39000",
            "--backend-reload",
        ]
    )

    assert args.task == "backend-dev"
    assert args.backend_host == "127.0.0.1"
    assert args.backend_port == 39000
    assert args.backend_reload is True


def test_build_parser_accepts_backend_test_flags():
    dev_module = load_module("test_dev_script_unit_dev_backend_test", "scripts/dev.py")

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "backend-test",
            "--pytest-slice",
            "ops",
            "--pytest-path",
            "tests/test_runtime_doctor_unit.py",
            "--pytest-path",
            "tests/test_runtime_ops_contracts_unit.py",
        ]
    )

    assert args.task == "backend-test"
    assert args.pytest_slice == "ops"
    assert args.pytest_path == [
        "tests/test_runtime_doctor_unit.py",
        "tests/test_runtime_ops_contracts_unit.py",
    ]


def test_build_parser_accepts_runtime_doctor_and_release_manifest_flags():
    dev_module = load_module("test_dev_script_unit_dev_runtime_doctor", "scripts/dev.py")

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "runtime-doctor",
            "--base-url",
            "http://localhost:39000",
            "--runtime-doctor-json",
            "--runtime-doctor-strict",
            "--release-tag",
            "v9.9.9",
        ]
    )

    assert args.task == "runtime-doctor"
    assert args.base_url == "http://localhost:39000"
    assert args.runtime_doctor_json is True
    assert args.runtime_doctor_strict is True
    assert args.release_tag == "v9.9.9"


def test_build_parser_accepts_runtime_lifecycle_flags():
    dev_module = load_module("test_dev_script_unit_dev_runtime_lifecycle", "scripts/dev.py")

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "runtime-prune",
            "--backup-label",
            "before-upgrade",
            "--restore-archive",
            "artifacts/runtime_backups/example.zip",
            "--prune-keep-latest-backups",
            "5",
            "--prune-vacuum-checkpoints",
            "--prune-checkpoint-backend",
            "postgres",
            "--prune-checkpoint-db",
            "postgresql://user:password@localhost:5432/moyuan",
            "--replay-session-id",
            "session-123",
            "--replay-checkpoint-backend",
            "sqlite",
            "--replay-dry-run",
        ]
    )

    assert args.task == "runtime-prune"
    assert args.backup_label == "before-upgrade"
    assert args.restore_archive == "artifacts/runtime_backups/example.zip"
    assert args.prune_keep_latest_backups == 5
    assert args.prune_vacuum_checkpoints is True
    assert args.prune_checkpoint_backend == "postgres"
    assert args.prune_checkpoint_db == "postgresql://user:password@localhost:5432/moyuan"
    assert args.replay_session_id == "session-123"
    assert args.replay_checkpoint_backend == "sqlite"
    assert args.replay_dry_run is True


def test_build_parser_rejects_non_test_pytest_path():
    dev_module = load_module("test_dev_script_unit_dev_backend_test_invalid", "scripts/dev.py")

    parser = dev_module.build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(
            [
                "backend-test",
                "--pytest-path",
                "scripts/dev.py",
            ]
        )


def test_npm_environment_sets_safe_default():
    dev_module = load_module("test_dev_script_unit_dev_env", "scripts/dev.py")

    env = dev_module.npm_environment()

    assert env["NODE_OPTIONS"] == "--max-old-space-size=4096"


def test_resolve_repo_python_falls_back_to_current_interpreter(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_python", "scripts/dev.py")
    monkeypatch.setattr(dev_module, "REPO_ROOT", PROJECT_ROOT / "tests" / "missing-dev-root")

    assert dev_module.resolve_repo_python() == sys.executable


def test_resolve_npm_command_prefers_windows_cmd_when_available(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_npm", "scripts/dev.py")

    def fake_which(name: str):
        return "C:/node/npm.cmd" if name == "npm.cmd" else None

    monkeypatch.setattr(dev_module.shutil, "which", fake_which)

    assert dev_module.resolve_npm_command() == "C:/node/npm.cmd"


def test_run_backend_dev_builds_uvicorn_command(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_backend_run", "scripts/dev.py")
    calls: list[list[str]] = []

    monkeypatch.setattr(dev_module, "ensure_python_module", lambda *args, **kwargs: None)
    monkeypatch.setattr(dev_module, "run_command", lambda command, **kwargs: calls.append(list(command)))

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "backend-dev",
            "--backend-host",
            "127.0.0.1",
            "--backend-port",
            "39000",
            "--backend-reload",
        ]
    )

    dev_module.run_backend_dev("python", args)

    assert calls == [
        [
            "python",
            "-m",
            "uvicorn",
            "moyuan_web.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "39000",
            "--app-dir",
            str(dev_module.BACKEND_ROOT),
            "--reload",
        ]
    ]


def test_run_runtime_doctor_builds_command(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_runtime_doctor_run", "scripts/dev.py")
    calls: list[list[str]] = []

    monkeypatch.setattr(dev_module, "run_command", lambda command, **kwargs: calls.append(list(command)))

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "runtime-doctor",
            "--base-url",
            "http://localhost:39000",
            "--runtime-doctor-json",
            "--runtime-doctor-strict",
        ]
    )

    dev_module.run_runtime_doctor("python", args)

    assert calls == [
        [
            "python",
            "scripts/runtime_doctor.py",
            "--base-url",
            "http://localhost:39000",
            "--json",
            "--strict",
        ]
    ]


def test_run_runtime_doctor_omits_base_url_when_not_set(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_runtime_doctor_default", "scripts/dev.py")
    calls: list[list[str]] = []

    monkeypatch.setattr(dev_module, "run_command", lambda command, **kwargs: calls.append(list(command)))

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "runtime-doctor",
            "--runtime-doctor-json",
        ]
    )

    dev_module.run_runtime_doctor("python", args)

    assert calls == [
        [
            "python",
            "scripts/runtime_doctor.py",
            "--json",
        ]
    ]


def test_run_runtime_backup_task_builds_command(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_runtime_backup", "scripts/dev.py")
    calls: list[list[str]] = []

    monkeypatch.setattr(dev_module, "run_command", lambda command, **kwargs: calls.append(list(command)))

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "runtime-backup",
            "--backup-label",
            "before-upgrade",
            "--backup-output-dir",
            "artifacts/runtime_backups",
        ]
    )

    dev_module.run_runtime_backup_task("python", args)

    assert calls == [
        [
            "python",
            "scripts/runtime_backup.py",
            "--output-dir",
            "artifacts/runtime_backups",
            "--label",
            "before-upgrade",
        ]
    ]


def test_run_runtime_restore_task_requires_archive(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_runtime_restore_missing", "scripts/dev.py")

    monkeypatch.setattr(dev_module, "run_command", lambda *args, **kwargs: None)

    parser = dev_module.build_parser()
    args = parser.parse_args(["runtime-restore"])

    with pytest.raises(SystemExit):
        dev_module.run_runtime_restore_task("python", args)


def test_run_runtime_restore_task_builds_command(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_runtime_restore", "scripts/dev.py")
    calls: list[list[str]] = []

    monkeypatch.setattr(dev_module, "run_command", lambda command, **kwargs: calls.append(list(command)))

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "runtime-restore",
            "--restore-archive",
            "artifacts/runtime_backups/runtime_backup_20260406T120000Z.zip",
            "--restore-no-safety-backup",
            "--restore-safety-output-dir",
            "artifacts/runtime_backups",
        ]
    )

    dev_module.run_runtime_restore_task("python", args)

    assert calls == [
        [
            "python",
            "scripts/runtime_restore.py",
            "--archive",
            "artifacts/runtime_backups/runtime_backup_20260406T120000Z.zip",
            "--no-safety-backup",
            "--safety-output-dir",
            "artifacts/runtime_backups",
        ]
    ]


def test_run_runtime_prune_task_builds_command(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_runtime_prune", "scripts/dev.py")
    calls: list[list[str]] = []

    monkeypatch.setattr(dev_module, "run_command", lambda command, **kwargs: calls.append(list(command)))

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "runtime-prune",
            "--prune-backups-dir",
            "artifacts/runtime_backups",
            "--prune-keep-latest-backups",
            "5",
            "--prune-max-backup-age-days",
            "14",
            "--prune-max-session-age-seconds",
            "2592000",
            "--prune-max-failure-age-days",
            "30",
            "--prune-vacuum-checkpoints",
            "--prune-checkpoint-backend",
            "postgres",
            "--prune-checkpoint-db",
            "postgresql://user:password@localhost:5432/moyuan",
        ]
    )

    dev_module.run_runtime_prune_task("python", args)

    assert calls == [
        [
            "python",
            "scripts/runtime_prune.py",
            "--backups-dir",
            "artifacts/runtime_backups",
            "--keep-latest-backups",
            "5",
            "--max-backup-age-days",
            "14",
            "--max-session-age-seconds",
            "2592000",
            "--max-failure-age-days",
            "30",
            "--vacuum-checkpoints",
            "--checkpoint-backend",
            "postgres",
            "--checkpoint-db",
            "postgresql://user:password@localhost:5432/moyuan",
        ]
    ]


def test_run_agent_replay_task_requires_session_id(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_agent_replay_missing", "scripts/dev.py")

    monkeypatch.setattr(dev_module, "run_command", lambda *args, **kwargs: None)

    parser = dev_module.build_parser()
    args = parser.parse_args(["agent-replay"])

    with pytest.raises(SystemExit):
        dev_module.run_agent_replay_task("python", args)


def test_run_agent_replay_task_builds_command(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_agent_replay", "scripts/dev.py")
    calls: list[list[str]] = []

    monkeypatch.setattr(dev_module, "run_command", lambda command, **kwargs: calls.append(list(command)))

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "agent-replay",
            "--replay-session-id",
            "session-123",
            "--replay-db",
            "postgresql://user:password@localhost:5432/moyuan",
            "--replay-checkpoint-backend",
            "postgres",
            "--replay-checkpoint-id",
            "checkpoint-456",
            "--replay-checkpoint-ns",
            "agent",
            "--replay-dry-run",
        ]
    )

    dev_module.run_agent_replay_task("python", args)

    assert calls == [
        [
            "python",
            "scripts/agent_replay.py",
            "--session-id",
            "session-123",
            "--db",
            "postgresql://user:password@localhost:5432/moyuan",
            "--checkpoint-backend",
            "postgres",
            "--checkpoint-id",
            "checkpoint-456",
            "--checkpoint-ns",
            "agent",
            "--dry-run",
        ]
    ]


def test_run_runtime_maintenance_task_orders_backup_doctor_prune(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_runtime_maintenance", "scripts/dev.py")
    calls: list[tuple[str, bool, bool, bool]] = []

    monkeypatch.setattr(
        dev_module,
        "run_runtime_backup_task",
        lambda python, args: calls.append(("backup", args.runtime_doctor_json, args.prune_vacuum_checkpoints, args.replay_dry_run)),
    )
    monkeypatch.setattr(
        dev_module,
        "run_runtime_doctor",
        lambda python, args: calls.append(("doctor", args.runtime_doctor_json, args.prune_vacuum_checkpoints, args.replay_dry_run)),
    )
    monkeypatch.setattr(
        dev_module,
        "run_runtime_prune_task",
        lambda python, args: calls.append(("prune", args.runtime_doctor_json, args.prune_vacuum_checkpoints, args.replay_dry_run)),
    )

    parser = dev_module.build_parser()
    args = parser.parse_args(["runtime-maintenance"])

    dev_module.run_runtime_maintenance_task("python", args)

    assert calls == [
        ("backup", True, False, False),
        ("doctor", True, False, False),
        ("prune", True, False, False),
    ]


def test_run_checkpoint_maintenance_task_orders_prune_replay_doctor(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_checkpoint_maintenance", "scripts/dev.py")
    calls: list[tuple[str, bool, bool, bool]] = []

    monkeypatch.setattr(
        dev_module,
        "run_runtime_prune_task",
        lambda python, args: calls.append(("prune", args.runtime_doctor_json, args.prune_vacuum_checkpoints, args.replay_dry_run)),
    )
    monkeypatch.setattr(
        dev_module,
        "run_agent_replay_task",
        lambda python, args: calls.append(("replay", args.runtime_doctor_json, args.prune_vacuum_checkpoints, args.replay_dry_run)),
    )
    monkeypatch.setattr(
        dev_module,
        "run_runtime_doctor",
        lambda python, args: calls.append(("doctor", args.runtime_doctor_json, args.prune_vacuum_checkpoints, args.replay_dry_run)),
    )

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "checkpoint-maintenance",
            "--replay-session-id",
            "session-123",
        ]
    )

    dev_module.run_checkpoint_maintenance_task("python", args)

    assert calls == [
        ("prune", True, True, True),
        ("replay", True, True, True),
        ("doctor", True, True, True),
    ]


def test_build_backend_test_command_for_runtime_slice(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_backend_test_run", "scripts/dev.py")

    monkeypatch.setattr(dev_module, "ensure_python_module", lambda *args, **kwargs: None)

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "backend-test",
            "--pytest-slice",
            "runtime",
        ]
    )

    command = dev_module.build_backend_test_command("python", args)

    assert command == [
        "python",
        "-m",
        "pytest",
        "tests/test_agent_runtime_phase1_unit.py",
        "tests/test_agent_subagent_phase2_unit.py",
        "tests/test_runtime_flow_contract_unit.py",
        "tests/test_runtime_source_adapters_unit.py",
        "tests/test_runtime_event_emitters_unit.py",
        "tests/test_runtime_contract_audit_script_unit.py",
        "tests/test_chat_stream_local.py",
        "tests/test_chat_service_health_metrics_unit.py",
        "tests/test_langchain_1x_agent_unit.py",
        "-q",
    ]


def test_build_backend_test_command_appends_explicit_paths(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_backend_test_paths", "scripts/dev.py")

    monkeypatch.setattr(dev_module, "ensure_python_module", lambda *args, **kwargs: None)

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "backend-test",
            "--pytest-slice",
            "unit",
            "--pytest-path",
            "tests/test_runtime_doctor_unit.py",
        ]
    )

    command = dev_module.build_backend_test_command("python", args)

    assert command == [
        "python",
        "-m",
        "pytest",
        "tests",
        "tests/test_runtime_doctor_unit.py",
        "-m",
        "unit and not local and not external_api",
        "-q",
    ]


def test_run_benchmark_report_builds_default_command(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_benchmark_report", "scripts/dev.py")
    calls: list[list[str]] = []

    monkeypatch.setattr(dev_module, "run_command", lambda command, **kwargs: calls.append(list(command)))

    dev_module.run_benchmark_report("python")

    assert calls == [
        [
            "python",
            "scripts/agent_benchmark.py",
            "--output-dir",
            "docs/benchmarks",
        ]
    ]


def test_run_golden_report_builds_default_command(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_golden_report", "scripts/dev.py")
    calls: list[list[str]] = []

    monkeypatch.setattr(dev_module, "run_command", lambda command, **kwargs: calls.append(list(command)))

    dev_module.run_golden_report("python")

    assert calls == [
        [
            "python",
            "scripts/agent_golden_eval.py",
            "--dataset",
            "tests/golden/agent_react_golden.json",
            "--report",
            "docs/benchmarks/agent_golden_eval_latest.json",
            "--min-pass-rate",
            "0.0",
        ]
    ]


def test_run_quality_gate_builds_default_command(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_quality_gate", "scripts/dev.py")
    calls: list[list[str]] = []

    monkeypatch.setattr(dev_module, "run_command", lambda command, **kwargs: calls.append(list(command)))

    dev_module.run_quality_gate("python")

    assert calls == [
        [
            "python",
            "scripts/agent_quality_gate.py",
            "--golden-report",
            "docs/benchmarks/agent_golden_eval_latest.json",
            "--benchmark-report",
            "docs/benchmarks/agent_benchmark_latest.json",
            "--baseline-benchmark-report",
            "docs/benchmarks/agent_benchmark_baseline.json",
            "--min-golden-pass-rate",
            "0.96",
            "--max-golden-hallucination-rate",
            "0.05",
            "--min-benchmark-success-rate",
            "0.60",
            "--max-benchmark-hallucination-rate",
            "0.05",
            "--max-benchmark-fallback-steps-total",
            "5",
            "--max-success-rate-regression",
            "0.05",
            "--max-hallucination-rate-regression",
            "0.02",
            "--max-fallback-steps-regression",
            "2",
        ]
    ]


def test_run_release_harness_scorecard_builds_default_command(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_release_scorecard", "scripts/dev.py")
    calls: list[list[str]] = []

    monkeypatch.setattr(dev_module, "run_command", lambda command, **kwargs: calls.append(list(command)))

    dev_module.run_release_harness_scorecard("python")

    assert calls == [
        [
            "python",
            "scripts/release_harness_scorecard.py",
            "--output-dir",
            "docs/benchmarks",
            "--strict",
        ]
    ]


def test_run_support_bundle_uses_default_base_url(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_support_bundle", "scripts/dev.py")
    calls: list[list[str]] = []

    monkeypatch.setattr(dev_module, "run_command", lambda command, **kwargs: calls.append(list(command)))

    parser = dev_module.build_parser()
    args = parser.parse_args(["support-bundle"])

    dev_module.run_support_bundle("python", args)

    assert calls == [
        [
            "python",
            "scripts/export_support_bundle.py",
            "--base-url",
            "http://localhost:38083",
        ]
    ]


def test_run_release_manifest_includes_release_tag_when_present(monkeypatch):
    dev_module = load_module("test_dev_script_unit_dev_release_manifest", "scripts/dev.py")
    calls: list[list[str]] = []

    monkeypatch.setattr(dev_module, "run_command", lambda command, **kwargs: calls.append(list(command)))

    parser = dev_module.build_parser()
    args = parser.parse_args(
        [
            "release-manifest",
            "--git-sha",
            "abc1234",
            "--git-ref",
            "refs/tags/v9.9.9",
            "--release-tag",
            "v9.9.9",
            "--owner",
            "openai",
        ]
    )

    dev_module.run_release_manifest("python", args)

    assert calls == [
        [
            "python",
            "scripts/export_release_manifest.py",
            "--git-sha",
            "abc1234",
            "--git-ref",
            "refs/tags/v9.9.9",
            "--owner",
            "openai",
            "--release-tag",
            "v9.9.9",
        ]
    ]
