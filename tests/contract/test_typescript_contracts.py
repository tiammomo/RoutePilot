"""Lightweight safeguards for the committed TypeScript contract surface."""

from __future__ import annotations

from pathlib import Path

from routepilot_contracts.validation import CONTRACT_MODELS


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
TYPESCRIPT_CONTRACT = (
    REPOSITORY_ROOT / "packages/typescript/contracts_generated/index.ts"
).read_text(encoding="utf-8")


def test_typescript_contract_map_contains_every_python_contract() -> None:
    for contract_name in (*CONTRACT_MODELS, "RunEvent@1"):
        assert f'"{contract_name}"' in TYPESCRIPT_CONTRACT


def test_typescript_exports_a_discriminated_run_event_union_and_v1_constant() -> None:
    for event_type in (
        "run.accepted",
        "run.lifecycle_changed",
        "run.phase_changed",
        "agent.activity",
        "artifact.candidate_updated",
        "artifact.published",
        "citation.added",
        "risk.detected",
        "input.required",
        "approval.required",
        "run.completed",
        "run.failed",
        "run.canceled",
        "heartbeat",
    ):
        assert f'"{event_type}"' in TYPESCRIPT_CONTRACT
    assert "export type RunEvent =" in TYPESCRIPT_CONTRACT
    assert "schema_version: 1;" in TYPESCRIPT_CONTRACT
    assert "CONTRACT_SCHEMA_VERSIONS" in TYPESCRIPT_CONTRACT
