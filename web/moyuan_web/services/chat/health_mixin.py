"""Health and diagnostics helpers for chat orchestration."""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


class ChatHealthMixin:
    """Health, telemetry, and SLO snapshot helpers."""

    async def health_status(self) -> dict[str, Any]:
        """Return lightweight runtime readiness status used by health endpoints."""
        return {
            "initialized": self._initialized,
            "llm_adapter": self._llm_adapter is not None,
            "tools_count": len(self._tools) if self._tools else 0,
            "memory_enabled": self._memory_manager is not None,
            "runtime_layer": "agent-runtime" if self._agent_runtime is not None else "graph-direct",
            "skills_count": len(self._agent_runtime.skill_registry) if self._agent_runtime is not None else 0,
            "subagents_count": len(self._agent_runtime.subagents) if self._agent_runtime is not None else 0,
        }

    async def tools_health_status(self) -> dict[str, Any]:
        """Return detailed tool-health diagnostics with SLO counters and circuit states."""
        status = await self.health_status()
        diagnostics = self._agent_runtime.get_tool_health_diagnostics() if self._agent_runtime is not None else {}
        health_metrics = self._build_health_metrics_snapshot()
        return {
            "status": "ok" if status.get("initialized") else "not initialized",
            "initialized": status.get("initialized", False),
            "configured_tools_count": status.get("tools_count", 0),
            "circuit_open_count": diagnostics.get("open_circuit_count", 0),
            "slo": health_metrics.get("slo", {}),
            "intent_aggregate": health_metrics.get("intent_aggregate", {}),
            "window_minutes": self._health_window_minutes,
            "diagnostics": diagnostics,
        }

    async def tools_intents_health_status(self) -> dict[str, Any]:
        """Return intent-level aggregate health metrics for monitoring dashboards."""
        status = await self.health_status()
        health_metrics = self._build_health_metrics_snapshot()
        slo = health_metrics.get("slo", {})
        return {
            "status": "ok" if status.get("initialized") else "not initialized",
            "window_minutes": self._health_window_minutes,
            "total_requests": int(slo.get("total_requests", 0) or 0),
            "intent_aggregate": health_metrics.get("intent_aggregate", {}),
        }

    @staticmethod
    def _extract_failure_clusters(execution_stats: dict[str, Any]) -> dict[str, int]:
        """Extract clustered failure patterns from execution metadata for telemetry."""
        steps = list((execution_stats or {}).get("steps", []) or [])
        clusters = {"timeout": 0, "param_error": 0, "irrelevant_answer": 0, "tool_error": 0}
        for step in steps:
            code = str(step.get("error_code") or "")
            if code == "TOOL_TIMEOUT":
                clusters["timeout"] += 1
            elif code == "PARAM_VALIDATION_ERROR":
                clusters["param_error"] += 1
            elif code:
                clusters["tool_error"] += 1
        return clusters

    def _emit_failure_telemetry(
        self,
        session_id: str,
        run_id: str,
        mode: str,
        execution_stats: dict[str, Any],
        answer: str,
        hard_error: Optional[str] = None,
    ) -> None:
        """Emit summarized failure telemetry into service health metric buffers."""
        clusters = self._extract_failure_clusters(execution_stats)
        if not answer.strip():
            clusters["irrelevant_answer"] += 1
        payload = {
            "ts": datetime.now().isoformat(),
            "session_id": session_id,
            "run_id": run_id,
            "mode": mode,
            "clusters": clusters,
            "hard_error": hard_error,
        }
        if not any(value > 0 for value in clusters.values()) and not hard_error:
            return

        root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
        target = os.path.join(root, "data", "runtime_failure_clusters.jsonl")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        try:
            with open(target, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.warning("Failed to write failure telemetry: %s", exc)

    @staticmethod
    def _parse_int_env(name: str, default: int, minimum: int) -> int:
        """Parse integer environment variable with fallback and lower-bound protection."""
        raw = str(os.getenv(name, str(default))).strip()
        try:
            value = int(raw)
            if value < minimum:
                raise ValueError(f"{name} must be >= {minimum}")
            return value
        except Exception:
            return default

    @staticmethod
    def _parse_float_env(name: str, default: float) -> float:
        """Parse float environment variable with fallback protection."""
        raw = str(os.getenv(name, str(default))).strip()
        try:
            value = float(raw)
            if value < 0.0 or value > 1.0:
                raise ValueError(f"{name} must be in [0, 1]")
            return value
        except Exception:
            return default

    def _record_run_metrics(self, intent: str, execution_stats: dict[str, Any], hard_error: bool) -> None:
        """Record per-run metrics into bounded in-memory buffers for SLO snapshots."""
        steps = list((execution_stats or {}).get("steps", []) or [])
        has_timeout = any(str(step.get("error_code") or "") == "TOOL_TIMEOUT" for step in steps)
        has_failure = hard_error or any(str(step.get("status") or "") in {"failed", "blocked"} for step in steps)
        has_fallback = any(bool(step.get("fallback_used")) for step in steps)
        record = {
            "timestamp": datetime.now(),
            "intent": str(intent or "unknown"),
            "has_timeout": has_timeout,
            "has_failure": has_failure,
            "has_fallback": has_fallback,
        }
        with self._health_metrics_lock:
            self._health_metrics.append(record)
            self._prune_old_metrics_locked()

    def _prune_old_metrics_locked(self) -> None:
        """Prune old metrics outside configured health window under lock."""
        if not self._health_metrics:
            return
        cutoff = datetime.now() - timedelta(minutes=self._health_window_minutes)
        while self._health_metrics and self._health_metrics[0]["timestamp"] < cutoff:
            self._health_metrics.popleft()

    def _build_health_metrics_snapshot(self) -> dict[str, Any]:
        """Build current health snapshot including SLO rates and intent aggregates."""
        with self._health_metrics_lock:
            self._prune_old_metrics_locked()
            records = list(self._health_metrics)

        total = len(records)
        timeout_count = sum(1 for item in records if bool(item.get("has_timeout")))
        failure_count = sum(1 for item in records if bool(item.get("has_failure")))
        fallback_count = sum(1 for item in records if bool(item.get("has_fallback")))
        timeout_rate = round(timeout_count / total, 4) if total else 0.0
        failure_rate = round(failure_count / total, 4) if total else 0.0
        fallback_rate = round(fallback_count / total, 4) if total else 0.0

        status = "ok"
        if (
            timeout_rate > float(self._slo_thresholds["timeout_rate"])
            or failure_rate > float(self._slo_thresholds["failure_rate"])
            or fallback_rate > float(self._slo_thresholds["fallback_rate"])
        ):
            status = "degraded"

        intent_aggregate: dict[str, dict[str, Any]] = {}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in records:
            intent = str(item.get("intent") or "unknown")
            grouped.setdefault(intent, []).append(item)
        for intent, items in grouped.items():
            bucket_total = len(items)
            intent_aggregate[intent] = {
                "total": bucket_total,
                "timeout_rate": round(sum(1 for it in items if bool(it.get("has_timeout"))) / bucket_total, 4)
                if bucket_total
                else 0.0,
                "failure_rate": round(sum(1 for it in items if bool(it.get("has_failure"))) / bucket_total, 4)
                if bucket_total
                else 0.0,
                "fallback_rate": round(sum(1 for it in items if bool(it.get("has_fallback"))) / bucket_total, 4)
                if bucket_total
                else 0.0,
            }

        return {
            "slo": {
                "status": status,
                "timeout_rate": timeout_rate,
                "failure_rate": failure_rate,
                "fallback_rate": fallback_rate,
                "thresholds": dict(self._slo_thresholds),
                "total_requests": total,
            },
            "intent_aggregate": intent_aggregate,
        }
