# API Reference

所有业务接口默认前缀为 `/api`。

## Health

- `GET /api/health`
- `GET /api/health/llm`
- `GET /api/health/tools`
- `GET /api/health/tools/intents`
- `GET /api/ready`
- `GET /api/live`

## Chat

- `POST /api/chat/stream`

请求体：

```json
{
  "message": "推荐一个周末短途城市",
  "session_id": "optional",
  "mode": "direct|react|plan"
}
```

SSE 事件（`type`）：

- `session_id`
- `reasoning_start`
- `reasoning_chunk`
- `reasoning_end`
- `plan_preview`（仅 `mode=plan`）
- `tool_start`
- `tool_end`
- `answer_start`
- `chunk`
- `metadata`
- `error`
- `done`

`plan_preview` 关键字段：
- `plan_id`
- `intent`
- `explanation`
- `validation_status`（`pass|warn|fail`）
- `validation_errors`（`[{step_id, tool, code, message}]`）
- `steps`（含 `step_id` / `depends_on` / `tool` / `params`）

`metadata` 关键字段：
- `tools_used`
- `answer_length`
- `reasoning_length`
- `plan_id`
- `execution_stats`
- `verification_passed`
- `stale_result_count`
- `fallback_steps`

高风险问答约束（`budget/价格/政策/签证/退改`）：
- 最终答案正文会强制包含证据段，显式给出 `source` 与 `fetched_at`。

`GET /api/health/tools` 关键字段：
- `slo`（`status/timeout_rate/failure_rate/fallback_rate/thresholds/total_requests`）
- `intent_aggregate`（`{intent: {total, timeout_rate, failure_rate, fallback_rate}}`）
- `window_minutes`

`GET /api/health/tools/intents` 关键字段：
- `window_minutes`
- `total_requests`
- `intent_aggregate`（按 intent 的 `total/timeout_rate/failure_rate/fallback_rate`）

## Session

- `POST /api/session/new`
- `GET /api/sessions`
- `DELETE /api/session/{session_id}`
- `PUT /api/session/{session_id}/name`
- `PUT /api/session/{session_id}/model`
- `GET /api/session/{session_id}/model`
- `POST /api/clear/{session_id}`
- `POST /api/clear?session_id=...`

## Model

- `GET /api/models`
- `GET /api/models/{model_id}`

## City

- `GET /api/cities`
- `GET /api/cities/{city_id}`
- `GET /api/cities/{city_id}/attractions`
- `GET /api/regions`
- `GET /api/tags`

## API 文档页面

- `GET /docs`
- `GET /rapidoc`
- `GET /redoc`
