"""Run offline and optional live diagnostics for runtime health, contracts, and data assets."""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import yaml

try:
    from scripts.runtime_data_utils import DEFAULT_BACKUP_DIR, ROOT, discover_runtime_files
except ImportError:  # pragma: no cover - script execution path
    from runtime_data_utils import DEFAULT_BACKUP_DIR, ROOT, discover_runtime_files


DEFAULT_OPENAPI_SNAPSHOT = ROOT / "docs" / "reference" / "openapi.snapshot.json"
DEFAULT_SSE_SNAPSHOT = ROOT / "docs" / "reference" / "sse-contract.snapshot.json"


def utc_now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _build_check(name: str, status: str, message: str, **details: Any) -> dict[str, Any]:
    """Build one normalized diagnostic check record."""
    return {
        "name": name,
        "status": status,
        "message": message,
        "details": details,
    }


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    """Load one YAML mapping from disk and reject non-object roots."""
    payload = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(payload, dict):
        raise ValueError("expected a mapping at YAML root")
    return payload


def _check_server_config(path: Path) -> dict[str, Any]:
    """Inspect server config presence and top-level runtime fields."""
    if not path.exists():
        return _build_check(
            "server_config",
            "ok",
            "Server config file is absent; runtime will fall back to built-in defaults.",
            path=str(path),
            exists=False,
            fallback_defaults=True,
        )

    try:
        payload = _load_yaml_mapping(path)
    except Exception as exc:
        return _build_check(
            "server_config",
            "not_ready",
            f"Server config cannot be parsed: {exc}",
            path=str(path),
            exists=True,
        )

    web = payload.get("web") if isinstance(payload.get("web"), dict) else {}
    frontend = payload.get("frontend") if isinstance(payload.get("frontend"), dict) else {}
    observability = payload.get("observability") if isinstance(payload.get("observability"), dict) else {}
    return _build_check(
        "server_config",
        "ok",
        "Server config parsed successfully.",
        path=str(path),
        exists=True,
        web_host=str(web.get("host", "0.0.0.0")),
        web_port=int(web.get("port", 38000) or 38000),
        frontend_port=int(frontend.get("port", 33001) or 33001),
        metrics_enabled=bool(observability.get("metrics_enabled", True)),
        metrics_path=str(observability.get("metrics_path", "/api/metrics")),
    )


def _check_llm_config(path: Path) -> dict[str, Any]:
    """Inspect llm config structure and minimum active-model readiness."""
    if not path.exists():
        return _build_check(
            "llm_config",
            "not_ready",
            "LLM config file is missing.",
            path=str(path),
            exists=False,
        )

    try:
        payload = _load_yaml_mapping(path)
    except Exception as exc:
        return _build_check(
            "llm_config",
            "not_ready",
            f"LLM config cannot be parsed: {exc}",
            path=str(path),
            exists=True,
        )

    models = payload.get("models")
    models = models if isinstance(models, dict) else {}
    model_ids = [str(model_id) for model_id in models.keys()]
    default_model = str(payload.get("default_model") or "").strip()

    if not model_ids:
        return _build_check(
            "llm_config",
            "not_ready",
            "LLM config does not define any models.",
            path=str(path),
            exists=True,
            default_model=default_model,
            active_models=[],
        )

    if default_model and default_model not in models:
        return _build_check(
            "llm_config",
            "not_ready",
            "LLM config default_model does not exist in models.",
            path=str(path),
            exists=True,
            default_model=default_model,
            active_models=model_ids,
        )

    return _build_check(
        "llm_config",
        "ok",
        "LLM config parsed successfully.",
        path=str(path),
        exists=True,
        default_model=default_model or model_ids[0],
        active_models=model_ids,
        models_count=len(model_ids),
    )


def _check_data_dir(path: Path) -> dict[str, Any]:
    """Verify runtime data directory is writable."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=path, prefix=".doctor-", delete=True):
            pass
        return _build_check("data_dir", "ok", "Runtime data directory is writable.", path=str(path))
    except Exception as exc:
        return _build_check(
            "data_dir",
            "not_ready",
            f"Runtime data directory is not writable: {exc}",
            path=str(path),
        )


def _check_runtime_files(project_root: Path) -> dict[str, Any]:
    """Summarize known runtime files currently present under the project root."""
    files = discover_runtime_files(project_root)
    return _build_check(
        "runtime_files",
        "ok",
        f"Discovered {len(files)} runtime file(s).",
        files=[
            {
                "key": item["key"],
                "relative_path": item["relative_path"],
                "size_bytes": item["size_bytes"],
            }
            for item in files
        ],
    )


def _check_backups(path: Path) -> dict[str, Any]:
    """Inspect runtime backup archive inventory."""
    try:
        path.mkdir(parents=True, exist_ok=True)
        archives = sorted(path.glob("runtime_backup_*.zip"))
    except Exception as exc:
        return _build_check("backups", "degraded", f"Backup directory is not accessible: {exc}", path=str(path))

    latest = archives[-1] if archives else None
    return _build_check(
        "backups",
        "ok",
        "Runtime backup inventory loaded." if archives else "No runtime backup archives found yet.",
        path=str(path),
        archive_count=len(archives),
        latest_archive=str(latest) if latest else None,
    )


def _check_json_snapshot(name: str, path: Path) -> dict[str, Any]:
    """Validate one JSON contract snapshot file."""
    if not path.exists():
        return _build_check(name, "degraded", "Snapshot file is missing.", path=str(path), exists=False)

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return _build_check(
            name,
            "degraded",
            f"Snapshot file is not valid JSON: {exc}",
            path=str(path),
            exists=True,
        )

    keys = sorted(payload.keys()) if isinstance(payload, dict) else []
    return _build_check(
        name,
        "ok",
        "Snapshot file loaded.",
        path=str(path),
        exists=True,
        root_type=type(payload).__name__,
        top_level_keys=keys[:12],
    )


def _check_contract_snapshots(openapi_snapshot: Path, sse_snapshot: Path) -> dict[str, Any]:
    """Validate OpenAPI and SSE contract snapshot files."""
    openapi_check = _check_json_snapshot("openapi_snapshot", openapi_snapshot)
    sse_check = _check_json_snapshot("sse_snapshot", sse_snapshot)
    overall_status = "ok" if all(item["status"] == "ok" for item in (openapi_check, sse_check)) else "degraded"
    return _build_check(
        "contract_snapshots",
        overall_status,
        "Contract snapshots validated." if overall_status == "ok" else "One or more contract snapshots need attention.",
        snapshots={
            "openapi": openapi_check,
            "sse": sse_check,
        },
    )


def _probe_http_endpoints(base_url: str, *, expect_metrics: bool) -> dict[str, Any]:
    """Optionally probe live HTTP endpoints for health, readiness, and metrics."""
    checks: dict[str, dict[str, Any]] = {}
    statuses: list[str] = []
    urls = {
        "health": f"{base_url.rstrip('/')}/api/health",
        "ready": f"{base_url.rstrip('/')}/api/ready",
        "metrics": f"{base_url.rstrip('/')}/api/metrics",
    }

    with httpx.Client(timeout=3.0) as client:
        for name, url in urls.items():
            if name == "metrics" and not expect_metrics:
                checks[name] = _build_check(name, "ok", "Metrics probe skipped because metrics are disabled by config.", url=url)
                statuses.append("ok")
                continue
            try:
                response = client.get(url)
                if name == "metrics":
                    ok = response.status_code == 200 and "text/plain" in response.headers.get("content-type", "")
                elif name == "ready":
                    ok = response.status_code == 200
                else:
                    ok = response.status_code < 500
                status = "ok" if ok else "degraded"
                checks[name] = _build_check(
                    name,
                    status,
                    f"HTTP {response.status_code}",
                    url=url,
                    status_code=response.status_code,
                    content_type=response.headers.get("content-type", ""),
                )
            except Exception as exc:
                checks[name] = _build_check(name, "degraded", f"Probe failed: {exc}", url=url)
            statuses.append(checks[name]["status"])

    overall_status = "ok" if all(status == "ok" for status in statuses) else "degraded"
    return _build_check(
        "http_probe",
        overall_status,
        "Live HTTP probes passed." if overall_status == "ok" else "One or more live HTTP probes failed.",
        base_url=base_url,
        endpoints=checks,
    )


def run_runtime_doctor(
    *,
    project_root: Path = ROOT,
    base_url: str | None = None,
    backup_dir: Path = DEFAULT_BACKUP_DIR,
    openapi_snapshot: Path = DEFAULT_OPENAPI_SNAPSHOT,
    sse_snapshot: Path = DEFAULT_SSE_SNAPSHOT,
) -> dict[str, Any]:
    """Build an aggregated runtime diagnostics report."""
    project_root = Path(project_root)
    server_config_path = project_root / "config" / "server_config.yaml"
    llm_config_path = project_root / "config" / "llm_config.yaml"
    data_dir = project_root / "data"

    checks: dict[str, dict[str, Any]] = {
        "server_config": _check_server_config(server_config_path),
        "llm_config": _check_llm_config(llm_config_path),
        "data_dir": _check_data_dir(data_dir),
        "runtime_files": _check_runtime_files(project_root),
        "backups": _check_backups(Path(backup_dir)),
        "contract_snapshots": _check_contract_snapshots(Path(openapi_snapshot), Path(sse_snapshot)),
    }

    server_metrics_enabled = True
    server_details = checks["server_config"].get("details", {})
    if isinstance(server_details, dict):
        server_metrics_enabled = bool(server_details.get("metrics_enabled", True))

    if base_url:
        checks["http_probe"] = _probe_http_endpoints(base_url, expect_metrics=server_metrics_enabled)

    required_checks = {"llm_config", "data_dir"}
    required_failed = any(checks[name]["status"] == "not_ready" for name in required_checks)
    degraded = any(item["status"] == "degraded" for item in checks.values())
    ok_checks = sum(1 for item in checks.values() if item["status"] == "ok")

    if required_failed:
        status = "not_ready"
    elif degraded:
        status = "degraded"
    else:
        status = "ok"

    return {
        "status": status,
        "checked_at": utc_now_iso(),
        "project_root": str(project_root),
        "summary": {
            "checks_total": len(checks),
            "checks_ok": ok_checks,
            "checks_degraded": sum(1 for item in checks.values() if item["status"] == "degraded"),
            "checks_not_ready": sum(1 for item in checks.values() if item["status"] == "not_ready"),
        },
        "checks": checks,
    }


def render_text_report(report: dict[str, Any]) -> str:
    """Render doctor report as human-readable text."""
    lines = [
        f"Runtime doctor status: {report.get('status')}",
        f"Checked at: {report.get('checked_at')}",
        f"Project root: {report.get('project_root')}",
        "",
    ]
    for name, check in report.get("checks", {}).items():
        lines.append(f"[{check.get('status', 'unknown').upper()}] {name}: {check.get('message', '')}")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    """Construct CLI parser for runtime diagnostics utility."""
    parser = argparse.ArgumentParser(description="Run runtime diagnostics for ShuaiTravelAgent.")
    parser.add_argument(
        "--base-url",
        default=None,
        help="Optional running API base URL, for example http://localhost:38000.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print full JSON report instead of human-readable text.",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with non-zero status when any check is degraded or not ready.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint for runtime diagnostics."""
    parser = build_parser()
    args = parser.parse_args(argv)
    report = run_runtime_doctor(base_url=args.base_url)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render_text_report(report))
    if args.strict and report.get("status") != "ok":
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
