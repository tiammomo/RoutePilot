"""Behavioral tests for the Python contract validation entry points."""

from __future__ import annotations

from copy import deepcopy

import pytest
from pydantic import ValidationError

from routepilot_contracts import validate_artifact, validate_contract, validate_run_event

from .samples import build_valid_contracts, valid_run_events


@pytest.mark.parametrize("contract_name", sorted(build_valid_contracts()))
def test_each_valid_artifact_contract_is_accepted(contract_name: str) -> None:
    payload = build_valid_contracts()[contract_name]

    parsed = validate_contract(contract_name, payload)

    assert parsed.schema_version == 1
    assert f"{parsed.artifact_type}@{parsed.schema_version}" == contract_name
    assert validate_artifact(payload) == parsed


@pytest.mark.parametrize("event", valid_run_events(), ids=lambda event: event["type"])
def test_each_public_run_event_variant_is_accepted(event: dict[str, object]) -> None:
    parsed = validate_run_event(event)

    assert parsed.schema_version == 1
    assert parsed.type == event["type"]


@pytest.mark.parametrize("contract_name", sorted(build_valid_contracts()))
def test_all_artifact_objects_reject_unknown_top_level_fields(contract_name: str) -> None:
    payload = deepcopy(build_valid_contracts()[contract_name])
    payload["internal_debug_payload"] = {"raw": "must never cross the boundary"}

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_contract(contract_name, payload)


@pytest.mark.parametrize("contract_name", sorted(build_valid_contracts()))
def test_all_artifacts_reject_an_unrecognized_schema_version(contract_name: str) -> None:
    payload = deepcopy(build_valid_contracts()[contract_name])
    payload["schema_version"] = 2

    with pytest.raises(ValidationError):
        validate_contract(contract_name, payload)


def test_nested_objects_also_reject_unknown_fields() -> None:
    payload = build_valid_contracts()["TripBrief@1"]
    payload["destination"]["location"]["implicit_coordinate_system"] = "forbidden"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_contract("TripBrief@1", payload)


@pytest.mark.parametrize(
    ("path", "invalid_value"),
    [
        (("date_window", "timezone"), "UTC+08:00"),
        (("budget", "currency"), "cny"),
        (("destination", "location", "latitude"), "91"),
        (("created_at",), "2026-07-12T10:00:00"),
    ],
)
def test_trip_brief_rejects_invalid_timezone_currency_coordinate_and_timestamp(
    path: tuple[str, ...], invalid_value: str
) -> None:
    payload = build_valid_contracts()["TripBrief@1"]
    target = payload
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = invalid_value

    with pytest.raises(ValidationError):
        validate_contract("TripBrief@1", payload)


def test_source_provenance_requires_an_explicit_version() -> None:
    payload = build_valid_contracts()["EvidenceBundle@1"]
    del payload["evidence"][0]["source"]["version"]

    with pytest.raises(ValidationError):
        validate_contract("EvidenceBundle@1", payload)


def test_decimal_money_range_rejects_reversed_bounds() -> None:
    payload = build_valid_contracts()["TripBrief@1"]
    payload["budget"]["min_amount"] = "3000"
    payload["budget"]["max_amount"] = "2500"

    with pytest.raises(ValidationError, match="min_amount cannot exceed max_amount"):
        validate_contract("TripBrief@1", payload)


def test_evidence_bundle_rejects_unknown_evidence_references() -> None:
    payload = build_valid_contracts()["EvidenceBundle@1"]
    payload["citations"][0]["evidence_id"] = "evidence_missing"

    with pytest.raises(ValidationError, match="unknown evidence"):
        validate_contract("EvidenceBundle@1", payload)


def test_constraint_report_rejects_a_false_summary() -> None:
    payload = build_valid_contracts()["ConstraintReport@1"]
    payload["summary"]["failed"] = 1

    with pytest.raises(ValidationError, match="summary counts"):
        validate_contract("ConstraintReport@1", payload)


def test_semantic_report_rejects_inconsistent_coverage() -> None:
    payload = build_valid_contracts()["SemanticRiskReport@1"]
    payload["evidence_coverage"]["coverage_ratio"] = "0.5"

    with pytest.raises(ValidationError, match="coverage_ratio"):
        validate_contract("SemanticRiskReport@1", payload)


def test_validation_report_enforces_publication_gate() -> None:
    payload = build_valid_contracts()["ValidationReport@1"]
    payload["verdict"] = "fail"
    payload["publishable"] = True

    with pytest.raises(ValidationError, match="cannot be publishable"):
        validate_contract("ValidationReport@1", payload)


def test_trip_snapshot_rejects_mismatched_embedded_versions() -> None:
    payload = build_valid_contracts()["TripSnapshot@1"]
    payload["itinerary"]["trip_brief_ref"]["artifact_id"] = "brief_other"

    with pytest.raises(ValidationError, match="embedded brief"):
        validate_contract("TripSnapshot@1", payload)


@pytest.mark.parametrize("sensitive_field", ["conversation", "members", "exact_budget"])
def test_share_snapshot_is_a_closed_public_whitelist(sensitive_field: str) -> None:
    payload = build_valid_contracts()["ShareSnapshot@1"]
    payload[sensitive_field] = {"secret": "not allowed"}

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_contract("ShareSnapshot@1", payload)


def test_run_event_rejects_mismatched_type_specific_data() -> None:
    payload = valid_run_events()[0]
    payload["type"] = "run.completed"

    with pytest.raises(ValidationError):
        validate_run_event(payload)


def test_run_event_rejects_internal_and_extra_data() -> None:
    payload = valid_run_events()[3]
    payload["data"]["raw_model_output"] = "private chain data"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        validate_run_event(payload)


def test_validation_entry_fails_closed_for_unknown_contract_versions() -> None:
    payload = build_valid_contracts()["TripBrief@1"]

    with pytest.raises(ValueError, match="unsupported contract"):
        validate_contract("TripBrief@2", payload)
