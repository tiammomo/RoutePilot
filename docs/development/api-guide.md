# API 与事件开发指南

RoutePilot API 是受身份、租户、幂等和版本控制约束的控制平面，不是匿名聊天接口。浏览器必须通过 Next.js 同源 BFF；后端服务可以在受信网络中使用经过验证的 OIDC access token 访问 FastAPI。

## 入口与认证

| 场景 | 入口 | 身份 |
| --- | --- | --- |
| 浏览器 | `/api/v1/*` 同源 BFF | HttpOnly OIDC 会话或显式本地开发会话 |
| 受信服务 | `http://api:38083/api/v1/*` | `Authorization: Bearer <access-token>` |
| 本地调试 | `127.0.0.1:38083` | 仅在 `ROUTEPILOT_V1_DEV_AUTH=1` 和 dev/local 环境允许受信开发身份 |

不要从浏览器保存或发送数据库、Provider、BFF secret。不要把 tenant header 当作生产认证；tenant 必须来自 API 验证后的 Principal。

OpenAPI：`http://127.0.0.1:38083/docs`。OpenAPI 描述字段形状，但本指南定义调用语义。

## 请求约定

- JSON 请求使用 `Content-Type: application/json`；未知字段被拒绝。
- 创建 Run、恢复、取消、Artifact command、知识入库和分享变更需要调用者持有的 `Idempotency-Key`。
- 相同 key 与相同请求可以安全重放；相同 key 与不同请求返回冲突。
- Artifact 生命周期操作使用 `base_version`；分享轮换和撤销使用 `If-Match`。
- 每个响应包含 `X-Request-ID`，错误体中包含可公开的 `trace_id`。
- API 不自动重试有歧义的 mutation。网络中断后应使用原 idempotency key 重放同一请求。

## 最小问答流程

以下示例假定调用者已经从受信身份系统取得 access token，不要把真实 token 写入脚本或 shell history：

```bash
export ROUTEPILOT_API=http://127.0.0.1:38083/api/v1
export ROUTEPILOT_ACCESS_TOKEN='仅放在当前受限终端会话'
```

创建 Trip：

```bash
curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $ROUTEPILOT_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"title":"第一次去京都住哪里方便","locale":"zh-CN","timezone":"Asia/Shanghai"}' \
  "$ROUTEPILOT_API/trips"
```

提交轻量问答 Run，将返回的 `trip_id` 保存为 `TRIP_ID`：

```bash
export TRIP_ID='trip_...'
export IDEMPOTENCY_KEY="ask-$(openssl rand -hex 16)"
curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $ROUTEPILOT_ACCESS_TOKEN" \
  -H 'Content-Type: application/json' \
  -H "Idempotency-Key: $IDEMPOTENCY_KEY" \
  -d '{
    "command": {
      "type": "trip.ask",
      "message": "第一次去京都，住哪里出行方便且晚上安静？",
      "payload": {"title":"京都住宿选择","locale":"zh-CN","destination_hint":"京都"}
    },
    "base_artifact_id": null,
    "base_artifact_version": null
  }' \
  "$ROUTEPILOT_API/trips/$TRIP_ID/runs"
```

`trip.ask` 只产生 `TravelAnswer`，不会替换当前正式 `TripSnapshot`。`trip.plan` 需要 Web 使用的结构化 `trip_request`；以 OpenAPI 和生成的契约为准，不要从自然语言猜测日期、人数或预算。

## Run 状态与 SSE 恢复

创建 Run 返回 `202` 和当前快照。使用返回的 `run_id`：

```bash
curl --no-buffer --fail-with-body \
  -H "Authorization: Bearer $ROUTEPILOT_ACCESS_TOKEN" \
  "$ROUTEPILOT_API/runs/$RUN_ID/events?after_seq=0"
```

客户端必须记录最后一个事件 `seq`。断线后使用 `Last-Event-ID` 或 `after_seq` 恢复，只读取缺失事件，不重新创建 Run。

Run、A2A Task 和 Artifact version 是三个独立生命周期。收到 `run.completed` 也应读取结果 Artifact 引用，不能根据 Agent 活动文本推断正式发布状态。

## 等待输入与恢复

当 Run 进入 `waiting_input` 时，读取快照中的 `pending_input`：

- 使用原样的 `request_id`；
- 提交当前 `control_version`；
- 只提交服务端列出的字段；
- 在 `expires_at` 前完成。

```json
{
  "expected_control_version": 3,
  "request_id": "input_...",
  "values": {
    "destination": "北京",
    "confirmed": true
  }
}
```

恢复请求同样需要新的、可稳定重放的 `Idempotency-Key`。

## Artifact 生命周期

- `PATCH /artifacts/{artifact_id}` 创建新候选版本，不修改旧版本；
- `artifact.select`、`artifact.publish`、`artifact.revoke` 通过 commands 端点执行；
- command 必须针对最新版本并携带 `base_version`；
- 冲突返回 `409 VERSION_CONFLICT` 和 `current_version`，调用者应刷新而不是覆盖。

## 错误处理

公开错误结构：

```json
{
  "detail": {
    "code": "VERSION_CONFLICT",
    "message": "The resource changed; refresh and retry.",
    "retryable": true,
    "trace_id": "req_...",
    "current_version": 7
  }
}
```

调用方只依赖 `code`、`retryable` 和显式版本字段。服务端不会返回 traceback、Provider 原始错误、prompt、reasoning 或凭据。排障时记录 `trace_id`、HTTP 状态、资源 ID 和发生时间，不记录 token 或完整私人请求体。

## 浏览器 BFF 的额外边界

同源 mutation 需要 BFF 的 CSRF token 和合法 Origin。Web 客户端已经封装在 `apps/web/src/shared/api/client.ts`。业务组件不得自行构造 API origin、Authorization 或租户 header，也不得添加任意代理路径。

A2A JSON-RPC、知识管理和 Provider metadata 的完整路由可在 OpenAPI 中查看。扩展 Agent 时参阅 [Agent 与 A2A 扩展指南](agent-extension.md)。
