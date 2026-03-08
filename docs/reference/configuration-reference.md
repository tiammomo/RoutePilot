# Configuration Reference

## 配置文件

- `config/server_config.yaml`: 服务地址、端口、CORS
- `config/llm_config.yaml`: LLM 模型配置（本地私有）
- `config/llm_config.yaml.example`: LLM 示例模板

## 运行时基线

- Python: `3.13.x`（通过 `uv` 管理）
- 虚拟环境路径: 项目根目录 `.venv`

## server_config 关键项

```yaml
web:
  host: "0.0.0.0"
  port: 38000
frontend:
  port: 33001
```

## 前端环境变量

- `NEXT_PUBLIC_API_BASE`: API 根地址，默认 `http://localhost:38000`
- `NEXT_PUBLIC_APP_NAME`: 应用名称（可选）

## 运行时环境变量

- `SHUAI_WEB_PORT`: `run_api.py` 在启动 uvicorn 时注入
- `CORS_ORIGINS`: 逗号分隔，覆盖默认 CORS 白名单
- `AGENT_CHECKPOINT_DB`: Agent checkpoint SQLite 文件路径（默认 `data/langgraph_checkpoints.sqlite3`）
- `AGENT_CHECKPOINT_MAX_PER_THREAD`: 每个 thread 保留的 checkpoint 数（默认 `200`）
- `AGENT_CHECKPOINT_COMPACTION_INTERVAL`: 触发 compaction 的写入间隔（默认 `50`）

## Agent 运行时配置分组（可灰度启停）

以下变量由 [runtime_config.py](/D:/projects/shuai/ShuaiTravelAgent/agent/src/graph/runtime_config.py) 统一读取。

### 可靠性（Reliability）

- `AGENT_RELIABILITY_CONTROLS_ENABLED`：启停可靠性控制（默认 `true`）
- `AGENT_TOOL_TIMEOUT_SECONDS`：工具默认超时秒数（默认 `20`）
- `AGENT_TOOL_MAX_RETRIES`：工具默认重试次数（默认 `1`）
- `AGENT_TOOL_COOLDOWN_SECONDS`：熔断冷却时间秒（默认 `45`）
- `AGENT_CIRCUIT_BREAKER_THRESHOLD`：熔断阈值（默认 `3`）
- `AGENT_MAX_EXECUTION_ROUNDS`：最大执行回合（默认 `8`）

### 时效性（Timeliness）

- `AGENT_TIMELINESS_CONTROLS_ENABLED`：启停 stale 刷新链路（默认 `true`）
- `AGENT_MAX_PLAN_STEPS`：计划最大步数（默认 `6`）
- `AGENT_EARLY_STOP_CONFIDENCE`：高置信直答阈值（默认 `0.9`）

### 安全（Security）

- `AGENT_SECURITY_CONTROLS_ENABLED`：启停参数安全拦截（默认 `true`）
- `AGENT_INTENT_STRUCTURED_METHOD`：意图结构化输出首选方法（默认 `json_schema`）
- `AGENT_STREAM_EVENTS_VERSION`：事件流协议版本（默认 `v1`）

### 成本（Cost）

- `AGENT_COST_CONTROLS_ENABLED`：启停预算控制（默认 `true`）
- `AGENT_ROUND_MAX_TOOLS`：每轮最大工具调用数（默认 `4`）
- `AGENT_ROUND_MAX_ELAPSED_MS`：每轮最大累计耗时毫秒（默认 `15000`）
- `AGENT_ROUND_MAX_TOKENS`：每轮最大估算 token（默认 `2500`）
- `AGENT_MAX_PARALLELISM`：默认并发上限（默认 `2`）

### 健康诊断（SLO）

以下变量由 [chat_service.py](/D:/projects/shuai/ShuaiTravelAgent/web/src/services/chat_service.py) 使用：

- `AGENT_HEALTH_WINDOW_MINUTES`：健康聚合窗口分钟数（默认 `60`）
- `AGENT_SLO_TIMEOUT_RATE_THRESHOLD`：超时率阈值（默认 `0.1`）
- `AGENT_SLO_FAILURE_RATE_THRESHOLD`：失败率阈值（默认 `0.2`）
- `AGENT_SLO_FALLBACK_RATE_THRESHOLD`：fallback 率阈值（默认 `0.5`）
