"""Application-facing runtime wrapper for the phase-1 supervisor architecture."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Optional

from langchain_core.runnables import Runnable
from langchain_core.tools import Tool

from ..artifacts import (
    build_trip_plan_artifact_from_plan_preview,
    build_trip_plan_artifact_from_stream_event,
)
from ..contracts import (
    ExecutionReceipt,
    ExecutionReceiptStage,
    SubagentExecutionReceipt,
    SupervisorPlanPreview,
    SupervisorPlanPreviewRequest,
    SupervisorRunRequest,
    SupervisorRuntimeContext,
)
from ..graph.state import TRAVEL_AGENT_SYSTEM_PROMPT
from ..skills import SkillRegistry, build_default_skill_registry
from ..subagents import SubagentRegistry, build_default_subagent_registry
from ..supervisor import SupervisorTravelAgentGraph, build_supervisor_agent
from .legacy_bridge import DefaultLegacyRuntimeBridge, LegacyRuntimeBridge


class AgentRuntime:
    """Compatibility runtime that introduces skills, subagents, and artifact-first payloads."""

    def __init__(
        self,
        llm: Runnable,
        tools: list[Tool],
        *,
        system_prompt: str = TRAVEL_AGENT_SYSTEM_PROMPT,
        memory_manager: Any = None,
        routing_llm: Optional[Runnable] = None,
        skill_registry: Optional[SkillRegistry] = None,
        legacy_bridge: Optional[LegacyRuntimeBridge] = None,
    ):
        """Initialize the application-facing runtime wrapper."""
        self.llm = llm
        self.tools = tools
        self.system_prompt = system_prompt
        self.memory_manager = memory_manager
        self.routing_llm = routing_llm
        self.skill_registry = skill_registry or build_default_skill_registry(tools)
        self.subagent_registry = build_default_subagent_registry(self.skill_registry)
        self.subagents = self.subagent_registry.names()
        self.legacy_bridge = legacy_bridge or DefaultLegacyRuntimeBridge()

    def build_supervisor_graph(self, checkpointer: Any = None) -> SupervisorTravelAgentGraph:
        """Build the phase-1 supervisor graph wrapper."""
        return build_supervisor_agent(
            llm=self.llm,
            tools=self.tools,
            system_prompt=self.system_prompt,
            routing_llm=self.routing_llm,
            checkpointer=checkpointer,
            skill_registry=self.skill_registry,
        )

    async def stream_with_memory(
        self,
        *,
        user_message: str,
        session_id: str = "default",
        persist_memory: bool = True,
        run_id: Optional[str] = None,
        chat_mode: Optional[str] = None,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Stream normalized events and attach subagent and artifact payloads."""
        request = self._build_stream_request(
            user_message=user_message,
            session_id=session_id,
            persist_memory=persist_memory,
            run_id=run_id,
            chat_mode=chat_mode,
        )
        tracker = _SubagentTracker(
            registry=self.subagent_registry,
            session_id=request.session_id,
            run_id=request.run_id,
            chat_mode=request.chat_mode,
        )
        async for event in self.legacy_bridge.stream_with_memory(
            request=request,
            context=self._build_runtime_context(),
        ):
            if event.get("type") == "stage":
                explicit_subagent = _coerce_optional_str(event.get("subagent"))
                next_subagent = self.subagent_registry.resolve_subagent_for_stage(
                    stage=_coerce_optional_str(event.get("stage")),
                    label=_coerce_optional_str(event.get("label")),
                    explicit_subagent=explicit_subagent,
                )
                for transition_event in tracker.transition(next_subagent, trigger="stage"):
                    yield transition_event
                if next_subagent:
                    event = dict(event)
                    event["subagent"] = next_subagent
                tracker.note_stage(
                    stage=_coerce_optional_str(event.get("stage")),
                    label=_coerce_optional_str(event.get("label")),
                    subagent=_coerce_optional_str(event.get("subagent")),
                )

            if event.get("type") == "tool_start":
                tool_name = _coerce_optional_str(event.get("tool")) or ""
                next_subagent = self.subagent_registry.resolve_subagent_for_tool(tool_name)
                for transition_event in tracker.transition(next_subagent, trigger="tool"):
                    yield transition_event
                if next_subagent:
                    event = dict(event)
                    event["subagent"] = next_subagent
                tracker.note_tool(tool_name, subagent=_coerce_optional_str(event.get("subagent")))

            if event.get("type") == "tool_end":
                tool_name = _coerce_optional_str(event.get("tool")) or ""
                subagent_name = self.subagent_registry.resolve_subagent_for_tool(tool_name)
                if subagent_name:
                    event = dict(event)
                    event["subagent"] = subagent_name
                tracker.note_tool(tool_name, subagent=_coerce_optional_str(event.get("subagent")))

            if event.get("type") == "done":
                enriched_event = dict(event)
                artifact = build_trip_plan_artifact_from_stream_event(
                    enriched_event,
                    user_message=request.user_message,
                    session_id=request.session_id,
                    chat_mode=request.chat_mode,
                )
                subagent_patches = self.subagent_registry.done_artifact_patches(
                    enriched_event,
                    user_message=request.user_message,
                    session_id=request.session_id,
                    chat_mode=request.chat_mode,
                )
                merged_artifact = _merge_artifact_patches(artifact, subagent_patches.values())
                enriched_event["artifact"] = merged_artifact
                for subagent_name, patch in subagent_patches.items():
                    tracker.note_artifact_patch(subagent_name, patch)
                    yield {
                        "type": "artifact_patch",
                        "subagent": subagent_name,
                        "artifact_patch": patch,
                        "run_id": request.run_id,
                        "session_id": request.session_id,
                    }
                for transition_event in tracker.finish():
                    yield transition_event
                enriched_event["execution_receipt"] = tracker.build_execution_receipt()
                yield enriched_event
                continue
            yield event

    def generate_plan_preview_with_memory(
        self,
        *,
        user_message: str,
        session_id: str = "default",
        chat_mode: Optional[str] = None,
    ) -> dict[str, Any]:
        """Generate a memory-aware plan preview and attach a preview artifact."""
        request = self._build_plan_preview_request(
            user_message=user_message,
            session_id=session_id,
            chat_mode=chat_mode,
        )
        preview = self.legacy_bridge.generate_plan_preview_with_memory(
            request=request,
            context=self._build_runtime_context(),
        )
        enriched_preview = _coerce_plan_preview_dict(preview)
        artifact = build_trip_plan_artifact_from_plan_preview(
            enriched_preview,
            user_message=request.user_message,
            session_id=request.session_id,
        )
        preview_patch = self.subagent_registry.preview_artifact_patch(enriched_preview)
        enriched_preview["artifact"] = _merge_artifact_patches(artifact, [preview_patch])
        enriched_preview["subagent"] = "planning"
        enriched_preview["skills"] = self.subagent_registry.skill_names("planning")
        enriched_preview["artifact_patch"] = preview_patch
        return enriched_preview

    def get_tool_health_diagnostics(self) -> dict[str, Any]:
        """Return tool diagnostics plus phase-1 skill and subagent metadata."""
        diagnostics = dict(self.legacy_bridge.get_tool_health_diagnostics())
        diagnostics["skills"] = self.skill_registry.to_dict()
        diagnostics["subagents"] = list(self.subagents)
        diagnostics["subagent_skills"] = {
            name: self.subagent_registry.skill_names(name) for name in self.subagents
        }
        diagnostics["subagent_skill_policies"] = {
            name: self.subagent_registry.selection_policy(name) for name in self.subagents
        }
        diagnostics["architecture_phase"] = "phase2-supervisor-subagents"
        return diagnostics

    def _build_runtime_context(self) -> SupervisorRuntimeContext:
        """Build the shared runtime context passed to the compatibility bridge."""
        return SupervisorRuntimeContext(
            llm=self.llm,
            tools=self.tools,
            memory_manager=self.memory_manager,
            routing_llm=self.routing_llm,
        )

    def _build_stream_request(
        self,
        *,
        user_message: str,
        session_id: str,
        persist_memory: bool,
        run_id: Optional[str],
        chat_mode: Optional[str],
    ) -> SupervisorRunRequest:
        """Build the explicit supervisor-run request used by the runtime seam."""
        return SupervisorRunRequest(
            user_message=user_message,
            session_id=session_id,
            system_prompt=self.system_prompt,
            persist_memory=persist_memory,
            run_id=run_id,
            chat_mode=chat_mode,
        )

    def _build_plan_preview_request(
        self,
        *,
        user_message: str,
        session_id: str,
        chat_mode: Optional[str],
    ) -> SupervisorPlanPreviewRequest:
        """Build the explicit plan-preview request used by the runtime seam."""
        return SupervisorPlanPreviewRequest(
            user_message=user_message,
            session_id=session_id,
            system_prompt=self.system_prompt,
            chat_mode=chat_mode,
        )


class _SubagentTracker:
    """Track active subagent transitions while preserving backward compatibility."""

    def __init__(
        self,
        *,
        registry: SubagentRegistry,
        session_id: str,
        run_id: Optional[str],
        chat_mode: Optional[str],
    ):
        """Initialize state used to emit subagent transition events."""
        self.registry = registry
        self.session_id = session_id
        self.run_id = run_id
        self.chat_mode = chat_mode
        self.active: Optional[str] = None
        self.sequence = 0
        self.segments: list[SubagentExecutionReceipt] = []
        self._active_segment: Optional[SubagentExecutionReceipt] = None

    def transition(self, next_subagent: Optional[str], *, trigger: str) -> list[dict[str, Any]]:
        """Emit start/end events when the active subagent changes."""
        if next_subagent == self.active:
            return []

        events: list[dict[str, Any]] = []
        if self.active:
            active_subagent = self.registry.get(self.active)
            if active_subagent is not None:
                self._finalize_active_segment(
                    status="completed",
                    summary=f"{self.active} segment completed",
                )
                events.append(
                    active_subagent.end_event(
                        session_id=self.session_id,
                        run_id=self.run_id,
                        sequence=self.sequence,
                        status="completed",
                        summary=f"{self.active} segment completed",
                    )
                )

        self.active = next_subagent
        if next_subagent:
            next_subagent_model = self.registry.get(next_subagent)
            if next_subagent_model is not None:
                self.sequence += 1
                self._active_segment = SubagentExecutionReceipt(
                    subagent=next_subagent,
                    sequence=self.sequence,
                    trigger=trigger,
                    description=next_subagent_model.description,
                    skills=next_subagent_model.skill_names(),
                    tool_names=next_subagent_model.tool_names(),
                )
                self.segments.append(self._active_segment)
                events.append(
                    next_subagent_model.start_event(
                        session_id=self.session_id,
                        run_id=self.run_id,
                        sequence=self.sequence,
                        trigger=trigger,
                        chat_mode=self.chat_mode,
                    )
                )
        return events

    def finish(self) -> list[dict[str, Any]]:
        """Emit the terminal end event for any active subagent."""
        return self.transition(None, trigger="finish")

    def note_stage(
        self,
        *,
        stage: Optional[str],
        label: Optional[str],
        subagent: Optional[str],
    ) -> None:
        """Attach one routed stage observation to the most relevant segment."""
        segment = self._segment_for(subagent or self.active)
        if segment is None:
            return
        observation = ExecutionReceiptStage(stage=stage, label=label)
        if any(
            existing.stage == observation.stage and existing.label == observation.label
            for existing in segment.stages
        ):
            return
        segment.stages.append(observation)

    def note_tool(self, tool_name: str, *, subagent: Optional[str]) -> None:
        """Attach one tool usage breadcrumb to the most relevant segment."""
        normalized = _coerce_optional_str(tool_name)
        if not normalized:
            return
        segment = self._segment_for(subagent or self.active)
        if segment is None:
            return
        if normalized not in segment.tools_used:
            segment.tools_used.append(normalized)

    def note_artifact_patch(self, subagent: str, patch: dict[str, Any]) -> None:
        """Attach artifact patch coverage to the latest segment for one subagent."""
        segment = self._segment_for(subagent)
        if segment is None or not isinstance(patch, dict):
            return
        for section in patch:
            normalized = _coerce_optional_str(section)
            if normalized and normalized not in segment.artifact_patch_sections:
                segment.artifact_patch_sections.append(normalized)

    def build_execution_receipt(self) -> dict[str, Any]:
        """Build the execution receipt payload for the completed runtime run."""
        receipt = ExecutionReceipt(
            session_id=self.session_id,
            run_id=self.run_id,
            chat_mode=self.chat_mode,
            subagent_order=[segment.subagent for segment in self.segments],
            tools_used=_dedupe_preserve_order(
                tool_name for segment in self.segments for tool_name in segment.tools_used
            ),
            artifact_patch_subagents=_dedupe_preserve_order(
                segment.subagent for segment in self.segments if segment.artifact_patch_sections
            ),
            segments=self.segments,
        )
        return receipt.to_dict()

    def _finalize_active_segment(self, *, status: str, summary: str) -> None:
        """Finalize the active mutable segment before it is closed."""
        if self._active_segment is None:
            return
        self._active_segment.status = status
        self._active_segment.summary = summary
        self._active_segment = None

    def _segment_for(self, subagent: Optional[str]) -> Optional[SubagentExecutionReceipt]:
        """Return the newest segment associated with one subagent name."""
        normalized = _coerce_optional_str(subagent)
        if not normalized:
            return self._active_segment
        for segment in reversed(self.segments):
            if segment.subagent == normalized:
                return segment
        return None


def _merge_artifact_patches(
    base_artifact: dict[str, Any],
    patches: Any,
) -> dict[str, Any]:
    """Recursively merge subagent artifact patches into the base artifact."""
    merged = dict(base_artifact)
    for patch in patches:
        if isinstance(patch, dict):
            _deep_merge_inplace(merged, patch)
    return merged


def _deep_merge_inplace(target: dict[str, Any], patch: dict[str, Any]) -> None:
    """Recursively merge one patch dictionary into the target artifact."""
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(target.get(key), dict):
            _deep_merge_inplace(target[key], value)
            continue
        target[key] = value


def _coerce_optional_str(value: Any) -> Optional[str]:
    """Return a normalized optional string value."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _dedupe_preserve_order(values: Any) -> list[str]:
    """Return one de-duplicated string list while preserving the first-seen order."""
    deduped: list[str] = []
    for value in values:
        normalized = _coerce_optional_str(value)
        if normalized and normalized not in deduped:
            deduped.append(normalized)
    return deduped


def _coerce_plan_preview_dict(preview: Any) -> dict[str, Any]:
    """Return a dictionary view for either the preview contract or a compatibility dict."""
    if isinstance(preview, SupervisorPlanPreview):
        return preview.to_dict()
    return dict(preview) if isinstance(preview, dict) else {}
