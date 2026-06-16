# Observability Assets

This folder contains importable observability assets for the web/API runtime.

## Files

- `grafana-dashboard.json`
  - Grafana dashboard showing request rate, latency, stream outcomes, SSE events, and readiness.
- `prometheus-alerts.yml`
  - Prometheus alert rules for readiness, 5xx spikes, chat stream failures, and stalled SSE activity.
- `prometheus.yml`
  - Local Prometheus scrape config that targets the backend service at `backend:38083`.
- `grafana-provisioning/`
  - Local Grafana datasource and dashboard provisioning for the bundled dashboard.

## Recommended usage

1. Import [`grafana-dashboard.json`](/D:/moyuan/moyuan-travel-agent/ops/observability/grafana-dashboard.json) into Grafana.
2. Load [`prometheus-alerts.yml`](/D:/moyuan/moyuan-travel-agent/ops/observability/prometheus-alerts.yml) into your Prometheus rules path.
3. Ensure Prometheus scrapes `/api/metrics` from the backend service.

## Local stack

Run the backend, frontend, Prometheus, and Grafana together with:

```bash
docker compose --profile observability up --build
```

Local ports:

- App frontend: `http://localhost:33003`
- App backend: `http://localhost:38083`
- Prometheus: `http://localhost:39090`
- Grafana: `http://localhost:33002`

The bundled Grafana stack auto-provisions:

- datasource `moyuan-travel-agent Prometheus`
- dashboard `moyuan-travel-agent Overview`

## Metrics used

- `moyuan_http_requests_total`
- `moyuan_http_request_duration_seconds`
- `moyuan_http_in_flight_requests`
- `moyuan_chat_stream_requests_total`
- `moyuan_rate_limit_rejections_total`
- `moyuan_http_timeouts_total`
- `moyuan_sse_events_total`
- `moyuan_readiness_state`
