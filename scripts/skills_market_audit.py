"""Audit the governed skills market against onboarding requirements."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import importlib
import importlib.util
import warnings
from dataclasses import dataclass
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

from agent.travel_agent.contracts import SkillContract
from agent.travel_agent.skills import build_default_skill_registry

REQUIRED_ONBOARDING_REQUIREMENTS = ("schema", "tests", "docs", "eval")


@dataclass(slots=True)
class SkillMarketAuditFinding:
    """Describe one skills-market governance finding."""

    skill: str
    field: str
    message: str

    def to_dict(self) -> dict[str, str]:
        """Return one JSON-serializable finding payload."""
        return {
            "skill": self.skill,
            "field": self.field,
            "message": self.message,
        }


def _normalize_repo_path(reference: str | None) -> Path | None:
    """Resolve one repo-relative path while ignoring optional `::anchor` suffixes."""

    if not reference:
        return None
    relative = reference.split("::", 1)[0].strip()
    if not relative:
        return None
    return ROOT.joinpath(*relative.split("/"))


def _path_exists(reference: str | None) -> bool:
    """Return whether one repo-relative governance path exists on disk."""

    candidate = _normalize_repo_path(reference)
    return bool(candidate and candidate.exists())


def audit_skill_contract(skill: SkillContract) -> list[SkillMarketAuditFinding]:
    """Return governance findings for one skill contract."""

    findings: list[SkillMarketAuditFinding] = []
    metadata = skill.market_metadata
    requirements = set(metadata.onboarding_requirements)
    missing_requirements = [
        requirement
        for requirement in REQUIRED_ONBOARDING_REQUIREMENTS
        if requirement not in requirements
    ]

    if not skill.allowed_subagents:
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="allowed_subagents",
                message="missing allowed_subagents for governed rollout",
            )
        )
    if not skill.input_contract.required_context:
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="input_contract.required_context",
                message="missing required input context",
            )
        )
    if not skill.output_contract.artifact:
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="output_contract.artifact",
                message="missing output artifact contract",
            )
        )
    if not skill.output_contract.fields:
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="output_contract.fields",
                message="missing structured output fields",
            )
        )
    if not metadata.owner:
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="market_metadata.owner",
                message="missing owner",
            )
        )
    if not metadata.version:
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="market_metadata.version",
                message="missing version",
            )
        )
    if missing_requirements:
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="market_metadata.onboarding_requirements",
                message=(
                    "missing onboarding requirements: "
                    + ", ".join(missing_requirements)
                ),
            )
        )
    if not metadata.docs_path:
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="market_metadata.docs_path",
                message="missing docs_path",
            )
        )
    elif not _path_exists(metadata.docs_path):
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="market_metadata.docs_path",
                message=f"docs_path does not exist: {metadata.docs_path}",
            )
        )
    if not metadata.test_fixture:
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="market_metadata.test_fixture",
                message="missing test_fixture",
            )
        )
    elif not _path_exists(metadata.test_fixture):
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="market_metadata.test_fixture",
                message=f"test_fixture does not exist: {metadata.test_fixture}",
            )
        )
    if not metadata.eval_fixture:
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="market_metadata.eval_fixture",
                message="missing eval_fixture",
            )
        )
    elif not _path_exists(metadata.eval_fixture):
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="market_metadata.eval_fixture",
                message=f"eval_fixture does not exist: {metadata.eval_fixture}",
            )
        )

    onboarding_doc = skill.metadata.get("onboarding_doc")
    if not isinstance(onboarding_doc, str) or not onboarding_doc.strip():
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="metadata.onboarding_doc",
                message="missing onboarding_doc pointer",
            )
        )
    elif not _path_exists(onboarding_doc):
        findings.append(
            SkillMarketAuditFinding(
                skill=skill.name,
                field="metadata.onboarding_doc",
                message=f"onboarding_doc does not exist: {onboarding_doc}",
            )
        )

    return findings


def build_skills_market_audit_report() -> dict[str, Any]:
    """Audit the default skills catalog and return a structured report."""

    skills = build_default_skill_registry().all_skills()
    findings = [
        finding.to_dict()
        for skill in skills
        for finding in audit_skill_contract(skill)
    ]

    return {
        "audited_skills": len(skills),
        "required_onboarding_requirements": list(REQUIRED_ONBOARDING_REQUIREMENTS),
        "skills": [skill.name for skill in skills],
        "findings": findings,
    }


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser for the skills-market audit."""

    parser = argparse.ArgumentParser(
        description="Audit the governed skills market against schema/tests/docs/eval onboarding requirements."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when any governance finding is discovered.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the skills-market audit CLI."""

    parser = build_parser()
    args = parser.parse_args(argv)
    report = build_skills_market_audit_report()
    print(f"audited_skills={report['audited_skills']}")
    print(f"findings={len(report['findings'])}")
    if report["findings"]:
        for finding in report["findings"]:
            print(
                f"{finding['skill']}|{finding['field']}|{finding['message']}"
            )
    if args.strict and report["findings"]:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
