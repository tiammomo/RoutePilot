# Observability Assets

This folder contains importable observability assets for the web/API runtime.

## Files

- `grafana-dashboard.json`
  - Grafana dashboard showing request rate, latency, stream outcomes, SSE events, and readiness.
- `prometheus-alerts.yml`
  - Prometheus alert rules for readiness, 5xx spikes, chat stream failures, and stalled SSE activity.
- `prometheus.yml`
  - Local Prometheus scrape config that targets the backend service at `backend:38000`.
- `grafana-provisioning/`
  - Local Grafana datasource and dashboard provisioning for the bundled dashboard.

## Recommended usage

1. Import [`grafana-dashboard.json`](/D:/projects/shuai/ShuaiTravelAgent/ops/observability/grafana-dashboard.json) into Grafana.
2. Load [`prometheus-alerts.yml`](/D:/projects/shuai/ShuaiTravelAgent/ops/observability/prometheus-alerts.yml) into your Prometheus rules path.
3. Ensure Prometheus scrapes `/api/metrics` from the backend service.

## Local stack

Run the backend, frontend, Prometheus, and Grafana together with:

```bash
docker compose --profile observability up --build
```

Local ports:

- App frontend: `http://localhost:33001`
- App backend: `http://localhost:38000`
- Prometheus: `http://localhost:39090`
- Grafana: `http://localhost:33002`

The bundled Grafana stack auto-provisions:

- datasource `Shuai Prometheus`
- dashboard `ShuaiTravelAgent Overview`

## Metrics used

- `shuai_http_requests_total`
- `shuai_http_request_duration_seconds`
- `shuai_http_in_flight_requests`
- `shuai_chat_stream_requests_total`
- `shuai_rate_limit_rejections_total`
- `shuai_http_timeouts_total`
- `shuai_sse_events_total`
- `shuai_readiness_state`
