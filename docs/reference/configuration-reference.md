# Configuration Reference

## 配置文件总览

当前与运行时相关的核心配置文件有：

- [`config/server_config.yaml`](/D:/projects/shuai/ShuaiTravelAgent/config/server_config.yaml)
  - 服务端口、CORS、中间件、metrics、startup 校验
- [`config/server_config.yaml.example`](/D:/projects/shuai/ShuaiTravelAgent/config/server_config.yaml.example)
  - 服务配置模板
- [`config/llm_config.yaml`](/D:/projects/shuai/ShuaiTravelAgent/config/llm_config.yaml)
  - LLM provider / model 配置
- [`config/llm_config.yaml.example`](/D:/projects/shuai/ShuaiTravelAgent/config/llm_config.yaml.example)
  - LLM 配置模板
- [`.env.example`](/D:/projects/shuai/ShuaiTravelAgent/.env.example)
  - 常用环境变量参考

## 配置来源优先级

[`config/__init__.py`](/D:/projects/shuai/ShuaiTravelAgent/config/__init__.py) 当前采用：

`环境变量 > YAML 配置 > 代码默认值`

这意味着：

1. 本地默认建议复制 `server_config.yaml.example` 和 `llm_config.yaml.example`
2. 在 Docker 或 CI 中，优先通过环境变量覆盖端口、CORS、observability 等项
3. 如果缺失 `server_config.yaml`，系统仍可回退到默认值，但 `/api/ready` 会把真实解析结果写出来

## server_config 关键项

推荐模板：

```yaml
web:
  host: "0.0.0.0"
  port: 38000
  debug: false
  cors_origins:
    - "http://localhost:33001"
    - "http://localhost:38000"

frontend:
  port: 33001

middleware:
  request_timeout_seconds: 30.0
  rate_limit_max_requests: 100
  rate_limit_window_seconds: 60

observability:
  metrics_enabled: true
  metrics_path: "/api/metrics"
  structured_logging: true

startup:
  fail_fast_validation: false
```

### `web`

- `host`
  - Web API 监听地址
- `port`
  - Web API 端口，当前统一为 `38000`
- `debug`
  - 是否以调试方式运行
- `cors_origins`
  - 允许的前端来源列表

### `frontend`

- `port`
  - 前端开发和文档基线端口，当前统一为 `33001`

### `middleware`

- `request_timeout_seconds`
  - 超时中间件阈值
- `rate_limit_max_requests`
  - 滑动窗口内允许的最大请求数
- `rate_limit_window_seconds`
  - 限流窗口大小
  - `/api/health`、`/api/ready`、`/api/live`、metrics 路径默认不参与限流，避免自检和 Prometheus 抓取被误伤

### `observability`

- `metrics_enabled`
  - 是否启用 metrics 端点
- `metrics_path`
  - metrics 自定义路径，默认 `/api/metrics`
  - 当它不是默认值时，应用会同时保留 `/api/metrics`，并额外挂载这个别名路径
- `structured_logging`
  - 是否输出 JSON 结构化日志

### `startup`

- `fail_fast_validation`
  - 当 readiness 校验失败时，应用是否在启动阶段直接抛错退出

## Web / observability 环境变量

这些变量主要由 [`config/__init__.py`](/D:/projects/shuai/ShuaiTravelAgent/config/__init__.py) 解析：

- `SHUAI_WEB_HOST`
- `SHUAI_WEB_PORT`
- `SHUAI_WEB_DEBUG`
- `SHUAI_FRONTEND_PORT`
- `CORS_ORIGINS`
- `SHUAI_CORS_ORIGINS`
- `SHUAI_REQUEST_TIMEOUT_SECONDS`
- `SHUAI_RATE_LIMIT_MAX_REQUESTS`
- `SHUAI_RATE_LIMIT_WINDOW_SECONDS`
- `SHUAI_METRICS_ENABLED`
- `SHUAI_METRICS_PATH`
- `SHUAI_STRUCTURED_LOGGING`
- `SHUAI_FAIL_FAST_STARTUP_VALIDATION`

## Build metadata 环境变量

以下变量主要用于 release / 容器构建时注入：

- `APP_VERSION`
  - 后端暴露在 `/` 与 `/api/health` 的版本号，默认回退到代码内置版本
- `APP_BUILD_SHA`
  - 当前构建对应的 git sha
- `APP_BUILD_CREATED_AT`
  - 当前构建时间戳

对应实现入口：

- [`web/shuai_web/app_meta.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/app_meta.py)
- [`Dockerfile.backend`](/D:/projects/shuai/ShuaiTravelAgent/Dockerfile.backend)
- [`frontend/Dockerfile`](/D:/projects/shuai/ShuaiTravelAgent/frontend/Dockerfile)

### 推荐用途

- 本地联调：优先复制 YAML
- Docker / Compose：优先用 env 覆盖
- CI：由 workflow 复制 example 文件并在必要时用 env 注入

## LLM 相关配置

LLM 配置路径由 [`web/shuai_web/config/runtime.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/config/runtime.py) 统一解析：

- 默认路径：`config/llm_config.yaml`

启动校验时会检查：

1. 文件是否存在
2. 能否被 `ConfigManager` 解析
3. 是否至少有一个 active model

如果这些条件不满足：

- `/api/health` 仍可能返回 `healthy`
- 但 `/api/ready` 会返回 `503`

## 前端环境变量

前端最关键的运行时变量：

- `NEXT_PUBLIC_API_BASE`
  - 浏览器侧 API 根地址，默认 `http://localhost:38000`
- `INTERNAL_API_BASE`
  - Next.js server/runtime rewrite 使用的内部 API 地址
- `NEXT_PUBLIC_APP_NAME`
  - 可选，应用名展示

对应代码路径：

- [`frontend/src/services/api.ts`](/D:/projects/shuai/ShuaiTravelAgent/frontend/src/services/api.ts)
- [`frontend/next.config.js`](/D:/projects/shuai/ShuaiTravelAgent/frontend/next.config.js)

## Agent 运行时配置分组（可灰度启停）

以下变量由 [`runtime_config.py`](/D:/projects/shuai/ShuaiTravelAgent/agent/travel_agent/graph/runtime_config.py) 统一读取。

### 可靠性（Reliability）

- `AGENT_RELIABILITY_CONTROLS_ENABLED`
- `AGENT_TOOL_TIMEOUT_SECONDS`
- `AGENT_TOOL_MAX_RETRIES`
- `AGENT_TOOL_COOLDOWN_SECONDS`
- `AGENT_CIRCUIT_BREAKER_THRESHOLD`
- `AGENT_MAX_EXECUTION_ROUNDS`

### 时效性（Timeliness）

- `AGENT_TIMELINESS_CONTROLS_ENABLED`
- `AGENT_MAX_PLAN_STEPS`
- `AGENT_EARLY_STOP_CONFIDENCE`

### 安全（Security）

- `AGENT_SECURITY_CONTROLS_ENABLED`
- `AGENT_INTENT_STRUCTURED_METHOD`
- `AGENT_STREAM_EVENTS_VERSION`

### 成本（Cost）

- `AGENT_COST_CONTROLS_ENABLED`
- `AGENT_ROUND_MAX_TOOLS`
- `AGENT_ROUND_MAX_ELAPSED_MS`
- `AGENT_ROUND_MAX_TOKENS`
- `AGENT_MAX_PARALLELISM`

### 健康诊断（SLO）

以下变量由 [`chat_service.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/services/chat_service.py) 使用：

- `AGENT_HEALTH_WINDOW_MINUTES`
- `AGENT_SLO_TIMEOUT_RATE_THRESHOLD`
- `AGENT_SLO_FAILURE_RATE_THRESHOLD`
- `AGENT_SLO_FALLBACK_RATE_THRESHOLD`

## 启动校验相关行为

readiness 检查的核心实现：

- [`web/shuai_web/startup_checks.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/startup_checks.py)
- [`web/shuai_web/routes/health.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/routes/health.py)

启动后建议立即检查：

```bash
curl http://localhost:38000/api/health
curl http://localhost:38000/api/ready
curl http://localhost:38000/api/metrics
```

如果 `/api/ready` 返回 `503`，优先检查：

- `config/llm_config.yaml`
- `config/server_config.yaml`
- `data/` 目录权限
- `SHUAI_FAIL_FAST_STARTUP_VALIDATION`
- 启动日志中的 `startup_validation`
