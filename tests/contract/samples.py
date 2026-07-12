"""Reusable, non-sensitive golden payload builders for v1 contract tests."""

from __future__ import annotations

from copy import deepcopy
from typing import Any


NOW = "2026-07-12T10:00:00Z"
LATER = "2026-07-13T10:00:00Z"
TIMEZONE = "Asia/Shanghai"


def source(
    source_id: str,
    *,
    kind: str = "rag",
    name: str = "RoutePilot knowledge base",
    version: str = "2026-07-12",
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "kind": kind,
        "name": name,
        "version": version,
        "uri": "https://example.com/source",
        "retrieved_at": NOW,
        "publisher": "RoutePilot",
        "license": "fixture-only",
    }


def artifact_ref(artifact_type: str, artifact_id: str, version: int = 1) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "schema_version": 1,
        "version": version,
    }


def artifact_header(artifact_type: str, artifact_id: str) -> dict[str, Any]:
    return {
        "artifact_type": artifact_type,
        "artifact_id": artifact_id,
        "schema_version": 1,
        "version": 1,
        "created_at": NOW,
        "created_by": {"actor_type": "agent", "actor_id": "agent_orchestrator"},
        "reason": "Contract fixture generated for a Beijing planning run.",
    }


def place() -> dict[str, Any]:
    return {
        "place_id": "place_forbidden_city",
        "display_name": "Forbidden City",
        "address": "4 Jingshan Front Street, Beijing",
        "country_code": "CN",
        "timezone": TIMEZONE,
        "location": {
            "latitude": "39.9163",
            "longitude": "116.3972",
            "coordinate_system": "GCJ-02",
            "accuracy_meters": "20",
        },
        "provider_ids": [
            {"provider": "AMap", "place_id": "B000A8UIN8", "version": "api-v3"}
        ],
        "source": source("src_place_001", kind="provider", name="AMap", version="api-v3"),
    }


def money(minimum: str, maximum: str) -> dict[str, Any]:
    return {
        "min_amount": minimum,
        "max_amount": maximum,
        "currency": "CNY",
        "basis": "total",
        "observed_at": NOW,
        "source": source("src_budget_001", kind="user", name="Trip command", version="msg-1"),
    }


def citation() -> dict[str, Any]:
    return {
        "citation_id": "citation_001",
        "evidence_id": "evidence_001",
        "title": "Forbidden City visitor information",
        "locator": "visitor-hours",
        "source": source("src_place_001", kind="provider", name="AMap", version="api-v3"),
    }


def build_valid_contracts() -> dict[str, dict[str, Any]]:
    travel_question = {
        **artifact_header("TravelQuestion", "question_001"),
        "created_by": {"actor_type": "user", "actor_id": "user_001"},
        "question": "带父母去北京，哪些历史文化地点更适合轻松游览？",
        "locale": "zh-CN",
        "destination_hint": "北京",
        "asked_at": NOW,
        "source": source("src_user_question", kind="user", name="Traveler question", version="1"),
    }
    travel_answer = {
        **artifact_header("TravelAnswer", "answer_001"),
        "question_ref": artifact_ref("TravelQuestion", "question_001"),
        "question": travel_question["question"],
        "answer_status": "answered",
        "summary": "优先选择预约规则清晰、可控制步行强度的历史文化地点。",
        "sections": [
            {
                "heading": "优先考虑故宫博物院",
                "body": "建议提前通过官方渠道预约，并为长者预留休息时间。",
                "evidence_refs": ["answer_evidence_001"],
            }
        ],
        "evidence": [
            {
                "evidence_id": "answer_evidence_001",
                "title": "Forbidden City visitor information",
                "statement": "故宫通常需要提前预约，开放安排应以官方页面为准。",
                "source": source("src_answer_001", kind="rag", name="Official visitor page", version="2026-07"),
                "freshness": {
                    "observed_at": NOW,
                    "valid_until": LATER,
                    "status": "fresh",
                    "source": source("src_answer_001", kind="rag", name="Official visitor page", version="2026-07"),
                },
            }
        ],
        "citations": [
            {
                "citation_id": "answer_citation_001",
                "evidence_id": "answer_evidence_001",
                "title": "Forbidden City visitor information",
                "locator": "visitor-information",
                "source": source("src_answer_001", kind="rag", name="Official visitor page", version="2026-07"),
            }
        ],
        "assumptions": ["同行人可以完成短距离步行"],
        "limitations": ["开放时间需要临行复核"],
        "suggested_questions": ["要不要整理成逐日行程？"],
        "generated_at": NOW,
    }
    brief = {
        **artifact_header("TripBrief", "brief_001"),
        "destination": place(),
        "date_window": {
            "start_date": "2026-10-01",
            "end_date": "2026-10-02",
            "timezone": TIMEZONE,
            "flexibility_days": 0,
        },
        "travelers": {
            "adults": 2,
            "children_ages": [],
            "seniors": 2,
            "rooms": 2,
            "accessibility_needs": ["Minimize long walks"],
        },
        "budget": money("2500", "3000"),
        "preferences": [
            {
                "preference_id": "preference_pace",
                "category": "pace",
                "value": "relaxed",
                "priority": 5,
            }
        ],
        "constraints": [
            {
                "constraint_id": "constraint_walk",
                "constraint_type": "mobility",
                "hard": True,
                "priority": 5,
                "description": "Keep walking below five kilometres per day.",
                "source": source(
                    "src_user_001", kind="user", name="Trip command", version="msg-1"
                ),
            }
        ],
        "clarification_items": [
            {
                "question_id": "question_hotel",
                "prompt": "Should lodging be included?",
                "required": True,
                "status": "answered",
                "answer": "Yes, include lodging.",
            }
        ],
        "source": source("src_user_001", kind="user", name="Trip command", version="msg-1"),
    }

    evidence_bundle = {
        **artifact_header("EvidenceBundle", "bundle_001"),
        "trip_brief_ref": artifact_ref("TripBrief", "brief_001"),
        "timezone": TIMEZONE,
        "evidence": [
            {
                "evidence_id": "evidence_001",
                "kind": "opening_hours",
                "title": "Forbidden City visitor information",
                "summary": "Morning entry leaves a relaxed afternoon buffer.",
                "place_ref": place(),
                "claims": [
                    {
                        "claim_id": "claim_hours_001",
                        "statement": "A morning visit is feasible for the selected date.",
                        "confidence": "0.95",
                    }
                ],
                "source": source(
                    "src_place_001", kind="provider", name="AMap", version="api-v3"
                ),
                "freshness": {
                    "observed_at": NOW,
                    "valid_until": LATER,
                    "status": "fresh",
                    "source": source(
                        "src_place_001", kind="provider", name="AMap", version="api-v3"
                    ),
                },
                "retrieved_at": NOW,
            }
        ],
        "citations": [citation()],
        "conflicts": [],
    }

    candidate_set = {
        **artifact_header("CandidateSet", "candidates_001"),
        "trip_brief_ref": artifact_ref("TripBrief", "brief_001"),
        "evidence_bundle_ref": artifact_ref("EvidenceBundle", "bundle_001"),
        "timezone": TIMEZONE,
        "candidates": [
            {
                "candidate_id": "candidate_001",
                "category": "poi",
                "place_ref": place(),
                "rationale": "High evidence coverage and accessible morning timing.",
                "evidence_refs": ["evidence_001"],
                "score": "0.93",
                "estimated_cost": money("240", "280"),
                "recommended_duration_minutes": 180,
                "tags": ["culture", "accessible"],
            }
        ],
        "selection_notes": ["Keep a taxi alternative for the senior travelers."],
    }

    itinerary = {
        **artifact_header("ItineraryPlan", "plan_001"),
        "plan_id": "plan_candidate_001",
        "status": "published",
        "trip_brief_ref": artifact_ref("TripBrief", "brief_001"),
        "candidate_set_ref": artifact_ref("CandidateSet", "candidates_001"),
        "evidence_bundle_ref": artifact_ref("EvidenceBundle", "bundle_001"),
        "timezone": TIMEZONE,
        "assumptions": [
            {
                "assumption_id": "assumption_entry",
                "text": "The party can obtain timed-entry tickets.",
                "source": source(
                    "src_agent_001", kind="agent", name="Planner", version="planner-v1"
                ),
                "evidence_refs": ["evidence_001"],
            }
        ],
        "days": [
            {
                "date": "2026-10-01",
                "timezone": TIMEZONE,
                "time_blocks": [
                    {
                        "block_id": "block_001",
                        "title": "Forbidden City",
                        "category": "visit",
                        "place_ref": place(),
                        "time_range": {
                            "local_date": "2026-10-01",
                            "start_local_time": "09:00:00",
                            "end_local_time": "12:00:00",
                            "end_day_offset": 0,
                            "timezone": TIMEZONE,
                        },
                        "duration_minutes": 180,
                        "transit_from_previous": None,
                        "cost_range": money("240", "280"),
                        "evidence_refs": ["evidence_001"],
                        "alternatives": [],
                    }
                ],
                "day_summary": "A low-intensity cultural morning with afternoon buffer.",
                "daily_cost": money("800", "1000"),
            }
        ],
        "budget_summary": {
            "estimated_total": money("2500", "2900"),
            "category_totals": [
                {"category": "tickets", "cost": money("240", "280")}
            ],
            "contingency_percent": "10",
        },
        "route_summary": {
            "total_distance_meters": 4200,
            "total_transit_duration_minutes": 45,
            "legs_count": 2,
            "source": source(
                "src_route_001", kind="provider", name="AMap Routes", version="api-v3"
            ),
        },
        "citations": [citation()],
        "unresolved_risks": [],
        "validation_ref": None,
    }

    constraint_report = {
        **artifact_header("ConstraintReport", "constraints_001"),
        "plan_ref": artifact_ref("ItineraryPlan", "plan_001"),
        "timezone": TIMEZONE,
        "checked_at": NOW,
        "engine": {"name": "RoutePilot ValidationService", "version": "1.0.0"},
        "outcome": "pass",
        "checks": [
            {
                "check_id": "check_walk_001",
                "constraint_ref": "constraint_walk",
                "category": "hard_constraint",
                "outcome": "pass",
                "message": "Daily walking remains under the requested limit.",
                "source": source(
                    "src_route_001", kind="provider", name="AMap Routes", version="api-v3"
                ),
                "related_block_ids": ["block_001"],
                "observations": [
                    {"metric": "walking_distance", "value": "4200", "unit": "meter"}
                ],
            }
        ],
        "summary": {"passed": 1, "warnings": 0, "failed": 0},
    }

    semantic_report = {
        **artifact_header("SemanticRiskReport", "semantic_001"),
        "plan_ref": artifact_ref("ItineraryPlan", "plan_001"),
        "evidence_bundle_ref": artifact_ref("EvidenceBundle", "bundle_001"),
        "timezone": TIMEZONE,
        "assessed_at": NOW,
        "reviewer": {"name": "RoutePilot Verifier", "version": "verifier-v1"},
        "assessment_source": source(
            "src_verifier_001", kind="agent", name="Verifier", version="verifier-v1"
        ),
        "outcome": "pass",
        "evidence_coverage": {
            "claims_total": 1,
            "claims_supported": 1,
            "claims_missing": 0,
            "coverage_ratio": "1",
        },
        "risks": [],
        "source_conflicts": [],
    }

    validation_report = {
        **artifact_header("ValidationReport", "validation_001"),
        "plan_ref": artifact_ref("ItineraryPlan", "plan_001"),
        "constraint_report_ref": artifact_ref("ConstraintReport", "constraints_001"),
        "semantic_risk_report_ref": artifact_ref("SemanticRiskReport", "semantic_001"),
        "timezone": TIMEZONE,
        "generated_at": NOW,
        "policy_version": "publication-policy-v1",
        "verdict": "pass",
        "publishable": True,
        "blockers": [],
        "warnings": [],
    }

    snapshot = {
        **artifact_header("TripSnapshot", "snapshot_001"),
        "trip_id": "trip_001",
        "title": "Relaxed Beijing family trip",
        "status": "ready",
        "timezone": TIMEZONE,
        "brief": deepcopy(brief),
        "itinerary": deepcopy(itinerary),
        "validation": deepcopy(validation_report),
        "generated_at": NOW,
        "source_artifact_versions": [
            artifact_ref("TripBrief", "brief_001"),
            artifact_ref("ItineraryPlan", "plan_001"),
            artifact_ref("ValidationReport", "validation_001"),
        ],
    }

    share_snapshot = {
        **artifact_header("ShareSnapshot", "share_snapshot_001"),
        "public_id": "public_trip_001",
        "trip_snapshot_ref": artifact_ref("TripSnapshot", "snapshot_001"),
        "title": "Relaxed Beijing family trip",
        "destination": {
            "display_name": "Beijing",
            "locality": "Beijing",
            "country_code": "CN",
            "approximate_location": {
                "latitude": "39.90",
                "longitude": "116.40",
                "coordinate_system": "GCJ-02",
                "accuracy_meters": 1000,
            },
        },
        "date_window": {
            "start_date": "2026-10-01",
            "end_date": "2026-10-02",
            "timezone": TIMEZONE,
            "flexibility_days": 0,
        },
        "days": [
            {
                "date": "2026-10-01",
                "timezone": TIMEZONE,
                "summary": "A relaxed cultural morning.",
                "time_blocks": [
                    {
                        "block_id": "block_001",
                        "title": "Forbidden City",
                        "category": "visit",
                        "time_range": {
                            "local_date": "2026-10-01",
                            "start_local_time": "09:00:00",
                            "end_local_time": "12:00:00",
                            "end_day_offset": 0,
                            "timezone": TIMEZONE,
                        },
                        "place": {
                            "display_name": "Forbidden City",
                            "locality": "Dongcheng, Beijing",
                            "country_code": "CN",
                            "approximate_location": None,
                        },
                        "transit_from_previous": None,
                        "citation_refs": ["citation_001"],
                    }
                ],
            }
        ],
        "citations": [citation()],
        "published_at": NOW,
    }

    return {
        "TravelQuestion@1": travel_question,
        "TravelAnswer@1": travel_answer,
        "TripBrief@1": brief,
        "EvidenceBundle@1": evidence_bundle,
        "CandidateSet@1": candidate_set,
        "ItineraryPlan@1": itinerary,
        "ConstraintReport@1": constraint_report,
        "SemanticRiskReport@1": semantic_report,
        "ValidationReport@1": validation_report,
        "TripSnapshot@1": snapshot,
        "ShareSnapshot@1": share_snapshot,
    }


def valid_run_events() -> list[dict[str, Any]]:
    base = {
        "event_id": "event_001",
        "schema_version": 1,
        "seq": 1,
        "occurred_at": NOW,
        "trip_id": "trip_001",
        "run_id": "run_001",
        "trace_id": "trace_001",
        "audience": "trip_members",
    }
    plan_ref = artifact_ref("ItineraryPlan", "plan_001")
    events = [
        {"type": "run.accepted", "data": {"lifecycle_state": "queued", "phase": "accepted", "control_version": 1}},
        {"type": "run.lifecycle_changed", "data": {"previous_state": "queued", "lifecycle_state": "running", "control_version": 2, "reason_code": "WORKER_STARTED"}},
        {"type": "run.phase_changed", "data": {"previous_phase": "accepted", "phase": "research", "progress_percent": 20}},
        {"type": "agent.activity", "data": {"agent": "research", "activity": "hybrid_retrieval", "status": "completed", "duration_ms": 420, "sources": [{"kind": "provider", "name": "AMap", "version": "api-v3"}]}},
        {"type": "artifact.candidate_updated", "data": {"artifact_ref": plan_ref, "status": "candidate"}},
        {"type": "artifact.published", "data": {"artifact_ref": plan_ref, "status": "published"}},
        {"type": "citation.added", "data": {"citation": citation(), "artifact_ref": plan_ref}},
        {"type": "risk.detected", "data": {"risk_id": "risk_001", "severity": "low", "message": "Timed entry should be reconfirmed.", "artifact_ref": plan_ref}},
        {"type": "input.required", "data": {"request_id": "request_001", "prompt": "Choose a pace.", "fields": [{"field_id": "field_pace", "label": "Pace", "input_type": "single_select", "required": True, "options": ["relaxed", "packed"]}], "expires_at": LATER}},
        {"type": "approval.required", "data": {"approval_id": "approval_001", "prompt": "Publish this itinerary?", "artifact_ref": plan_ref, "expires_at": LATER}},
        {"type": "run.completed", "data": {"lifecycle_state": "completed", "snapshot_ref": artifact_ref("TripSnapshot", "snapshot_001"), "duration_ms": 1820}},
        {"type": "run.failed", "data": {"lifecycle_state": "failed", "failed_phase": "research", "error": {"code": "PROVIDER_TIMEOUT", "message": "A travel data provider timed out.", "retryable": True}}},
        {"type": "run.canceled", "data": {"lifecycle_state": "canceled", "canceled_by": "user", "reason": "Plans changed."}},
        {"type": "heartbeat", "data": {"server_time": NOW}},
    ]
    result = []
    for index, event in enumerate(events, start=1):
        envelope = deepcopy(base)
        envelope["event_id"] = f"event_{index:03d}"
        envelope["seq"] = index
        envelope.update(event)
        result.append(envelope)
    return result
