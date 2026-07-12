"""Committed JSON Schema compatibility and validation tests."""

from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from routepilot_contracts.generate import build_schema_documents

from .samples import build_valid_contracts, valid_run_events

jsonschema = pytest.importorskip(
    "jsonschema", reason="install routepilot-contracts[test] to validate JSON Schema documents"
)
Draft202012Validator = jsonschema.Draft202012Validator
FormatChecker = jsonschema.FormatChecker


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SCHEMA_ROOT = REPOSITORY_ROOT / "schemas"


def _load(relative_path: str) -> dict[str, Any]:
    return json.loads((SCHEMA_ROOT / relative_path).read_text(encoding="utf-8"))


def _walk(value: Any):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _schema_by_contract() -> dict[str, dict[str, Any]]:
    return {
        document["x-routepilot-contract"]: document
        for document in build_schema_documents().values()
    }


def test_committed_schemas_are_in_sync_with_the_python_source_of_truth() -> None:
    generated = build_schema_documents()

    assert len(generated) == 10
    for relative_path, expected in generated.items():
        assert _load(relative_path) == expected, f"regenerate stale schema: {relative_path}"


@pytest.mark.parametrize("relative_path", sorted(build_schema_documents()))
def test_every_schema_is_valid_draft_2020_12_and_all_objects_are_closed(
    relative_path: str,
) -> None:
    schema = _load(relative_path)

    Draft202012Validator.check_schema(schema)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"].endswith(relative_path)
    assert schema["x-routepilot-contract"].endswith("@1")
    object_nodes = [node for node in _walk(schema) if node.get("type") == "object"]
    assert object_nodes
    assert all(node.get("additionalProperties") is False for node in object_nodes)
    version_nodes = [
        node["properties"]["schema_version"]
        for node in object_nodes
        if "schema_version" in node.get("properties", {})
    ]
    assert version_nodes
    assert all(node.get("const") == 1 for node in version_nodes)


@pytest.mark.parametrize("contract_name", sorted(build_valid_contracts()))
def test_json_schemas_accept_valid_artifact_samples(contract_name: str) -> None:
    schema = _schema_by_contract()[contract_name]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    validator.validate(build_valid_contracts()[contract_name])


@pytest.mark.parametrize("contract_name", sorted(build_valid_contracts()))
def test_json_schemas_reject_extra_fields_and_wrong_versions(contract_name: str) -> None:
    schema = _schema_by_contract()[contract_name]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    with_extra = deepcopy(build_valid_contracts()[contract_name])
    with_extra["private_payload"] = "forbidden"
    wrong_version = deepcopy(build_valid_contracts()[contract_name])
    wrong_version["schema_version"] = 2

    assert list(validator.iter_errors(with_extra))
    assert list(validator.iter_errors(wrong_version))


@pytest.mark.parametrize("event", valid_run_events(), ids=lambda event: event["type"])
def test_run_event_json_schema_accepts_every_public_variant(event: dict[str, Any]) -> None:
    schema = _schema_by_contract()["RunEvent@1"]

    Draft202012Validator(schema, format_checker=FormatChecker()).validate(event)


def test_run_event_json_schema_rejects_wrong_data_and_unknown_fields() -> None:
    schema = _schema_by_contract()["RunEvent@1"]
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    mismatched = valid_run_events()[0]
    mismatched["type"] = "run.completed"
    leaked = valid_run_events()[3]
    leaked["data"]["provider_raw_payload"] = {"secret": "forbidden"}

    assert list(validator.iter_errors(mismatched))
    assert list(validator.iter_errors(leaked))


def test_schema_provenance_and_domain_value_objects_are_explicit() -> None:
    documents = build_schema_documents().values()
    serialized = "\n".join(json.dumps(document, sort_keys=True) for document in documents)

    for required_marker in (
        '"format": "iana-time-zone"',
        '"currency"',
        '"coordinate_system"',
        '"source"',
        '"version"',
    ):
        assert required_marker in serialized
