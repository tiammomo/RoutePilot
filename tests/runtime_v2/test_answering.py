"""Grounded lightweight travel-answer Agent tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from agent.travel_agent.a2a.models import AgentExecutionContext, AgentInvocation, ArtifactInput
from agent.travel_agent.runtime_v2.a2a_executors import AnsweringA2AExecutor
from routepilot_contracts import validate_contract
from routepilot_contracts.artifacts import TravelAnswer, TravelQuestion
from tests.contract.samples import build_valid_contracts


def context() -> AgentExecutionContext:
    return AgentExecutionContext(
        tenant_id="tenant-a",
        actor_id="user-a",
        agent_interface_id="answering",
        task_id="task-answer-1",
        context_id="context-answer-1",
        run_id="run-answer-1",
        dispatch_id="dispatch-answer-1",
        deadline=datetime.now(UTC) + timedelta(seconds=30),
    )


def question(*, destination: str | None = "北京") -> TravelQuestion:
    payload = build_valid_contracts()["TravelQuestion@1"]
    payload["destination_hint"] = destination
    parsed = validate_contract("TravelQuestion@1", payload)
    assert isinstance(parsed, TravelQuestion)
    return parsed


@pytest.mark.asyncio
async def test_answering_agent_returns_citation_ready_catalog_answer_without_model() -> None:
    value = question()
    result = await AnsweringA2AExecutor().execute(
        context(),
        AgentInvocation(
            goal=value.question,
            artifacts=[
                ArtifactInput(contract="TravelQuestion@1", payload=value.model_dump(mode="json"))
            ],
        ),
        None,
    )

    assert result.kind == "completed"
    parsed = validate_contract("TravelAnswer@1", result.artifacts[0].payload)
    assert isinstance(parsed, TravelAnswer)
    assert parsed.answer_status == "answered"
    assert len(parsed.evidence) >= 3
    assert all(section.evidence_refs for section in parsed.sections)
    assert all(citation.source.uri is not None for citation in parsed.citations)


@pytest.mark.asyncio
async def test_answering_agent_fails_closed_when_no_grounded_evidence_exists() -> None:
    value = question(destination=None)
    result = await AnsweringA2AExecutor().execute(
        context(),
        AgentInvocation(
            goal=value.question,
            artifacts=[
                ArtifactInput(contract="TravelQuestion@1", payload=value.model_dump(mode="json"))
            ],
        ),
        None,
    )

    parsed = validate_contract("TravelAnswer@1", result.artifacts[0].payload)
    assert isinstance(parsed, TravelAnswer)
    assert parsed.answer_status == "insufficient_evidence"
    assert parsed.evidence == []
    assert "不编造" in parsed.summary
