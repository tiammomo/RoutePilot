"""Plan preview collaboration helpers for streamed chat mode."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional, Protocol

from .shared import merge_artifact_payload


class _PlanPreviewState(Protocol):
    """Minimal state contract required to enrich streamed plan previews."""

    reasoning_content: str
    final_artifact: dict[str, Any]
    subagent_events: list[dict[str, Any]]


class ChatPlanPreviewCoordinator:
    """Generate, normalize, and apply plan preview state updates."""

    def __init__(
        self,
        *,
        generate_plan_preview: Callable[[str, str], dict[str, Any]],
        get_timestamp: Callable[[], str],
        logger: logging.Logger,
    ) -> None:
        self._generate_plan_preview = generate_plan_preview
        self._get_timestamp = get_timestamp
        self._logger = logger

    async def normalize(
        self,
        state: _PlanPreviewState,
        *,
        session_id: str,
        message: str,
    ) -> list[dict[str, Any]]:
        """Normalize plan-preview output into streamed payloads and state updates."""
        payloads = self._build_intro_payloads(state)
        plan_preview = await self._load_plan_preview(session_id, message)
        if not plan_preview:
            return payloads

        self._merge_preview_artifacts(state, plan_preview)
        payloads.extend(self._build_subagent_start_payloads(state, plan_preview))
        payloads.append(self._build_preview_payload(plan_preview))
        payloads.extend(self._build_subagent_completion_payloads(state, plan_preview))

        summary_payload = self._build_summary_payload(state, plan_preview)
        if summary_payload is not None:
            payloads.append(summary_payload)

        return payloads

    def _build_intro_payloads(self, state: _PlanPreviewState) -> list[dict[str, Any]]:
        """Emit the initial reasoning hint shown before preview generation completes."""
        intro = "开始制定旅行计划..."
        state.reasoning_content += intro
        return [{"type": "reasoning_chunk", "content": intro}]

    async def _load_plan_preview(self, session_id: str, message: str) -> Optional[dict[str, Any]]:
        """Run plan preview generation on a worker thread and soften failures."""
        try:
            return await asyncio.to_thread(self._generate_plan_preview, session_id, message)
        except Exception as exc:
            self._logger.warning("Plan preview failed, continue react flow: %s", exc)
            return None

    def _merge_preview_artifacts(self, state: _PlanPreviewState, plan_preview: dict[str, Any]) -> None:
        """Merge preview artifact fragments into the accumulated final artifact."""
        state.final_artifact = merge_artifact_payload(state.final_artifact, plan_preview.get("artifact", {}))
        state.final_artifact = merge_artifact_payload(
            state.final_artifact,
            plan_preview.get("artifact_patch", {}),
        )

    def _build_subagent_start_payloads(
        self,
        state: _PlanPreviewState,
        plan_preview: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build optional subagent-start events for preview generation."""
        preview_subagent = plan_preview.get("subagent")
        if not preview_subagent:
            return []

        preview_skills = plan_preview.get("skills", [])
        state.subagent_events.append(
            {
                "subagent": preview_subagent,
                "skills": preview_skills,
                "trigger": "plan_preview",
                "timestamp": self._get_timestamp(),
            }
        )
        return [
            {
                "type": "subagent_start",
                "subagent": preview_subagent,
                "skills": preview_skills,
            }
        ]

    @staticmethod
    def _build_preview_payload(plan_preview: dict[str, Any]) -> dict[str, Any]:
        """Build the public plan preview payload consumed by the client."""
        return {
            "type": "plan_preview",
            "plan_id": plan_preview.get("plan_id"),
            "intent": plan_preview.get("intent"),
            "explanation": plan_preview.get("plan_explanation"),
            "validation_status": plan_preview.get("validation_status", "pass"),
            "validation_errors": plan_preview.get("validation_errors", []),
            "steps": plan_preview.get("plan", []),
            "artifact": plan_preview.get("artifact", {}),
        }

    def _build_subagent_completion_payloads(
        self,
        state: _PlanPreviewState,
        plan_preview: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Build optional artifact/subagent completion payloads for the preview phase."""
        preview_subagent = plan_preview.get("subagent")
        preview_artifact_patch = plan_preview.get("artifact_patch", {})
        if not preview_subagent or not preview_artifact_patch:
            return []

        state.subagent_events.append(
            {
                "subagent": preview_subagent,
                "status": "preview_ready",
                "summary": "Plan preview artifact prepared.",
                "timestamp": self._get_timestamp(),
            }
        )
        return [
            {
                "type": "artifact_patch",
                "subagent": preview_subagent,
                "artifact_patch": preview_artifact_patch,
            },
            {
                "type": "subagent_end",
                "subagent": preview_subagent,
                "status": "preview_ready",
            },
        ]

    @staticmethod
    def _build_summary_payload(
        state: _PlanPreviewState,
        plan_preview: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Build the reasoning summary shown after preview steps are available."""
        preview_steps = plan_preview.get("plan", [])
        if not preview_steps:
            return None

        preview_intent = plan_preview.get("intent")
        preview_summary = f"识别意图：{preview_intent}，将执行 {len(preview_steps)} 步。"
        state.reasoning_content += f" 识别意图：{preview_intent}，共 {len(preview_steps)} 步。"
        return {"type": "reasoning_chunk", "content": preview_summary}
