#!/usr/bin/env python3
"""Validate ADR / RFC / design-review records and templates."""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


ADR_STATUS_PREFIX = "Status:"
RFC_STATUS_PREFIX = "Status:"
DESIGN_REVIEW_STATUS_PREFIX = "Status:"

ADR_REQUIRED_SECTIONS = ("## Status", "## Context", "## Decision", "## Consequences")
RFC_REQUIRED_SECTIONS = ("## Status", "## Problem", "## Proposal", "## Rollout", "## Risks")
DESIGN_REVIEW_REQUIRED_SECTIONS = (
    "## Status",
    "## Scope",
    "## Review Checklist",
    "## Decision",
    "## Follow-ups",
)


@dataclass(frozen=True)
class AuditRule:
    """Describe one family of architecture decision records."""

    label: str
    root: str
    pattern: str
    required_sections: tuple[str, ...]
    required_status_prefix: str


@dataclass(frozen=True)
class AuditFinding:
    """Represent one missing requirement in a decision record."""

    label: str
    path: str
    detail: str


DEFAULT_RULES: tuple[AuditRule, ...] = (
    AuditRule(
        label="adr",
        root="docs/governance/adr",
        pattern="ADR-*.md",
        required_sections=ADR_REQUIRED_SECTIONS,
        required_status_prefix=ADR_STATUS_PREFIX,
    ),
    AuditRule(
        label="rfc",
        root="docs/governance/rfcs",
        pattern="RFC-*.md",
        required_sections=RFC_REQUIRED_SECTIONS,
        required_status_prefix=RFC_STATUS_PREFIX,
    ),
    AuditRule(
        label="design-review",
        root="docs/governance/design-reviews",
        pattern="DR-*.md",
        required_sections=DESIGN_REVIEW_REQUIRED_SECTIONS,
        required_status_prefix=DESIGN_REVIEW_STATUS_PREFIX,
    ),
)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for record auditing."""

    parser = argparse.ArgumentParser(
        description="Audit ADR / RFC / design-review records for required sections."
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail when any record is missing required sections or status.",
    )
    parser.add_argument(
        "--max-output",
        type=int,
        default=20,
        help="Maximum number of sample findings to print.",
    )
    return parser.parse_args()


def repo_root() -> Path:
    """Return the repository root based on the script path."""

    return Path(__file__).resolve().parent.parent


def iter_record_paths(root: Path, rule: AuditRule) -> Iterable[Path]:
    """Yield tracked record files for one rule."""

    record_root = root / rule.root
    if not record_root.exists():
        return []
    return sorted(record_root.glob(rule.pattern))


def audit_record(path: Path, root: Path, rule: AuditRule) -> list[AuditFinding]:
    """Collect missing requirements for one record file."""

    content = path.read_text(encoding="utf-8")
    findings: list[AuditFinding] = []
    relative_path = path.relative_to(root).as_posix()

    if rule.required_status_prefix not in content:
        findings.append(
            AuditFinding(rule.label, relative_path, f"missing status prefix `{rule.required_status_prefix}`")
        )

    for section in rule.required_sections:
        if section not in content:
            findings.append(
                AuditFinding(rule.label, relative_path, f"missing required section `{section}`")
            )

    return findings


def audit_all_records(root: Path) -> tuple[list[AuditFinding], list[str]]:
    """Audit all configured record families."""

    findings: list[AuditFinding] = []
    audited_paths: list[str] = []
    for rule in DEFAULT_RULES:
        for path in iter_record_paths(root, rule):
            audited_paths.append(path.relative_to(root).as_posix())
            findings.extend(audit_record(path, root, rule))
    return findings, audited_paths


def main() -> int:
    """Run the architecture decision record audit."""

    args = parse_args()
    root = repo_root()
    findings, audited_paths = audit_all_records(root)

    print(f"audited_records={len(audited_paths)}")
    print(f"findings={len(findings)}")
    if audited_paths:
        print("records:")
        for path in audited_paths[: args.max_output]:
            print(path)

    if findings:
        print("sample_findings:")
        for finding in findings[: args.max_output]:
            print(f"{finding.label}|{finding.path}|{finding.detail}")

    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
