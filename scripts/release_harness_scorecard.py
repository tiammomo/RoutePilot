"""Build a release-facing scorecard for delivery, skills, and agent quality artifacts."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import re
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

if __package__:
    _bootstrap_paths = importlib.import_module(f"{__package__}.bootstrap_paths")
else:
    _bootstrap_paths_path = Path(__file__).with_name("bootstrap_paths.py")
    _bootstrap_paths_spec = importlib.util.spec_from_file_location("bootstrap_paths", _bootstrap_paths_path)
    if _bootstrap_paths_spec is None or _bootstrap_paths_spec.loader is None:
        raise ImportError(f"Unable to load bootstrap_paths from {_bootstrap_paths_path}")
    _bootstrap_paths = importlib.util.module_from_spec(_bootstrap_paths_spec)
    _bootstrap_paths_spec.loader.exec_module(_bootstrap_paths)

ROOT = _bootstrap_paths.PROJECT_ROOT
ensure_project_paths = _bootstrap_paths.ensure_project_paths

warnings.filterwarnings(
    "ignore",
    message="Core Pydantic V1 functionality isn't compatible with Python 3.14 or greater.",
    category=UserWarning,
)

ensure_project_paths()

DEFAULT_OUTPUT_DIR = ROOT / "docs" / "benchmarks"
DEFAULT_BENCHMARK_REPORT = ROOT / "docs" / "benchmarks" / "agent_benchmark_latest.json"
DEFAULT_GOLDEN_REPORT = ROOT / "docs" / "benchmarks" / "agent_golden_eval_latest.json"
DEFAULT_SUBAGENT_SCORECARD = ROOT / "docs" / "benchmarks" / "agent_subagent_scorecard_latest.json"
DEFAULT_DELIVERY_SNAPSHOT = (
    ROOT
    / "frontend"
    / "tests"
    / "features"
    / "trip-plan"
    / "__snapshots__"
    / "travelPlanDeliverySnapshot.test.ts.snap"
)
DEFAULT_SKILLS_CATALOG = ROOT / "docs" / "reference" / "skills-market-catalog.md"
EXPECTED_DELIVERY_MODES = ["direct", "plan", "react"]
EXPECTED_SUBAGENTS = ["research", "planning", "budget", "verification"]


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _repo_relative_text(path: Path) -> str:
    """Return one repo-relative POSIX path string when possible."""
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _safe_float(value: Any, default: float = 0.0) -> float:
    """Convert one value to float while tolerating missing or malformed input."""
    try:
        return float(value)
    except Exception:
        return default


def _safe_int(value: Any, default: int = 0) -> int:
    """Convert one value to int while tolerating missing or malformed input."""
    try:
        return int(value)
    except Exception:
        return default


def _load_json(path: Path) -> dict[str, Any]:
    """Load one JSON file from disk and fail when it is missing."""
    if not path.exists():
        raise FileNotFoundError(f"Report not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _load_text(path: Path) -> str:
    """Load one UTF-8 text file from disk and fail when it is missing."""
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return path.read_text(encoding="utf-8")


def _append_finding(
    findings: list[dict[str, str]],
    *,
    severity: str,
    category: str,
    message: str,
) -> None:
    """Append one normalized finding entry."""
    findings.append(
        {
            "severity": severity,
            "category": category,
            "message": message,
        }
    )


def _load_default_skills() -> list[Any]:
    """Return the default governed skill catalog used by release checks."""
    from agent.travel_agent.skills import build_default_skill_registry

    return build_default_skill_registry().all_skills()


def _build_benchmark_summary(
    *,
    golden_report: Path,
    benchmark_report: Path,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    """Build the golden/benchmark summary shown in the release scorecard."""
    golden = _load_json(golden_report)
    benchmark = _load_json(benchmark_report)
    benchmark_aggregate = benchmark.get("aggregate", {}) if isinstance(benchmark, dict) else {}

    golden_pass_rate = _safe_float(golden.get("pass_rate"), 0.0)
    golden_hallucination_rate = _safe_float(golden.get("hallucination_rate"), 1.0)
    benchmark_success_rate = _safe_float(benchmark_aggregate.get("avg_success_rate"), 0.0)
    benchmark_hallucination_rate = _safe_float(benchmark_aggregate.get("hallucination_rate"), 1.0)
    fallback_steps_total = _safe_int(benchmark_aggregate.get("fallback_steps_total"), 0)

    if golden_pass_rate < 0.96:
        _append_finding(
            findings,
            severity="warning",
            category="benchmark",
            message=f"golden pass_rate is below release target: {golden_pass_rate:.4f}",
        )
    if golden_hallucination_rate > 0.05:
        _append_finding(
            findings,
            severity="warning",
            category="benchmark",
            message=(
                "golden hallucination_rate is above release target: "
                f"{golden_hallucination_rate:.4f}"
            ),
        )
    if benchmark_success_rate < 0.60:
        _append_finding(
            findings,
            severity="warning",
            category="benchmark",
            message=f"benchmark avg_success_rate is below release target: {benchmark_success_rate:.4f}",
        )
    if benchmark_hallucination_rate > 0.05:
        _append_finding(
            findings,
            severity="warning",
            category="benchmark",
            message=(
                "benchmark hallucination_rate is above release target: "
                f"{benchmark_hallucination_rate:.4f}"
            ),
        )

    return {
        "golden_report": _repo_relative_text(golden_report),
        "benchmark_report": _repo_relative_text(benchmark_report),
        "golden_pass_rate": golden_pass_rate,
        "golden_hallucination_rate": golden_hallucination_rate,
        "benchmark_success_rate": benchmark_success_rate,
        "benchmark_hallucination_rate": benchmark_hallucination_rate,
        "fallback_steps_total": fallback_steps_total,
    }


def _build_subagent_summary(
    *,
    scorecard_report: Path,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    """Build one subagent collaboration summary from the replay-backed scorecard."""
    payload = _load_json(scorecard_report)
    aggregate = payload.get("aggregate", {}) if isinstance(payload, dict) else {}
    expected_subagents = aggregate.get("expected_subagents") or []
    observed_subagents = aggregate.get("observed_subagents") or []

    if sorted(expected_subagents) != sorted(EXPECTED_SUBAGENTS):
        _append_finding(
            findings,
            severity="error",
            category="subagents",
            message=(
                "subagent scorecard is missing the canonical expected set: "
                f"{EXPECTED_SUBAGENTS}"
            ),
        )

    missing_subagents = _safe_int(aggregate.get("missing_subagents"), 0)
    mismatch_subagents = _safe_int(aggregate.get("mismatch_subagents"), 0)
    partial_subagents = _safe_int(aggregate.get("partial_subagents"), 0)
    healthy_subagents = _safe_int(aggregate.get("healthy_subagents"), 0)

    if missing_subagents > 0:
        _append_finding(
            findings,
            severity="warning",
            category="subagents",
            message=f"subagent scorecard still reports {missing_subagents} missing subagent(s)",
        )
    if mismatch_subagents > 0:
        _append_finding(
            findings,
            severity="warning",
            category="subagents",
            message=f"subagent scorecard still reports {mismatch_subagents} mismatch subagent(s)",
        )

    return {
        "scorecard_report": _repo_relative_text(scorecard_report),
        "expected_subagents": list(expected_subagents),
        "observed_subagents": list(observed_subagents),
        "healthy_subagents": healthy_subagents,
        "partial_subagents": partial_subagents,
        "missing_subagents": missing_subagents,
        "mismatch_subagents": mismatch_subagents,
    }


def _build_delivery_summary(
    *,
    delivery_snapshot: Path,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    """Build one delivery harness summary from the committed HTML snapshot fixture."""
    snapshot_text = _load_text(delivery_snapshot)
    modes = sorted(set(re.findall(r"replays ([a-z]+) mode", snapshot_text)))
    missing_modes = [mode for mode in EXPECTED_DELIVERY_MODES if mode not in modes]
    has_branding = "Moyuan Travel Agent" in snapshot_text

    if missing_modes:
        _append_finding(
            findings,
            severity="error",
            category="delivery",
            message=f"delivery snapshot is missing replay modes: {', '.join(missing_modes)}",
        )
    if not has_branding:
        _append_finding(
            findings,
            severity="error",
            category="delivery",
            message="delivery snapshot is missing the expected Moyuan Travel Agent branding",
        )

    return {
        "snapshot_path": _repo_relative_text(delivery_snapshot),
        "modes_covered": modes,
        "expected_modes": list(EXPECTED_DELIVERY_MODES),
        "branding_present": has_branding,
    }


def _build_skills_summary(
    *,
    skills_catalog: Path,
    findings: list[dict[str, str]],
) -> dict[str, Any]:
    """Build one governed skills-market summary for release checks."""
    catalog_text = _load_text(skills_catalog)
    skills = _load_default_skills()

    docs_covered = 0
    eval_covered = 0
    selection_policy_covered = 0
    onboarding_complete = 0
    issues: list[str] = []

    for skill in skills:
        if skill.market_metadata.docs_path:
            docs_covered += 1
        else:
            issues.append(f"{skill.name} is missing docs_path")

        if skill.market_metadata.eval_fixture:
            eval_covered += 1
        else:
            issues.append(f"{skill.name} is missing eval_fixture")

        if skill.allowed_subagents:
            onboarding_complete += 1
        else:
            issues.append(f"{skill.name} is missing allowed_subagents")

        if skill.selection_policy.priority > 0:
            selection_policy_covered += 1
        else:
            issues.append(f"{skill.name} is missing a positive selection priority")

        if not skill.selection_policy.intent_signals:
            issues.append(f"{skill.name} is missing selection intent signals")

    for issue in issues:
        _append_finding(
            findings,
            severity="error",
            category="skills",
            message=issue,
        )

    if "selection policy" not in catalog_text.lower():
        _append_finding(
            findings,
            severity="error",
            category="skills",
            message="skills catalog is missing the selection policy section",
        )

    return {
        "skills_catalog": _repo_relative_text(skills_catalog),
        "total_skills": len(skills),
        "docs_covered": docs_covered,
        "eval_covered": eval_covered,
        "selection_policy_covered": selection_policy_covered,
        "allowed_subagents_covered": onboarding_complete,
        "skill_names": [skill.name for skill in skills],
    }


def build_release_harness_scorecard(
    *,
    golden_report: Path = DEFAULT_GOLDEN_REPORT,
    benchmark_report: Path = DEFAULT_BENCHMARK_REPORT,
    subagent_scorecard_report: Path = DEFAULT_SUBAGENT_SCORECARD,
    delivery_snapshot: Path = DEFAULT_DELIVERY_SNAPSHOT,
    skills_catalog: Path = DEFAULT_SKILLS_CATALOG,
) -> dict[str, Any]:
    """Build one release-harness scorecard from committed benchmark and governance artifacts."""
    findings: list[dict[str, str]] = []

    benchmark_summary = _build_benchmark_summary(
        golden_report=golden_report,
        benchmark_report=benchmark_report,
        findings=findings,
    )
    subagent_summary = _build_subagent_summary(
        scorecard_report=subagent_scorecard_report,
        findings=findings,
    )
    delivery_summary = _build_delivery_summary(
        delivery_snapshot=delivery_snapshot,
        findings=findings,
    )
    skills_summary = _build_skills_summary(
        skills_catalog=skills_catalog,
        findings=findings,
    )

    errors = [finding for finding in findings if finding["severity"] == "error"]
    warnings_found = [finding for finding in findings if finding["severity"] == "warning"]
    status = "pass"
    if errors:
        status = "fail"
    elif warnings_found:
        status = "warn"

    return {
        "generated_at": utc_now_iso(),
        "status": status,
        "summary": {
            "error_count": len(errors),
            "warning_count": len(warnings_found),
        },
        "benchmark": benchmark_summary,
        "subagents": subagent_summary,
        "delivery": delivery_summary,
        "skills": skills_summary,
        "findings": findings,
    }


def _render_markdown(scorecard: dict[str, Any]) -> str:
    """Render one markdown summary for the release harness scorecard."""
    summary = scorecard.get("summary", {})
    benchmark = scorecard.get("benchmark", {})
    subagents = scorecard.get("subagents", {})
    delivery = scorecard.get("delivery", {})
    skills = scorecard.get("skills", {})

    lines = [
        "# Release Harness Scorecard",
        "",
        f"- generated_at: `{scorecard.get('generated_at', 'unknown')}`",
        f"- status: `{scorecard.get('status', 'unknown')}`",
        f"- errors: `{summary.get('error_count', 0)}`",
        f"- warnings: `{summary.get('warning_count', 0)}`",
        "",
        "## Benchmark",
        "",
        f"- golden pass rate: `{benchmark.get('golden_pass_rate', 0.0):.4f}`",
        f"- golden hallucination rate: `{benchmark.get('golden_hallucination_rate', 0.0):.4f}`",
        f"- benchmark success rate: `{benchmark.get('benchmark_success_rate', 0.0):.4f}`",
        f"- benchmark fallback steps total: `{benchmark.get('fallback_steps_total', 0)}`",
        "",
        "## Subagents",
        "",
        f"- expected: `{subagents.get('expected_subagents', [])}`",
        f"- observed: `{subagents.get('observed_subagents', [])}`",
        f"- healthy / partial / missing / mismatch: "
        f"`{subagents.get('healthy_subagents', 0)} / {subagents.get('partial_subagents', 0)} / "
        f"{subagents.get('missing_subagents', 0)} / {subagents.get('mismatch_subagents', 0)}`",
        "",
        "## Delivery",
        "",
        f"- snapshot: `{delivery.get('snapshot_path', '')}`",
        f"- replay modes: `{delivery.get('modes_covered', [])}`",
        f"- branding present: `{delivery.get('branding_present', False)}`",
        "",
        "## Skills",
        "",
        f"- total skills: `{skills.get('total_skills', 0)}`",
        f"- docs covered: `{skills.get('docs_covered', 0)}`",
        f"- eval covered: `{skills.get('eval_covered', 0)}`",
        f"- selection policy covered: `{skills.get('selection_policy_covered', 0)}`",
        "",
        "## Findings",
        "",
    ]
    findings = scorecard.get("findings", [])
    if not findings:
        lines.append("- none")
    else:
        for finding in findings:
            lines.append(
                f"- `{finding.get('severity', 'unknown')}` "
                f"`{finding.get('category', 'unknown')}`: {finding.get('message', '')}"
            )
    lines.append("")
    return "\n".join(lines)


def export_release_harness_scorecard(
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    *,
    golden_report: Path = DEFAULT_GOLDEN_REPORT,
    benchmark_report: Path = DEFAULT_BENCHMARK_REPORT,
    subagent_scorecard_report: Path = DEFAULT_SUBAGENT_SCORECARD,
    delivery_snapshot: Path = DEFAULT_DELIVERY_SNAPSHOT,
    skills_catalog: Path = DEFAULT_SKILLS_CATALOG,
) -> tuple[dict[str, Any], Path, Path]:
    """Write release-harness scorecard JSON and markdown to the requested directory."""
    scorecard = build_release_harness_scorecard(
        golden_report=golden_report,
        benchmark_report=benchmark_report,
        subagent_scorecard_report=subagent_scorecard_report,
        delivery_snapshot=delivery_snapshot,
        skills_catalog=skills_catalog,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "release_harness_scorecard_latest.json"
    markdown_path = output_dir / "release_harness_scorecard_latest.md"
    json_path.write_text(
        json.dumps(scorecard, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    markdown_path.write_text(_render_markdown(scorecard) + "\n", encoding="utf-8")
    return scorecard, json_path, markdown_path


def build_parser() -> argparse.ArgumentParser:
    """Construct the CLI parser for release-harness scorecard export."""
    parser = argparse.ArgumentParser(
        description="Export a release harness scorecard for delivery, skills, and agent quality artifacts."
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory for JSON and markdown scorecard outputs.",
    )
    parser.add_argument(
        "--golden-report",
        default=str(DEFAULT_GOLDEN_REPORT),
        help="Golden eval report path.",
    )
    parser.add_argument(
        "--benchmark-report",
        default=str(DEFAULT_BENCHMARK_REPORT),
        help="Benchmark report path.",
    )
    parser.add_argument(
        "--subagent-scorecard-report",
        default=str(DEFAULT_SUBAGENT_SCORECARD),
        help="Replay-backed subagent scorecard report path.",
    )
    parser.add_argument(
        "--delivery-snapshot",
        default=str(DEFAULT_DELIVERY_SNAPSHOT),
        help="Frontend delivery snapshot path.",
    )
    parser.add_argument(
        "--skills-catalog",
        default=str(DEFAULT_SKILLS_CATALOG),
        help="Skills market catalog path.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when the scorecard reports critical failures.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for release-harness scorecard export."""
    parser = build_parser()
    args = parser.parse_args(argv)
    scorecard, json_path, markdown_path = export_release_harness_scorecard(
        Path(args.output_dir),
        golden_report=Path(args.golden_report),
        benchmark_report=Path(args.benchmark_report),
        subagent_scorecard_report=Path(args.subagent_scorecard_report),
        delivery_snapshot=Path(args.delivery_snapshot),
        skills_catalog=Path(args.skills_catalog),
    )
    print(f"Release harness scorecard JSON report: {json_path}")
    print(f"Release harness scorecard Markdown report: {markdown_path}")
    if args.strict and scorecard.get("status") == "fail":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
