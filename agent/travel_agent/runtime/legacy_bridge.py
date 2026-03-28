"""Bridge legacy graph-builder entrypoints into the application-facing runtime."""

from __future__ import annotations

from typing import Any, AsyncGenerator, Protocol

from ..contracts import (
    SupervisorPlanPreview,
    SupervisorPlanPreviewRequest,
    SupervisorRunRequest,
    SupervisorRuntimeContext,
)

TOOL_RESULT_PREVIEW_LIMIT = 200


class LegacyRuntimeBridge(Protocol):
    """Describe the compatibility surface that still delegates to the legacy graph."""

    async def stream_with_memory(
        self,
        *,
        request: SupervisorRunRequest,
        context: SupervisorRuntimeContext,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield normalized runtime events backed by the legacy graph implementation."""

    def generate_plan_preview_with_memory(
        self,
        *,
        request: SupervisorPlanPreviewRequest,
        context: SupervisorRuntimeContext,
    ) -> SupervisorPlanPreview:
        """Return one memory-aware plan preview from the legacy graph path."""

    def get_tool_health_diagnostics(self) -> dict[str, Any]:
        """Return legacy graph tool-health diagnostics."""


class DefaultLegacyRuntimeBridge:
    """Lazy compatibility adapter around the existing graph.builder entrypoints."""

    async def stream_with_memory(
        self,
        *,
        request: SupervisorRunRequest,
        context: SupervisorRuntimeContext,
    ) -> AsyncGenerator[dict[str, Any], None]:
        """Yield runtime events from the legacy memory-aware streaming entrypoint."""
        from ..graph.legacy_runtime import stream_supervisor_run

        async for event in stream_supervisor_run(request=request, context=context):
            yield event

    def generate_plan_preview_with_memory(
        self,
        *,
        request: SupervisorPlanPreviewRequest,
        context: SupervisorRuntimeContext,
    ) -> SupervisorPlanPreview:
        """Return legacy graph plan preview data without exposing builder imports upstream."""
        from ..graph.legacy_runtime import generate_supervisor_plan_preview

        return generate_supervisor_plan_preview(request=request, context=context)

    def get_tool_health_diagnostics(self) -> dict[str, Any]:
        """Return tool-health diagnostics from the legacy graph compatibility path."""
        from ..graph.legacy_runtime import get_tool_health_diagnostics

        return get_tool_health_diagnostics()
