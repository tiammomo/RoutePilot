"""Unit tests for ADR / RFC / design-review audit script."""

from __future__ import annotations

from pathlib import Path

from scripts import decision_record_audit


def test_audit_record_reports_missing_sections(tmp_path: Path) -> None:
    """Flag records that miss required sections for their family."""

    record = tmp_path / "ADR-9999-demo.md"
    record.write_text("# ADR-9999 Demo\n\n## Status\n\nStatus: proposed\n", encoding="utf-8")

    rule = decision_record_audit.AuditRule(
        label="adr",
        root="docs/governance/adr",
        pattern="ADR-*.md",
        required_sections=decision_record_audit.ADR_REQUIRED_SECTIONS,
        required_status_prefix=decision_record_audit.ADR_STATUS_PREFIX,
    )

    findings = decision_record_audit.audit_record(record, tmp_path, rule)

    assert any("missing required section `## Context`" == finding.detail for finding in findings)
    assert any("missing required section `## Decision`" == finding.detail for finding in findings)
    assert any("missing required section `## Consequences`" == finding.detail for finding in findings)


def test_audit_record_accepts_complete_record(tmp_path: Path) -> None:
    """Accept records that include all required sections and status prefix."""

    record = tmp_path / "RFC-1234-demo.md"
    record.write_text(
        "\n".join(
            [
                "# RFC-1234 Demo",
                "",
                "## Status",
                "",
                "Status: draft",
                "",
                "## Problem",
                "",
                "Problem statement.",
                "",
                "## Proposal",
                "",
                "Proposal body.",
                "",
                "## Rollout",
                "",
                "Rollout plan.",
                "",
                "## Risks",
                "",
                "Risk list.",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    rule = decision_record_audit.AuditRule(
        label="rfc",
        root="docs/governance/rfcs",
        pattern="RFC-*.md",
        required_sections=decision_record_audit.RFC_REQUIRED_SECTIONS,
        required_status_prefix=decision_record_audit.RFC_STATUS_PREFIX,
    )

    findings = decision_record_audit.audit_record(record, tmp_path, rule)

    assert findings == []


def test_audit_all_records_collects_findings_across_families(tmp_path: Path) -> None:
    """Audit all configured record families under the governance tree."""

    adr_dir = tmp_path / "docs" / "governance" / "adr"
    rfc_dir = tmp_path / "docs" / "governance" / "rfcs"
    review_dir = tmp_path / "docs" / "governance" / "design-reviews"
    adr_dir.mkdir(parents=True)
    rfc_dir.mkdir(parents=True)
    review_dir.mkdir(parents=True)

    (adr_dir / "ADR-0001-demo.md").write_text(
        "# ADR\n\n## Status\n\nStatus: accepted\n\n## Context\n\n...\n\n## Decision\n\n...\n\n## Consequences\n\n...\n",
        encoding="utf-8",
    )
    (rfc_dir / "RFC-0001-demo.md").write_text(
        "# RFC\n\n## Status\n\nStatus: draft\n\n## Problem\n\n...\n",
        encoding="utf-8",
    )
    (review_dir / "DR-0001-demo.md").write_text(
        "# DR\n\n## Status\n\nStatus: draft\n\n## Scope\n\n...\n\n## Review Checklist\n\n...\n\n## Decision\n\n...\n",
        encoding="utf-8",
    )

    findings, audited_paths = decision_record_audit.audit_all_records(tmp_path)

    assert sorted(audited_paths) == [
        "docs/governance/adr/ADR-0001-demo.md",
        "docs/governance/design-reviews/DR-0001-demo.md",
        "docs/governance/rfcs/RFC-0001-demo.md",
    ]
    assert any(finding.path.endswith("RFC-0001-demo.md") for finding in findings)
    assert any(finding.path.endswith("DR-0001-demo.md") for finding in findings)
