# Backend Maintainer Playbook

这份手册面向维护 `agent/` 与 `web/` 的开发者，目标是帮助你快速定位改动入口、减少回归风险、缩短排障路径。

## 1. 一条请求如何流转

以 `POST /api/chat/stream` 为例：

1. `web/shuai_web/routes/chat.py`
2. `web/shuai_web/services/chat_service.py`
3. `agent/travel_agent/graph/builder.py`
4. `agent/travel_agent/graph/nodes.py`
5. `agent/travel_agent/tools/travel_tools.py` / `agent/travel_agent/tools/travel_api.py`
6. 返回 SSE 事件到前端

排障建议：

1. 先确认 route 是否拿到预期参数（`mode`、`session_id`、`message`）。
2. 再确认 service 层是否正确写入会话、推送 SSE 事件。
3. 最后看 graph/tool 层是否因 timeout、fallback、verify 导致结果偏差。

## 2. 核心模块职责

### Agent 层

- `graph/builder.py`: 组装 LangGraph、执行 `invoke/ainvoke/astream_events`。
- `graph/nodes.py`: 意图识别、策略路由、计划执行、验证、自检。
- `graph/memory_integration.py`: 会话记忆、摘要、用户画像衰减与合并。
- `graph/persistent_checkpointer.py`: checkpoint 持久化与压缩。
- `tools/travel_api.py`: provider 访问、缓存、failover、结果标准化。

### Web API 层

- `routes/*`: 请求校验与 HTTP/SSE 出口。
- `services/*`: 业务流程编排、聚合、错误降级、健康指标。
- `repositories/*` + `storage/*`: 持久化与读写抽象。
- `middleware/*`: 请求日志、限流、超时控制。

## 3. 高风险变更清单

以下变更建议至少补测试 + 回放：

1. `nodes.py` 中的 `execute/verify/self_check` 路由分支。
2. `travel_api.py` 的 provider 优先级、缓存策略、fallback 判定。
3. `chat_service.py` 的 SSE 事件顺序与字段命名。
4. `session` 相关存储格式（影响历史兼容性）。

## 4. 常见故障与定位建议

### 4.1 前端“卡住不出答案”

优先看：

1. 是否收到 `reasoning_start` 与 `answer_start`。
2. 是否最终有 `done` 事件。
3. `onError` 分支是否触发（查看 API 与 server 日志）。

### 4.2 工具结果为空或明显过期

优先看：

1. `execution_stats.steps[*].error_code`
2. `fallback_used` / `is_stale` / `refresh_attempted`
3. provider down 环境变量与配置文件

### 4.3 健康指标异常

优先看：

1. `GET /api/health/tools`
2. `GET /api/health/tools/intents`
3. `chat_service.py` 的 `_record_run_metrics` 与 `_build_health_metrics_snapshot`

## 5. 注释与文档约定

后端代码保持以下约定：

1. 模块、类、函数都应有 docstring。
2. Docstring 首句描述“职责”，不要写模板句（例如 `Execute ...`）。
3. `Args` 与 `Returns` 使用业务语义，不使用泛化占位文本。
4. 复杂分支可加少量内联注释，解释“为什么这样做”。

文档同步建议：

1. API 协议变更：更新 `docs/reference/api-reference.md`。
2. 结构变更：更新 `docs/reference/project-structure.md`。
3. 新增配置：更新 `docs/reference/configuration-reference.md`。

## 6. 提交前最小检查

```bash
python -m compileall -q agent web scripts
python -m pytest tests -q
```

如果改动涉及前端 SSE 渲染，也建议同时执行：

```bash
cd frontend
npm run lint
```

