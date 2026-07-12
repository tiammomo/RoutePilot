"""Artifact-first Travel Orchestrator using reliable local A2A Tasks."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import timedelta
import json
from typing import Any
from uuid import UUID, uuid5

from a2a.types import SendMessageRequest, TaskState
from a2a.utils.errors import InvalidParamsError
from google.protobuf.json_format import MessageToDict, ParseDict

from agent.travel_agent.a2a.constants import (
    INPUT_RESPONSE_SCHEMA_URI,
    TRAVEL_ARTIFACT_EXTENSION_URI,
    invocation_schema_uri,
)
from agent.travel_agent.a2a.models import (
    A2AActor,
    ArtifactInput,
    ContractName,
    InputResponse,
    TypedInputRequest,
)
from agent.travel_agent.a2a.service import TaskService
from routepilot_contracts.artifacts import (
    CandidateSet,
    ConstraintReport,
    EvidenceBundle,
    ItineraryPlan,
    SemanticRiskReport,
    TripBrief,
    TripSnapshot,
    ValidationReport,
)
from routepilot_contracts.common import ArtifactType
from routepilot_contracts.validation import validate_contract

from .shared import artifact_ref, new_id, system_actor, utc_now
from .validation import ValidationPolicyService


Progress = Callable[[str, str, int], Awaitable[None]]
_LOCAL_DISPATCH_NAMESPACE = UUID("9dba4a09-d63a-5f90-a69d-147a84ac1751")


class AgentTaskFailed(RuntimeError):
    """Safe orchestration failure; never includes private Task messages."""

    def __init__(self, interface_id: str, state: str):
        super().__init__(f"{interface_id} task ended in {state}")
        self.interface_id = interface_id
        self.state = state


class AgentInputRequired(RuntimeError):
    """A typed A2A interruption that can safely cross the Product Run boundary."""

    def __init__(
        self,
        interface_id: str,
        task_id: str,
        request: TypedInputRequest,
    ) -> None:
        super().__init__(f"{interface_id} task requires typed input")
        self.interface_id = interface_id
        self.task_id = task_id
        self.request = request


@dataclass(frozen=True, slots=True)
class AgentArtifact:
    contract: ContractName
    payload: dict[str, Any]
    artifact_id: str


@dataclass(frozen=True, slots=True)
class AgentTaskResult:
    interface_id: str
    task_id: str
    context_id: str
    artifacts: tuple[AgentArtifact, ...]


class LocalA2AAgentMesh:
    """Use the same A2A TaskService as HTTP without bypassing Task lifecycle."""

    def __init__(self, service: TaskService, *, timeout_seconds: int = 1_800):
        self.service = service
        self.timeout_seconds = max(5, min(timeout_seconds, 1_800))

    @staticmethod
    def deterministic_dispatch_id(
        tenant_id: str,
        run_id: str,
        interface_id: str,
        dispatch_key: str,
    ) -> str:
        """Derive a stable UUID so a reclaimed Product Run resumes the same Task."""

        scope = f"routepilot-v1\x1f{tenant_id}\x1f{run_id}\x1f{interface_id}\x1f{dispatch_key}"
        return str(uuid5(_LOCAL_DISPATCH_NAMESPACE, scope))

    async def dispatch(
        self,
        actor: A2AActor,
        *,
        interface_id: str,
        run_id: str,
        goal: str,
        artifacts: list[ArtifactInput],
        options: dict[str, Any] | None = None,
        dispatch_key: str | None = None,
        input_response: InputResponse | None = None,
    ) -> AgentTaskResult:
        stage_key = (dispatch_key or interface_id).strip()
        if not stage_key or len(stage_key) > 96:
            raise ValueError("dispatch_key must contain between 1 and 96 characters")
        dispatch_id = self.deterministic_dispatch_id(
            actor.tenant_id,
            run_id,
            interface_id,
            stage_key,
        )
        task = await self.service.recover_dispatch(
            actor,
            interface_id,
            run_id=run_id,
            dispatch_id=dispatch_id,
        )
        if task is not None:
            if task.status.state == TaskState.TASK_STATE_INPUT_REQUIRED and input_response:
                task = await self._resume_task(
                    actor,
                    interface_id=interface_id,
                    run_id=run_id,
                    dispatch_id=dispatch_id,
                    task=task,
                    response=input_response,
                )
            return self._task_result(interface_id, task)
        deadline = utc_now() + timedelta(seconds=self.timeout_seconds)
        payload = {
            "tenant": actor.tenant_id,
            "message": {
                "messageId": dispatch_id,
                "role": "ROLE_USER",
                "parts": [
                    {
                        "data": {
                            "goal": goal,
                            "artifacts": [item.model_dump(mode="json") for item in artifacts],
                            "options": options or {},
                        },
                        "metadata": {
                            "schema_uri": invocation_schema_uri(interface_id),
                            "schema_version": 1,
                        },
                    }
                ],
                "metadata": {
                    TRAVEL_ARTIFACT_EXTENSION_URI: {
                        "dispatch_id": dispatch_id,
                        "run_id": run_id,
                        "deadline": deadline.isoformat(),
                    }
                },
                "extensions": [TRAVEL_ARTIFACT_EXTENSION_URI],
            },
            "configuration": {
                "acceptedOutputModes": ["application/json"],
                "returnImmediately": False,
            },
        }
        params = ParseDict(payload, SendMessageRequest())
        try:
            task = await self.service.send_message(
                actor,
                interface_id,
                params,
                requested_extensions={TRAVEL_ARTIFACT_EXTENSION_URI},
            )
        except InvalidParamsError:
            # Another process may have atomically won the same deterministic
            # dispatch with an equivalent persisted invocation. Recover that
            # snapshot; unrelated validation failures still propagate.
            task = await self.service.recover_dispatch(
                actor,
                interface_id,
                run_id=run_id,
                dispatch_id=dispatch_id,
            )
            if task is None:
                raise
        return self._task_result(interface_id, task)

    async def _resume_task(
        self,
        actor: A2AActor,
        *,
        interface_id: str,
        run_id: str,
        dispatch_id: str,
        task: Any,
        response: InputResponse,
    ) -> Any:
        response_key = json.dumps(
            response.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        message_id = str(
            uuid5(
                _LOCAL_DISPATCH_NAMESPACE,
                f"routepilot-v1-resume\x1f{task.id}\x1f{response_key}",
            )
        )
        payload = {
            "tenant": actor.tenant_id,
            "message": {
                "messageId": message_id,
                "taskId": task.id,
                "contextId": task.context_id,
                "role": "ROLE_USER",
                "parts": [
                    {
                        "data": response.model_dump(mode="json"),
                        "metadata": {
                            "schema_uri": INPUT_RESPONSE_SCHEMA_URI,
                            "schema_version": 1,
                        },
                    }
                ],
                "metadata": {
                    TRAVEL_ARTIFACT_EXTENSION_URI: {
                        "dispatch_id": dispatch_id,
                        "run_id": run_id,
                    }
                },
                "extensions": [TRAVEL_ARTIFACT_EXTENSION_URI],
            },
            "configuration": {
                "acceptedOutputModes": ["application/json"],
                "returnImmediately": False,
            },
        }
        return await self.service.send_message(
            actor,
            interface_id,
            ParseDict(payload, SendMessageRequest()),
            requested_extensions={TRAVEL_ARTIFACT_EXTENSION_URI},
        )

    @staticmethod
    def _task_result(interface_id: str, task: Any) -> AgentTaskResult:
        if task.status.state == TaskState.TASK_STATE_INPUT_REQUIRED:
            try:
                if len(task.status.message.parts) != 1:
                    raise ValueError
                part = task.status.message.parts[0]
                if part.WhichOneof("content") != "data":
                    raise ValueError
                request = TypedInputRequest.model_validate(
                    MessageToDict(part.data, preserving_proto_field_name=False)
                )
            except (ValueError, TypeError):
                raise AgentTaskFailed(interface_id, "INVALID_INPUT_REQUEST") from None
            raise AgentInputRequired(interface_id, task.id, request)
        if task.status.state != TaskState.TASK_STATE_COMPLETED:
            raise AgentTaskFailed(interface_id, TaskState.Name(task.status.state))

        outputs: list[AgentArtifact] = []
        for artifact in task.artifacts:
            metadata = MessageToDict(artifact.metadata, preserving_proto_field_name=False)
            extension = metadata.get(TRAVEL_ARTIFACT_EXTENSION_URI)
            contract = extension.get("contract") if isinstance(extension, dict) else None
            if not isinstance(contract, str) or len(artifact.parts) != 1:
                raise AgentTaskFailed(interface_id, "INVALID_ARTIFACT")
            part = artifact.parts[0]
            if part.WhichOneof("content") != "data":
                raise AgentTaskFailed(interface_id, "INVALID_ARTIFACT")
            body = MessageToDict(part.data, preserving_proto_field_name=False)
            if not isinstance(body, dict):
                raise AgentTaskFailed(interface_id, "INVALID_ARTIFACT")
            validated = validate_contract(contract, body)
            outputs.append(
                AgentArtifact(
                    contract=contract,  # type: ignore[arg-type]
                    payload=validated.model_dump(mode="json"),
                    artifact_id=artifact.artifact_id,
                )
            )
        return AgentTaskResult(
            interface_id=interface_id,
            task_id=task.id,
            context_id=task.context_id,
            artifacts=tuple(outputs),
        )


def _artifact_input(contract: ContractName, artifact: Any) -> ArtifactInput:
    return ArtifactInput(contract=contract, payload=artifact.model_dump(mode="json"))


def _result(result: AgentTaskResult, contract: str, expected: type[Any]) -> Any:
    matches = [item for item in result.artifacts if item.contract == contract]
    if len(matches) != 1:
        raise AgentTaskFailed(result.interface_id, f"MISSING_{contract}")
    parsed = validate_contract(contract, matches[0].payload)
    if not isinstance(parsed, expected):
        raise AgentTaskFailed(result.interface_id, "INCOMPATIBLE_ARTIFACT")
    return parsed


@dataclass(frozen=True, slots=True)
class OrchestrationResult:
    """Complete validated Artifact graph with one final TripSnapshot."""

    brief: TripBrief
    evidence: EvidenceBundle
    candidates: CandidateSet
    plan: ItineraryPlan
    constraints: ConstraintReport
    semantics: SemanticRiskReport
    validation: ValidationReport
    snapshot: TripSnapshot
    task_refs: tuple[AgentTaskResult, ...]


class TravelOrchestratorV2:
    """Fan through professional A2A Agents and apply local publication policy."""

    def __init__(
        self,
        mesh: LocalA2AAgentMesh,
        *,
        policy: ValidationPolicyService | None = None,
    ) -> None:
        self.mesh = mesh
        self.policy = policy or ValidationPolicyService()

    async def execute(
        self,
        *,
        tenant_id: str,
        actor_id: str,
        run_id: str,
        trip_id: str,
        title: str,
        brief: TripBrief,
        goal: str,
        progress: Progress,
        base_snapshot: TripSnapshot | None = None,
        base_plan: ItineraryPlan | None = None,
        input_response: InputResponse | None = None,
    ) -> OrchestrationResult:
        actor = A2AActor(
            tenant_id=tenant_id,
            actor_id=actor_id,
            roles=frozenset({"owner"}),
        )
        await progress("research", "正在检索并核对旅行证据", 20)
        base_inputs = []
        if base_snapshot is not None:
            base_inputs.append(_artifact_input("TripSnapshot@1", base_snapshot))
        if base_plan is not None:
            base_inputs.append(_artifact_input("ItineraryPlan@1", base_plan))
        research = await self.mesh.dispatch(
            actor,
            interface_id="research",
            run_id=run_id,
            goal=goal,
            artifacts=[_artifact_input("TripBrief@1", brief), *base_inputs],
            dispatch_key="research",
            input_response=input_response,
        )
        evidence = _result(research, "EvidenceBundle@1", EvidenceBundle)
        candidates = _result(research, "CandidateSet@1", CandidateSet)

        await progress("planning", "正在生成结构化候选行程", 45)
        planning = await self.mesh.dispatch(
            actor,
            interface_id="planner",
            run_id=run_id,
            goal=goal,
            artifacts=[
                _artifact_input("TripBrief@1", brief),
                _artifact_input("EvidenceBundle@1", evidence),
                _artifact_input("CandidateSet@1", candidates),
                *base_inputs,
            ],
            dispatch_key="planning",
            input_response=input_response,
        )
        plan = _result(planning, "ItineraryPlan@1", ItineraryPlan)

        await progress("validation", "正在执行时间、路线和预算硬约束校验", 65)
        validation_task = await self.mesh.dispatch(
            actor,
            interface_id="validation",
            run_id=run_id,
            goal="独立校验候选行程，不修改方案",
            artifacts=[
                _artifact_input("TripBrief@1", brief),
                _artifact_input("ItineraryPlan@1", plan),
                _artifact_input("EvidenceBundle@1", evidence),
            ],
            dispatch_key="constraint-validation",
            input_response=input_response,
        )
        constraints = _result(validation_task, "ConstraintReport@1", ConstraintReport)

        await progress("validation", "正在独立审查证据覆盖和语义风险", 80)
        semantic_task = await self.mesh.dispatch(
            actor,
            interface_id="semantic-verifier",
            run_id=run_id,
            goal="审查证据覆盖、来源冲突、假设与软风险，不修改方案",
            artifacts=[
                _artifact_input("TripBrief@1", brief),
                _artifact_input("ItineraryPlan@1", plan),
                _artifact_input("EvidenceBundle@1", evidence),
                _artifact_input("ConstraintReport@1", constraints),
            ],
            dispatch_key="semantic-validation",
            input_response=input_response,
        )
        semantics = _result(semantic_task, "SemanticRiskReport@1", SemanticRiskReport)
        validation = self.policy.combine(plan, constraints, semantics)
        validated_plan = plan.model_copy(
            update={
                "status": "validated" if validation.publishable else "candidate",
                "validation_ref": artifact_ref(validation, ArtifactType.VALIDATION_REPORT),
            }
        )
        snapshot = TripSnapshot(
            artifact_id=new_id("artifact"),
            artifact_type="TripSnapshot",
            schema_version=1,
            version=1,
            created_at=utc_now(),
            created_by=system_actor("travel-orchestrator"),
            reason="汇总专业 Agent 结果并通过版本化发布门禁。",
            trip_id=trip_id,
            title=title[:256],
            status="ready" if validation.publishable else "planning",
            timezone=brief.destination.timezone,
            brief=brief,
            itinerary=validated_plan,
            validation=validation,
            generated_at=utc_now(),
            source_artifact_versions=[
                artifact_ref(brief, ArtifactType.TRIP_BRIEF),
                artifact_ref(validated_plan, ArtifactType.ITINERARY_PLAN),
                artifact_ref(validation, ArtifactType.VALIDATION_REPORT),
                artifact_ref(evidence, ArtifactType.EVIDENCE_BUNDLE),
                artifact_ref(candidates, ArtifactType.CANDIDATE_SET),
                artifact_ref(constraints, ArtifactType.CONSTRAINT_REPORT),
                artifact_ref(semantics, ArtifactType.SEMANTIC_RISK_REPORT),
            ],
        )
        await progress("publishing", "正在保存可恢复的旅行快照", 95)
        return OrchestrationResult(
            brief=brief,
            evidence=evidence,
            candidates=candidates,
            plan=validated_plan,
            constraints=constraints,
            semantics=semantics,
            validation=validation,
            snapshot=snapshot,
            task_refs=(research, planning, validation_task, semantic_task),
        )


__all__ = [
    "AgentArtifact",
    "AgentInputRequired",
    "AgentTaskFailed",
    "AgentTaskResult",
    "LocalA2AAgentMesh",
    "OrchestrationResult",
    "TravelOrchestratorV2",
]
