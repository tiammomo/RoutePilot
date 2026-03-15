# API Reference

所有业务接口默认前缀为 `/api`。

## 1. Health / Ready / Metrics

### `GET /api/health`

用于基础健康检查，通常在本地启动后优先访问。

返回示例：

```json
{
  "status": "healthy",
  "version": "3.3.0",
  "timestamp": "2026-03-09T16:22:01.796033+00:00",
  "build": {
    "version": "3.3.0",
    "sha": "local",
    "created_at": ""
  },
  "services": {
    "api": "healthy",
    "llm": "initialized",
    "sessions": "healthy"
  }
}
```

### `GET /api/ready`

用于真实 readiness 检查，当前会返回 startup validation 结果。

返回规则：

- `200`: `status == "ready"`
- `503`: `status == "starting"` 或 `status == "not_ready"`

返回示例：

```json
{
  "status": "ready",
  "validated_at": "2026-03-15T08:21:03.102313+00:00",
  "checks": {
    "server_config": {
      "name": "server_config",
      "status": "ok",
      "message": "Server configuration resolved.",
      "details": {
        "web_port": 38000,
        "frontend_port": 33001,
        "metrics_enabled": true
      }
    }
  }
}
```

### `GET /api/live`

简单 liveness 探针，通常只返回：

```json
{
  "status": "alive"
}
```

### `GET /api/metrics`

Prometheus 指标出口。

说明：

- 默认路径是 `/api/metrics`
- 如果 `metrics_path` 被改成其他值，应用也会额外挂载一个 metrics 别名路径
- metrics 路径默认不参与限流，避免 Prometheus 抓取被 429 干扰

默认会暴露：

- `shuai_http_requests_total`
- `shuai_http_request_duration_seconds`
- `shuai_http_in_flight_requests`
- `shuai_chat_stream_requests_total`
- `shuai_rate_limit_rejections_total`
- `shuai_http_timeouts_total`
- `shuai_sse_events_total`
- `shuai_readiness_state`

### 其他健康接口

- `GET /api/health/llm`
- `GET /api/health/tools`
- `GET /api/health/tools/intents`

`/api/health/tools` 重点字段：

- `slo`
- `intent_aggregate`
- `window_minutes`
- `diagnostics`

`/api/health/tools/intents` 重点字段：

- `window_minutes`
- `total_requests`
- `intent_aggregate`

`/api/health` 当前还会带：

- `build.version`
- `build.sha`
- `build.created_at`

## 2. Chat

### `POST /api/chat/stream`

主对话接口，返回 `text/event-stream`。

请求体：

```json
{
  "message": "请规划上海周末 2 天轻松游，预算 1500 元以内",
  "session_id": "optional-session-id",
  "mode": "react"
}
```

字段说明：

- `message`: 用户输入
- `session_id`: 可选；为空时后端可创建新会话
- `mode`: `direct | react | plan`

### 推荐请求头

前端当前会主动带：

- `X-Request-ID`
- `X-Trace-ID`

如果你自己写调试脚本，也建议带上这两个头，便于把请求日志、SSE payload 和前端日志串起来。

### 响应头

流式接口当前会返回：

- `Content-Type: text/event-stream`
- `X-Request-ID`
- `X-Trace-ID`
- `Cache-Control: no-cache`
- `Connection: keep-alive`

### SSE 事件类型

- `session_id`
- `reasoning_start`
- `reasoning_chunk`
- `reasoning_end`
- `plan_preview`
- `stage`
- `tool_start`
- `tool_end`
- `answer_start`
- `chunk`
- `metadata`
- `error`
- `done`

当前仓库会额外维护一份稳定的 SSE 契约快照，便于评审字段和顺序变更：

- [sse-contract.snapshot.json](/D:/projects/shuai/ShuaiTravelAgent/docs/reference/sse-contract.snapshot.json)

导出命令：

```bash
python scripts/export_sse_contract_snapshot.py
```

### SSE 推荐事件顺序（典型）

1. `session_id`
2. `reasoning_start`
3. `reasoning_chunk`（可多次）
4. `reasoning_end`
5. `answer_start`
6. `chunk`（可多次）
7. `metadata`
8. `done`

说明：

1. `plan_preview`、`stage`、`tool_start`、`tool_end` 可能穿插在中间
2. 若发生错误，通常会收到 `error`
3. 现在 `session_id / metadata / done` 等事件都可能带 `request_id / trace_id`

### SSE payload 示例

`stage`:

```json
{
  "type": "stage",
  "stage": "query",
  "label": "查询数据",
  "progress": 45,
  "request_id": "req-123",
  "trace_id": "trace-456"
}
```

`chunk`:

```json
{
  "type": "chunk",
  "content": "上午建议先到外滩...",
  "request_id": "req-123",
  "trace_id": "trace-456"
}
```

`metadata`:

```json
{
  "type": "metadata",
  "run_id": "uuid",
  "tools_used": ["query_hotels", "get_weather"],
  "answer_length": 1560,
  "reasoning_length": 820,
  "verification_passed": true,
  "stale_result_count": 0,
  "fallback_steps": 1,
  "request_id": "req-123",
  "trace_id": "trace-456"
}
```

### `plan_preview` 关键字段

- `plan_id`
- `intent`
- `explanation`
- `validation_status`
- `validation_errors`
- `steps`

### `metadata` 关键字段

- `tools_used`
- `answer_length`
- `reasoning_length`
- `plan_id`
- `execution_stats`
- `verification_passed`
- `stale_result_count`
- `fallback_steps`
- `request_id`
- `trace_id`

## 3. Session

### 接口列表

- `POST /api/session/new`
- `GET /api/sessions`
- `DELETE /api/session/{session_id}`
- `PUT /api/session/{session_id}/name`
- `PUT /api/session/{session_id}/model`
- `GET /api/session/{session_id}/model`
- `POST /api/clear/{session_id}`
- `POST /api/clear?session_id=...`

## 4. Model

- `GET /api/models`
- `GET /api/models/{model_id}`

## 5. City Explorer

### 接口列表

- `GET /api/cities`
- `GET /api/cities/{city_id}`
- `GET /api/cities/{city_id}/attractions`
- `GET /api/regions`
- `GET /api/tags`

## 6. Map / Route Preview

### `POST /api/map/route-preview`

用于行程卡中的真实路线预览与距离重排。

## 7. Share

### `POST /api/share-links`

创建可分享短链。

### `GET /api/share-links/{share_id}`

获取分享内容详情。

## 8. API 文档页面

- `GET /docs`
- `GET /rapidoc`
- `GET /redoc`

当前仓库还会维护一份 OpenAPI 快照文件：

- [`openapi.snapshot.json`](/D:/projects/shuai/ShuaiTravelAgent/docs/reference/openapi.snapshot.json)
- [`sse-contract.snapshot.json`](/D:/projects/shuai/ShuaiTravelAgent/docs/reference/sse-contract.snapshot.json)

## 9. 调试建议

### 调 SSE 时优先看这些信号

- Response header 是否为 `text/event-stream`
- 是否有 `X-Request-ID / X-Trace-ID`
- 是否先收到 `session_id`
- 是否最终收到 `done`
- SSE payload 中是否持续带 `request_id / trace_id`

### 调 readiness 时优先看这些信号

- `/api/ready` 返回的是 `200` 还是 `503`
- `checks` 里是哪一项失败
- `/api/metrics` 中 `shuai_readiness_state` 是否为 `1`
- 启动日志里是否有 `startup_validation`
