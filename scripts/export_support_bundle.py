"""Export a support bundle with runtime diagnostics, contracts, and live probe captures."""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import importlib
import importlib.util
import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx


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
ensure_project_paths()

from scripts.runtime_data_utils import discover_runtime_files, snapshot_timestamp_slug
from scripts.runtime_ops_contracts import (
    CheckpointRuntimeView,
    ReleaseHarnessScorecard,
    ReleaseManifest,
    RuntimeDoctorReport,
    SupportBundleDeliveryEvidenceSection,
    SupportBundleManifest,
    SupportBundleReleaseEvidenceSection,
    SupportBundleRuntimeHealthSection,
)
from scripts.runtime_doctor import render_text_report, run_runtime_doctor


DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "support"
DEFAULT_RELEASE_MANIFEST = ROOT / "artifacts" / "release" / "release-manifest.json"
DEFAULT_RELEASE_SCORECARD = ROOT / "docs" / "benchmarks" / "release_harness_scorecard_latest.json"


def utc_now_iso() -> str:
    """Return the current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _http_snapshot(base_url: str) -> dict[str, dict[str, Any]]:
    """Capture health, readiness, liveness, and metrics payloads from a running API."""
    base = base_url.rstrip("/")
    endpoints = {
        "health": f"{base}/api/health",
        "ready": f"{base}/api/ready",
        "live": f"{base}/api/live",
        "metrics": f"{base}/api/metrics",
    }
    snapshots: dict[str, dict[str, Any]] = {}
    with httpx.Client(timeout=5.0) as client:
        for name, url in endpoints.items():
            try:
                response = client.get(url)
                entry = {
                    "url": url,
                    "status_code": response.status_code,
                    "content_type": response.headers.get("content-type", ""),
                }
                if "application/json" in entry["content_type"]:
                    entry["body"] = response.json()
                else:
                    entry["body"] = response.text
            except Exception as exc:
                entry = {
                    "url": url,
                    "status_code": None,
                    "content_type": "",
                    "body": {"error": str(exc)},
                }
            snapshots[name] = entry
    return snapshots


def export_support_bundle(
    *,
    project_root: Path = ROOT,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    base_url: str | None = None,
    release_manifest_path: Path = DEFAULT_RELEASE_MANIFEST,
    release_scorecard_path: Path = DEFAULT_RELEASE_SCORECARD,
) -> Path:
    """Export a zip bundle containing runtime diagnostics and supporting artifacts."""
    project_root = Path(project_root)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    doctor_report = RuntimeDoctorReport.from_dict(
        run_runtime_doctor(project_root=project_root, base_url=base_url)
    )
    checkpoint_runtime_check = doctor_report.checks.get("checkpoint_runtime")
    checkpoint_runtime = CheckpointRuntimeView.from_dict(
        checkpoint_runtime_check.details if checkpoint_runtime_check is not None else {}
    )
    runtime_files = discover_runtime_files(project_root)
    http_snapshot = _http_snapshot(base_url) if base_url else None
    release_manifest = None
    if Path(release_manifest_path).exists():
        release_manifest = ReleaseManifest.from_dict(
            json.loads(Path(release_manifest_path).read_text(encoding="utf-8"))
        )
    release_scorecard = None
    if Path(release_scorecard_path).exists():
        release_scorecard = ReleaseHarnessScorecard.from_dict(
            json.loads(Path(release_scorecard_path).read_text(encoding="utf-8"))
        )
    included_contract_snapshots = [
        snapshot_name
        for snapshot_name in ("openapi.snapshot.json", "sse-contract.snapshot.json")
        if (project_root / "docs" / "reference" / snapshot_name).exists()
    ]

    bundle_name = f"support_bundle_{snapshot_timestamp_slug()}.zip"
    bundle_path = output_dir / bundle_name
    manifest = SupportBundleManifest(
        created_at=utc_now_iso(),
        project_root=str(project_root),
        base_url=base_url,
        runtime_health=SupportBundleRuntimeHealthSection.from_doctor_report(doctor_report),
        release_evidence=SupportBundleReleaseEvidenceSection.from_release_artifacts(
            manifest=release_manifest,
            manifest_path=str(release_manifest_path),
            scorecard=release_scorecard,
            scorecard_path=str(release_scorecard_path),
        ),
        delivery_evidence=SupportBundleDeliveryEvidenceSection(
            contract_snapshots=included_contract_snapshots,
            includes_http_snapshot=http_snapshot is not None,
        ),
    )

    with zipfile.ZipFile(bundle_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest.to_dict(), ensure_ascii=False, indent=2) + "\n")
        archive.writestr("doctor-report.json", json.dumps(doctor_report.to_dict(), ensure_ascii=False, indent=2) + "\n")
        archive.writestr("doctor-report.txt", render_text_report(doctor_report) + "\n")
        archive.writestr(
            "checkpoint-runtime.json",
            json.dumps(checkpoint_runtime.to_dict(), ensure_ascii=False, indent=2) + "\n",
        )
        archive.writestr(
            "runtime-files.json",
            json.dumps(
                [
                    {
                        "key": item["key"],
                        "relative_path": item["relative_path"],
                        "size_bytes": item["size_bytes"],
                        "sha256": item["sha256"],
                    }
                    for item in runtime_files
                ],
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )

        if Path(release_manifest_path).exists():
            archive.write(release_manifest_path, arcname="release-manifest.json")
        if Path(release_scorecard_path).exists():
            archive.write(release_scorecard_path, arcname="release-harness-scorecard.json")

        for snapshot_name in ("openapi.snapshot.json", "sse-contract.snapshot.json"):
            snapshot_path = project_root / "docs" / "reference" / snapshot_name
            if snapshot_path.exists():
                archive.write(snapshot_path, arcname=f"contracts/{snapshot_name}")

        if http_snapshot is not None:
            for name, payload in http_snapshot.items():
                body = payload.get("body")
                if isinstance(body, (dict, list)):
                    archive.writestr(
                        f"http/{name}.json",
                        json.dumps(body, ensure_ascii=False, indent=2) + "\n",
                    )
                else:
                    archive.writestr(f"http/{name}.txt", str(body))
                archive.writestr(
                    f"http/{name}.meta.json",
                    json.dumps(
                        {
                            "url": payload["url"],
                            "status_code": payload["status_code"],
                            "content_type": payload["content_type"],
                        },
                        ensure_ascii=False,
                        indent=2,
                    )
                    + "\n",
                )

    return bundle_path


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI parser for support bundle export utility."""
    parser = argparse.ArgumentParser(description="Export runtime support bundle.")
    parser.add_argument("--base-url", default=None, help="Optional running API base URL.")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="Directory where support bundles will be written.",
    )
    parser.add_argument(
        "--release-manifest",
        default=str(DEFAULT_RELEASE_MANIFEST),
        help="Path to an existing release manifest included in the bundle when present.",
    )
    parser.add_argument(
        "--release-scorecard",
        default=str(DEFAULT_RELEASE_SCORECARD),
        help="Path to an existing release harness scorecard included in the bundle when present.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for support bundle export."""
    parser = build_parser()
    args = parser.parse_args(argv)
    bundle_path = export_support_bundle(
        output_dir=Path(args.output_dir),
        base_url=str(args.base_url) if args.base_url else None,
        release_manifest_path=Path(args.release_manifest),
        release_scorecard_path=Path(args.release_scorecard),
    )
    print(f"Support bundle exported to: {bundle_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
