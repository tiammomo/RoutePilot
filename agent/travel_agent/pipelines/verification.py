"""Verification pipeline extracted from graph nodes to reduce stage coupling."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel


class VerificationPipeline:
    """Evaluate evidence freshness/completeness and decide retry vs degrade flow."""

    def __init__(
        self,
        *,
        runtime_config: Any,
        refreshable_tools: set[str],
        stage_output_model: type[BaseModel],
        issue_model: type[BaseModel],
        result_model: type[BaseModel],
        validate_stage_output: Callable[[type[BaseModel], dict[str, Any]], dict[str, Any]],
        last_user_text: Callable[[Mapping[str, Any]], str],
        is_high_risk_query: Callable[[str, str], bool],
    ) -> None:
        """Store collaborators required to evaluate one verification stage."""
        self.runtime_config = runtime_config
        self.refreshable_tools = refreshable_tools
        self.stage_output_model = stage_output_model
        self.issue_model = issue_model
        self.result_model = result_model
        self.validate_stage_output = validate_stage_output
        self.last_user_text = last_user_text
        self.is_high_risk_query = is_high_risk_query

    def build(self, state: Mapping[str, Any]) -> dict[str, Any]:
        """Build the verification-stage state patch for one graph turn."""
        intent = str(state.get("intent") or "general")
        strategy_detail = self._as_dict(state.get("strategy_detail"))
        requires_verification = bool(strategy_detail.get("requires_verification", False))
        required_tools = [str(item) for item in strategy_detail.get("required_tools", [])]
        verify_retry_count = self._safe_int(state.get("verify_retry_count"), 0)
        tool_results = self._as_dict(state.get("tool_results"))
        user_text = self.last_user_text(state)
        issues: list[BaseModel] = []

        successful_results = [
            item
            for item in tool_results.values()
            if isinstance(item, dict) and bool(item.get("success"))
        ]
        if requires_verification and not successful_results:
            issues.append(
                self.issue_model(
                    issue_type="missing_evidence",
                    message="高风险问题缺少工具成功结果，无法验证结论。",
                    severity="high",
                )
            )

        matched_success_tools = {
            str(item.get("tool_name") or "").split(":")[-1]
            for item in successful_results
            if isinstance(item, dict)
        }
        missing_required = [name for name in required_tools if name not in matched_success_tools]
        if requires_verification and missing_required:
            issues.append(
                self.issue_model(
                    issue_type="required_tools_missing",
                    message=f"缺少必选验证工具结果: {missing_required}",
                    severity="high",
                )
            )

        stale_count = 0
        refresh_targets: list[str] = []
        refresh_tools: list[str] = []
        for key, item in tool_results.items():
            if not isinstance(item, dict) or not bool(item.get("success")):
                continue
            if not bool(item.get("is_stale", False)):
                continue
            stale_count += 1
            tool_name = str(item.get("tool_name") or "").split(":")[-1]
            step_id = str(key).split(":", 1)[0].strip()
            if tool_name in self.refreshable_tools and step_id:
                if step_id not in refresh_targets:
                    refresh_targets.append(step_id)
                if tool_name not in refresh_tools:
                    refresh_tools.append(tool_name)

        if stale_count > 0:
            issues.append(
                self.issue_model(
                    issue_type="stale_data",
                    message=f"存在 {stale_count} 条过期结果，建议刷新后再回答。",
                    severity="medium",
                )
            )
            if verify_retry_count >= 1:
                issues.append(
                    self.issue_model(
                        issue_type="stale_refresh_failed",
                        message="已尝试刷新过期数据，但仍无法得到稳定实时结果，建议按降级策略回答并标注不确定性。",
                        severity="high",
                    )
                )
            elif not refresh_targets:
                issues.append(
                    self.issue_model(
                        issue_type="stale_unrefreshable",
                        message="存在过期结果，但缺少可刷新的天气/酒店工具步骤，建议按降级策略回答。",
                        severity="medium",
                    )
                )

        if not self.runtime_config.timeliness_controls_enabled:
            refresh_targets = []
            refresh_tools = []

        fetched_dates: list[datetime] = []
        for item in successful_results:
            raw = item.get("fetched_at")
            if not raw:
                continue
            try:
                dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                fetched_dates.append(dt)
            except Exception:
                continue
        if len(fetched_dates) >= 2:
            span_seconds = (max(fetched_dates) - min(fetched_dates)).total_seconds()
            if span_seconds > 7 * 24 * 3600:
                issues.append(
                    self.issue_model(
                        issue_type="date_inconsistency",
                        message="工具结果时间跨度过大，可能存在时效不一致。",
                        severity="medium",
                    )
                )

        if self.is_high_risk_query(user_text, intent) and not requires_verification:
            issues.append(
                self.issue_model(
                    issue_type="verification_policy_violation",
                    message="高风险问题未开启验证策略。",
                    severity="high",
                )
            )

        stale_retryable = stale_count > 0 and bool(refresh_targets) and verify_retry_count < 1
        structural_retryable = any(
            item.issue_type in {"missing_evidence", "required_tools_missing"}
            for item in issues
        ) and verify_retry_count < 1
        should_retry = stale_retryable or structural_retryable
        if not stale_retryable:
            refresh_targets = []
            refresh_tools = []

        passed = len(issues) == 0
        summary = "verification_passed" if passed else "; ".join(item.message for item in issues)

        result = self.result_model(
            passed=passed,
            should_retry=should_retry,
            refresh_targets=refresh_targets,
            refresh_tools=refresh_tools,
            issues=issues,
            summary=summary,
        )
        return self.validate_stage_output(
            self.stage_output_model,
            {
                "verify_result": result.model_dump(),
                "verify_retry_count": verify_retry_count + (1 if should_retry else 0),
                "early_stop_reason": state.get("early_stop_reason") if passed else summary,
            },
        )

    @staticmethod
    def _as_dict(value: Any) -> dict[str, Any]:
        """Coerce optional mapping-like values into a plain dict."""
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _safe_int(value: Any, default: int) -> int:
        """Parse integer-like values defensively while preserving a fallback."""
        try:
            return int(value)
        except (TypeError, ValueError):
            return default


__all__ = ["VerificationPipeline"]
