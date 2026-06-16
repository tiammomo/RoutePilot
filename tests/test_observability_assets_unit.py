"""Unit tests for observability asset fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import yaml


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_grafana_dashboard_asset_is_valid_json():
    dashboard_path = PROJECT_ROOT / "extend" / "observability" / "grafana-dashboard.json"
    payload = json.loads(dashboard_path.read_text(encoding="utf-8"))

    assert payload["title"] == "moyuan-travel-agent Overview"
    assert len(payload.get("panels", [])) >= 6
    expressions = [target["expr"] for panel in payload["panels"] for target in panel.get("targets", [])]
    assert any("moyuan_http_requests_total" in expr for expr in expressions)
    assert any("moyuan_chat_stream_requests_total" in expr for expr in expressions)
    assert any("moyuan_rate_limit_rejections_total" in expr for expr in expressions)
    assert any("moyuan_http_timeouts_total" in expr for expr in expressions)


def test_prometheus_alert_asset_is_valid_yaml():
    alerts_path = PROJECT_ROOT / "extend" / "observability" / "prometheus-alerts.yml"
    payload = yaml.safe_load(alerts_path.read_text(encoding="utf-8"))

    groups = payload.get("groups", [])
    assert len(groups) == 1
    rule_names = [rule["alert"] for rule in groups[0].get("rules", [])]
    assert "MoyuanReadinessDown" in rule_names
    assert "MoyuanChatStreamFailures" in rule_names
    assert "MoyuanHttpTimeoutSpike" in rule_names


def test_local_prometheus_scrape_config_is_valid_yaml():
    config_path = PROJECT_ROOT / "extend" / "observability" / "prometheus.yml"
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    scrape_configs = payload.get("scrape_configs", [])
    assert len(scrape_configs) == 1
    assert scrape_configs[0]["job_name"] == "moyuan-backend"
    assert scrape_configs[0]["metrics_path"] == "/api/metrics"
    assert scrape_configs[0]["static_configs"][0]["targets"] == ["backend:38083"]
