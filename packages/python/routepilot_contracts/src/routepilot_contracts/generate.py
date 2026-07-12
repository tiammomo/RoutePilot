"""Generate committed JSON Schema documents from the Pydantic contracts."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .artifacts import (
    CandidateSet,
    ConstraintReport,
    EvidenceBundle,
    ItineraryPlan,
    SemanticRiskReport,
    ShareSnapshot,
    TravelAnswer,
    TravelQuestion,
    TripBrief,
    TripSnapshot,
    ValidationReport,
)
from .events import RUN_EVENT_ADAPTER


SCHEMA_BASE_URI = "https://schemas.routepilot.dev/v1"
SCHEMA_DIALECT = "https://json-schema.org/draft/2020-12/schema"

SCHEMA_TARGETS: dict[str, tuple[str, type[BaseModel]]] = {
    "artifacts/travel-question.v1.schema.json": ("TravelQuestion@1", TravelQuestion),
    "artifacts/travel-answer.v1.schema.json": ("TravelAnswer@1", TravelAnswer),
    "artifacts/trip-brief.v1.schema.json": ("TripBrief@1", TripBrief),
    "artifacts/evidence-bundle.v1.schema.json": ("EvidenceBundle@1", EvidenceBundle),
    "artifacts/candidate-set.v1.schema.json": ("CandidateSet@1", CandidateSet),
    "artifacts/itinerary-plan.v1.schema.json": ("ItineraryPlan@1", ItineraryPlan),
    "artifacts/constraint-report.v1.schema.json": ("ConstraintReport@1", ConstraintReport),
    "artifacts/semantic-risk-report.v1.schema.json": (
        "SemanticRiskReport@1",
        SemanticRiskReport,
    ),
    "artifacts/validation-report.v1.schema.json": ("ValidationReport@1", ValidationReport),
    "artifacts/trip-snapshot.v1.schema.json": ("TripSnapshot@1", TripSnapshot),
    "artifacts/share-snapshot.v1.schema.json": ("ShareSnapshot@1", ShareSnapshot),
}


def _decorate_schema(schema: dict[str, Any], relative_path: str, contract: str) -> dict[str, Any]:
    return {
        "$schema": SCHEMA_DIALECT,
        "$id": f"{SCHEMA_BASE_URI}/{relative_path}",
        "x-routepilot-contract": contract,
        **schema,
    }


def build_schema_documents() -> dict[str, dict[str, Any]]:
    """Return all canonical schemas keyed by their repository-relative schema path."""

    documents = {
        relative_path: _decorate_schema(
            model.model_json_schema(mode="validation"), relative_path, contract
        )
        for relative_path, (contract, model) in SCHEMA_TARGETS.items()
    }
    event_path = "events/run-event.v1.schema.json"
    documents[event_path] = _decorate_schema(
        RUN_EVENT_ADAPTER.json_schema(mode="validation"), event_path, "RunEvent@1"
    )
    return documents


def write_schema_documents(output_root: Path) -> None:
    """Write schemas deterministically so drift is visible in code review."""

    for relative_path, document in build_schema_documents().items():
        destination = output_root / relative_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(
            json.dumps(document, ensure_ascii=False, indent=2, sort_keys=False) + "\n",
            encoding="utf-8",
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path.cwd() / "schemas",
        help="schema output directory (default: ./schemas)",
    )
    args = parser.parse_args()
    write_schema_documents(args.output_root)


if __name__ == "__main__":
    main()
