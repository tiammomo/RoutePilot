# System Architecture

## 三层结构

1. Frontend (`frontend`)
2. Web API (`web`)
3. Agent (`agent`)

## 调用链路

```text
Browser -> FastAPI (/api/chat/stream) -> ChatService -> LangGraph Agent -> Tools/LLM
```

## 关键设计点

- Chat 采用 SSE 实时流式输出
- Session 与模型切换通过 Web 层统一管理
- Agent 通过 `graph` + `tools` 解耦推理与外部数据访问
- `plan` 模式先输出 `plan_preview`（可审计执行计划），再进入执行阶段
- LangGraph 执行链按 `session_id -> thread_id` 注入线程配置，便于追踪与恢复
- Checkpoint 使用本地 SQLite 持久化，支持进程重启后的会话恢复
- Tool 执行节点支持超时、重试和结构化错误码（`TOOL_TIMEOUT` / `TOOL_EXECUTION_ERROR`）
- 会话层的 `delete/clear` 会同步清理 Agent memory，避免“会话已删但记忆残留”

## SSE 关键字段

- `plan_preview`：`validation_status`、`validation_errors`
- `metadata`：`verification_passed`、`stale_result_count`、`fallback_steps`、`tools_used`

## 健康诊断接口

- `GET /api/health/tools`：SLO 状态 + intent 聚合
- `GET /api/health/tools/intents`：意图维度窗口统计（`total_requests` + `intent_aggregate`）

## 故障回放

- 回放脚本：`python scripts/agent_replay.py --session-id <id> --db data/langgraph_checkpoints.sqlite3`
- 产物：`docs/benchmarks/agent_replay_<session>_<timestamp>.json/.md`

## 当前端口

- Frontend: `33001`
- Web API: `38000`
