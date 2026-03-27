"""Application-facing runtime wrapper for the phase-1 supervisor architecture."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Optional

from langchain_core.runnables import Runnable
from langchain_core.tools import Tool

from ..artifacts import (
    build_trip_plan_artifact_from_plan_preview,
    build_trip_plan_artifact_from_stream_event,
)
from ..graph.builder import (
    generate_plan_preview_with_memory,
    get_tool_health_diagnostics,
    run_travel_agent_streaming_with_memory,
)
from ..graph.state import TRAVEL_AGENT_SYSTEM_PROMPT
from ..skills import SkillRegistry, build_default_skill_registry
from ..subagents import SubagentRegistry, build_default_subagent_registry
from ..supervisor import SupervisorTravelAgentGraph, build_supervisor_agent


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
        tracker = _SubagentTracker(
            registry=self.subagent_registry,
            session_id=session_id,
            run_id=run_id,
            chat_mode=chat_mode,
        )
        async for event in run_travel_agent_streaming_with_memory(
            user_message=user_message,
            llm=self.llm,
            tools=self.tools,
            session_id=session_id,
            memory_manager=self.memory_manager,
            system_prompt=self.system_prompt,
            persist_memory=persist_memory,
            run_id=run_id,
            chat_mode=chat_mode,
            routing_llm=self.routing_llm,
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

            if event.get("type") == "tool_start":
                tool_name = _coerce_optional_str(event.get("tool")) or ""
                next_subagent = self.subagent_registry.resolve_subagent_for_tool(tool_name)
                for transition_event in tracker.transition(next_subagent, trigger="tool"):
                    yield transition_event
                if next_subagent:
                    event = dict(event)
                    event["subagent"] = next_subagent

            if event.get("type") == "tool_end":
                tool_name = _coerce_optional_str(event.get("tool")) or ""
                subagent_name = self.subagent_registry.resolve_subagent_for_tool(tool_name)
                if subagent_name:
                    event = dict(event)
                    event["subagent"] = subagent_name

            if event.get("type") == "done":
                enriched_event = dict(event)
                artifact = build_trip_plan_artifact_from_stream_event(
                    enriched_event,
                    user_message=user_message,
                    session_id=session_id,
                    chat_mode=chat_mode,
                )
                subagent_patches = self.subagent_registry.done_artifact_patches(
                    enriched_event,
                    user_message=user_message,
                    session_id=session_id,
                    chat_mode=chat_mode,
                )
                merged_artifact = _merge_artifact_patches(artifact, subagent_patches.values())
                enriched_event["artifact"] = merged_artifact
                for subagent_name, patch in subagent_patches.items():
                    yield {
                        "type": "artifact_patch",
                        "subagent": subagent_name,
                        "artifact_patch": patch,
                        "run_id": run_id,
                        "session_id": session_id,
                    }
                for transition_event in tracker.finish():
                    yield transition_event
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
        preview = generate_plan_preview_with_memory(
            user_message=user_message,
            llm=self.llm,
            tools=self.tools,
            session_id=session_id,
            memory_manager=self.memory_manager,
            system_prompt=self.system_prompt,
            chat_mode=chat_mode,
            routing_llm=self.routing_llm,
        )
        enriched_preview = dict(preview)
        artifact = build_trip_plan_artifact_from_plan_preview(
            enriched_preview,
            user_message=user_message,
            session_id=session_id,
        )
        preview_patch = self.subagent_registry.preview_artifact_patch(enriched_preview)
        enriched_preview["artifact"] = _merge_artifact_patches(artifact, [preview_patch])
        enriched_preview["subagent"] = "planning"
        enriched_preview["skills"] = self.subagent_registry.skill_names("planning")
        enriched_preview["artifact_patch"] = preview_patch
        return enriched_preview

    def get_tool_health_diagnostics(self) -> dict[str, Any]:
        """Return tool diagnostics plus phase-1 skill and subagent metadata."""
        diagnostics = dict(get_tool_health_diagnostics())
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

    def transition(self, next_subagent: Optional[str], *, trigger: str) -> list[dict[str, Any]]:
        """Emit start/end events when the active subagent changes."""
        if next_subagent == self.active:
            return []

        events: list[dict[str, Any]] = []
        if self.active:
            active_subagent = self.registry.get(self.active)
            if active_subagent is not None:
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
