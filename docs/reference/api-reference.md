# API Reference

所有业务接口默认前缀为 `/api`。

## 1. Health

### `GET /api/health`

用于基础健康检查，通常在本地启动后优先访问。

返回示例：

```json
{
  "status": "healthy",
  "version": "3.3.0",
  "timestamp": "2026-03-09T16:22:01.796033+00:00",
  "services": {
    "api": "healthy",
    "llm": "initialized",
    "sessions": "healthy"
  }
}
```

### 其他健康接口

- `GET /api/health/llm`
- `GET /api/health/tools`
- `GET /api/health/tools/intents`
- `GET /api/ready`
- `GET /api/live`

`/api/health/tools` 重点字段：

- `slo`
- `intent_aggregate`
- `window_minutes`
- `diagnostics`

`/api/health/tools/intents` 重点字段：

- `window_minutes`
- `total_requests`
- `intent_aggregate`

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

1. `plan_preview`、`stage`、`tool_start`、`tool_end` 可能穿插在中间。
2. 若发生错误，通常会收到 `error` 后再收到 `done`。

### SSE payload 示例

`stage`:

```json
{
  "type": "stage",
  "stage": "query",
  "label": "查询数据",
  "progress": 45
}
```

`tool_start`:

```json
{
  "type": "tool_start",
  "tool": "query_hotels"
}
```

`chunk`:

```json
{
  "type": "chunk",
  "content": "上午建议先到外滩..."
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
  "fallback_steps": 1
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

### 高风险问答约束

对于预算、价格、政策、签证、退改等高风险意图：

- 最终答案会尽量附上证据来源
- 会显式给出 `source` 和 `fetched_at`
- 若验证不足，前端会展示可信度与风险提示

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

### 常见用途

- 新建会话
- 获取历史会话列表
- 会话重命名
- 切换模型
- 清空当前会话消息
- 删除会话

## 4. Model

- `GET /api/models`
- `GET /api/models/{model_id}`

用于前端模型下拉与会话级模型切换。

## 5. City Explorer

### 接口列表

- `GET /api/cities`
- `GET /api/cities/{city_id}`
- `GET /api/cities/{city_id}/attractions`
- `GET /api/regions`
- `GET /api/tags`

### `GET /api/cities`

支持参数：

- `region`: 按地区筛选
- `tags`: 逗号分隔标签，如 `亲子,美食`

返回示例：

```json
{
  "cities": [
    {
      "id": "shanghai",
      "name": "上海",
      "region": "华东",
      "tags": ["现代都市", "购物", "夜景", "美食", "亲子"]
    }
  ]
}
```

### `GET /api/cities/{city_id}`

返回完整城市详情：

- `description`
- `attractions`
- `avg_budget_per_day`
- `best_seasons`

## 6. Map / Route Preview

### `POST /api/map/route-preview`

用于行程卡中的真实路线预览与距离重排。

请求体：

```json
{
  "spots": ["外滩", "陆家嘴", "南京东路步行街"],
  "city": "上海",
  "provider": "amap"
}
```

返回字段：

- `provider`
- `points`
- `distance_m`
- `duration_s`
- `static_map_url`
- `route_polyline`

## 7. Share

### `POST /api/share-links`

创建可分享短链。

请求体：

```json
{
  "title": "上海周末 2 天轻松游",
  "content": "...最终方案内容..."
}
```

返回字段：

- `success`
- `share_id`
- `share_url`

### `GET /api/share-links/{share_id}`

获取分享内容详情。

## 8. API 文档页面

- `GET /docs`
- `GET /rapidoc`
- `GET /redoc`

## 9. 调试建议

### 调 SSE 时优先看这些信号

- Response header 是否为 `text/event-stream`
- 是否先收到 `session_id`
- 是否有 `answer_start`
- 是否最终收到 `done`

### 调城市探索时优先看这些接口

- `/api/regions`
- `/api/tags`
- `/api/cities`
- `/api/cities/{city_id}`

### 调分享与地图时优先看这些接口

- `/api/share-links`
- `/api/map/route-preview`
