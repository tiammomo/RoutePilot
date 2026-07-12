"""Curated local registry for trusted RoutePilot A2A agent interfaces."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from typing import Protocol, cast

from a2a.types import AgentCapabilities, AgentCard, AgentExtension, AgentInterface, AgentSkill
from google.protobuf.json_format import MessageToDict

from .constants import A2A_PROTOCOL_VERSION, TRAVEL_ARTIFACT_EXTENSION_URI, invocation_schema_uri
from .models import (
    AgentExecutionContext,
    AgentInvocation,
    ContractName,
    ExecutionResult,
    FailedExecution,
    InputResponse,
)


class AgentExecutor(Protocol):
    """Framework-neutral professional-agent execution boundary."""

    async def execute(
        self,
        context: AgentExecutionContext,
        invocation: AgentInvocation,
        input_response: InputResponse | None,
    ) -> ExecutionResult:
        """Execute one idempotent A2A task attempt."""


class UnconfiguredExecutor:
    """Safe default until a real local or remote Agent adapter is installed."""

    async def execute(
        self,
        context: AgentExecutionContext,
        invocation: AgentInvocation,
        input_response: InputResponse | None,
    ) -> ExecutionResult:
        del context, invocation, input_response
        return FailedExecution(
            code="AGENT_IMPLEMENTATION_UNAVAILABLE",
            message="This agent capability is not configured in the current deployment.",
        )


@dataclass(frozen=True, slots=True)
class AgentProfile:
    """Registry policy attached to an official Agent Card."""

    interface_id: str
    skill_id: str
    required_input_contracts: tuple[ContractName, ...]
    allowed_output_contracts: tuple[ContractName, ...]
    card: AgentCard
    executor: AgentExecutor

    @property
    def invocation_schema_uri(self) -> str:
        """Return the only accepted initial structured-Part schema."""

        return invocation_schema_uri(self.interface_id)

    @property
    def etag(self) -> str:
        """Return a stable strong ETag for card cache/revalidation."""

        payload = MessageToDict(self.card, preserving_proto_field_name=False)
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        return f'"{digest}"'


def clone_card(card: AgentCard) -> AgentCard:
    """Return a detached copy of a mutable protobuf Agent Card."""

    cloned = AgentCard()
    cloned.CopyFrom(card)
    return cloned


class AgentRegistry:
    """Allowlist-only registry; it never discovers or trusts arbitrary URLs."""

    def __init__(self) -> None:
        self._profiles: dict[str, AgentProfile] = {}

    def register(self, profile: AgentProfile, *, replace: bool = False) -> None:
        """Register one curated interface and reject accidental shadowing."""

        if profile.interface_id in self._profiles and not replace:
            raise ValueError(f"agent interface already registered: {profile.interface_id}")
        self._profiles[profile.interface_id] = profile

    def get(self, interface_id: str) -> AgentProfile:
        """Resolve one trusted interface."""

        try:
            return self._profiles[interface_id]
        except KeyError as exc:
            raise KeyError(f"unknown agent interface: {interface_id}") from exc

    def list_profiles(self) -> tuple[AgentProfile, ...]:
        """List curated interfaces in deterministic order."""

        return tuple(self._profiles[key] for key in sorted(self._profiles))

    def select_for_skill(self, skill_id: str) -> AgentProfile:
        """Select an allowlisted interface by exact skill identifier."""

        matches = [profile for profile in self._profiles.values() if profile.skill_id == skill_id]
        if len(matches) != 1:
            raise KeyError(f"no unique agent interface for skill: {skill_id}")
        return matches[0]


def _build_card(
    *,
    base_url: str,
    interface_id: str,
    name: str,
    description: str,
    skill_id: str,
    skill_name: str,
    tags: list[str],
) -> AgentCard:
    endpoint = f"{base_url.rstrip('/')}/agents/{interface_id}/rpc"
    return AgentCard(
        name=name,
        description=description,
        version="1.0.0",
        supported_interfaces=[
            AgentInterface(
                url=endpoint,
                protocol_binding="JSONRPC",
                protocol_version=A2A_PROTOCOL_VERSION,
            )
        ],
        capabilities=AgentCapabilities(
            streaming=True,
            push_notifications=False,
            extended_agent_card=True,
            extensions=[
                AgentExtension(
                    uri=TRAVEL_ARTIFACT_EXTENSION_URI,
                    description=(
                        "Versioned RoutePilot travel artifacts and reliable dispatch metadata."
                    ),
                    required=True,
                )
            ],
        ),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id=skill_id,
                name=skill_name,
                description=description,
                tags=tags,
                input_modes=["application/json"],
                output_modes=["application/json"],
            )
        ],
    )


def build_default_registry(
    *,
    base_url: str | None = None,
    executors: dict[str, AgentExecutor] | None = None,
) -> AgentRegistry:
    """Build the curated V1 cards with optionally injected real executors."""

    resolved_base_url = cast(
        str,
        base_url
        or os.getenv(
            "ROUTEPILOT_A2A_PUBLIC_BASE_URL",
            "http://localhost:38083/api/v1/a2a",
        ),
    )
    executor_map = executors or {}
    fallback = UnconfiguredExecutor()
    specifications = (
        (
            "answering",
            "RoutePilot Answering Agent",
            "Answers travel questions from bounded RAG and live-provider evidence.",
            "travel.answer.v1",
            "Grounded travel answering",
            ["travel", "answering", "rag", "evidence"],
            ("TravelQuestion@1",),
            ("TravelAnswer@1",),
        ),
        (
            "research",
            "RoutePilot Research Agent",
            "Retrieves grounded travel evidence and destination candidates.",
            "travel.research.v1",
            "Travel research",
            ["travel", "research", "evidence"],
            ("TripBrief@1",),
            ("EvidenceBundle@1", "CandidateSet@1"),
        ),
        (
            "planner",
            "RoutePilot Planner Agent",
            "Builds candidate itineraries from validated travel evidence.",
            "travel.plan.v1",
            "Itinerary planning",
            ["travel", "planning", "itinerary"],
            ("TripBrief@1", "EvidenceBundle@1", "CandidateSet@1"),
            ("ItineraryPlan@1",),
        ),
        (
            "validation",
            "RoutePilot Validation Service Agent",
            "Runs deterministic route, time, budget, hours and hard-constraint checks.",
            "travel.validate.v1",
            "Deterministic validation",
            ["travel", "validation", "constraints"],
            ("TripBrief@1", "ItineraryPlan@1", "EvidenceBundle@1"),
            ("ConstraintReport@1",),
        ),
        (
            "semantic-verifier",
            "RoutePilot Semantic Verifier Agent",
            "Reviews evidence coverage, assumptions, conflicts and semantic risks.",
            "travel.verify.v1",
            "Semantic verification",
            ["travel", "verification", "risk"],
            (
                "TripBrief@1",
                "ItineraryPlan@1",
                "EvidenceBundle@1",
                "ConstraintReport@1",
            ),
            ("SemanticRiskReport@1",),
        ),
    )
    registry = AgentRegistry()
    for (
        interface_id,
        name,
        description,
        skill_id,
        skill_name,
        tags,
        required_inputs,
        allowed_outputs,
    ) in specifications:
        card = _build_card(
            base_url=resolved_base_url,
            interface_id=interface_id,
            name=name,
            description=description,
            skill_id=skill_id,
            skill_name=skill_name,
            tags=tags,
        )
        registry.register(
            AgentProfile(
                interface_id=interface_id,
                skill_id=skill_id,
                required_input_contracts=cast(tuple[ContractName, ...], required_inputs),
                allowed_output_contracts=cast(tuple[ContractName, ...], allowed_outputs),
                card=card,
                executor=executor_map.get(interface_id, fallback),
            )
        )
    return registry


__all__ = [
    "AgentExecutor",
    "AgentProfile",
    "AgentRegistry",
    "UnconfiguredExecutor",
    "build_default_registry",
    "clone_card",
]
