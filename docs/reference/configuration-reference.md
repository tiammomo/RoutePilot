# Configuration Reference

## 配置文件总览

当前与运行时相关的核心配置文件有：

- [`backend/config/server_config.yaml`](../../backend/config/server_config.yaml)
  - 服务端口、CORS、中间件、metrics、startup 校验
- [`backend/config/server_config.yaml.example`](../../backend/config/server_config.yaml.example)
  - 服务配置模板
- [`backend/config/llm_config.yaml`](../../backend/config/llm_config.yaml)
  - LLM provider / model 配置
- [`backend/config/llm_config.yaml.example`](../../backend/config/llm_config.yaml.example)
  - LLM 配置模板
- [`.env.example`](../../.env.example)
  - 常用环境变量参考

## 配置来源优先级

[`backend/config/__init__.py`](../../backend/config/__init__.py) 当前采用：

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
  port: 38083
  debug: false
  cors_origins:
    - "http://localhost:33003"
    - "http://localhost:38083"

frontend:
  port: 33003

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

database:
  backend: "file"
  postgres_dsn: ""
  pool_min: 1
  pool_max: 5
```

### `web`

- `host`
  - Backend API 监听地址
- `port`
  - Backend API 端口，当前统一为 `38083`
- `debug`
  - 是否以调试方式运行
- `cors_origins`
  - 允许的前端来源列表

### `frontend`

- `port`
  - 前端开发和文档基线端口，当前统一为 `33003`

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

### `database`

- `backend`
  - 持久化后端选择，当前支持 `file` 和 `postgres`
- `postgres_dsn`
  - PostgreSQL 连接串；切到 `postgres` backend 时必须提供
- `pool_min`
  - 数据库连接池最小常驻连接数
- `pool_max`
  - 数据库连接池上限

## Backend / observability 环境变量

这些变量主要由 [`backend/config/__init__.py`](../../backend/config/__init__.py) 解析：

- `MOYUAN_WEB_HOST`
- `MOYUAN_WEB_PORT`
- `MOYUAN_WEB_DEBUG`
- `MOYUAN_FRONTEND_PORT`
- `CORS_ORIGINS`
- `MOYUAN_CORS_ORIGINS`
- `MOYUAN_REQUEST_TIMEOUT_SECONDS`
- `MOYUAN_RATE_LIMIT_MAX_REQUESTS`
- `MOYUAN_RATE_LIMIT_WINDOW_SECONDS`
- `MOYUAN_METRICS_ENABLED`
- `MOYUAN_METRICS_PATH`
- `MOYUAN_STRUCTURED_LOGGING`
- `MOYUAN_DB_BACKEND`
- `MOYUAN_POSTGRES_DSN`
- `MOYUAN_DB_POOL_MIN`
- `MOYUAN_DB_POOL_MAX`
- `MOYUAN_FAIL_FAST_STARTUP_VALIDATION`
- `AGENT_CHECKPOINT_BACKEND`
- `AGENT_CHECKPOINT_DB`
- `AGENT_CHECKPOINT_DSN`
- `AGENT_CHECKPOINT_MAX_PER_THREAD`
- `AGENT_CHECKPOINT_COMPACTION_INTERVAL`

## Build metadata 环境变量

以下变量主要用于 release / 容器构建时注入：

- `APP_VERSION`
  - 后端暴露在 `/` 与 `/api/health` 的版本号，默认回退到代码内置版本
- `APP_BUILD_SHA`
  - 当前构建对应的 git sha
- `APP_BUILD_CREATED_AT`
  - 当前构建时间戳

对应实现入口：

- [`backend/moyuan_web/app_meta.py`](../../backend/moyuan_web/app_meta.py)
- [`deploy/docker/backend.Dockerfile`](../../deploy/docker/backend.Dockerfile)
- [`deploy/docker/frontend.Dockerfile`](../../deploy/docker/frontend.Dockerfile)

### 推荐用途

- 本地联调：优先复制 YAML
- Docker / Compose：优先用 env 覆盖
- CI：由 workflow 复制 example 文件并在必要时用 env 注入

## 数据库 migration / backfill

当前 PostgreSQL 基线已经有最小骨架：

- `deploy/migrations/alembic.ini`
- `deploy/migrations/`
- `scripts/runtime_backfill_postgres.py`

常用命令：

```bash
export MOYUAN_POSTGRES_DSN='postgresql://user:password@localhost:5432/moyuan'
alembic -c deploy/migrations/alembic.ini upgrade head
python scripts/runtime_backfill_postgres.py
```

如果只是本地验证 repository 骨架，也可以临时传入 SQLite URL：

```bash
python scripts/runtime_backfill_postgres.py --database-url 'sqlite+pysqlite:///./tmp-backfill.db'
```

当前 backfill 默认会尝试导入：

- `data/sessions/sessions.json`
- `data/share_links.json`
- `data/agent_memory.json`

## Checkpoint backend 配置

checkpoint backend 现在统一由 [`runtime_sources.py`](../../agent/travel_agent/runtime_sources.py) 解析和创建，默认仍是 SQLite 文件：

- `AGENT_CHECKPOINT_BACKEND`
  - 当前支持 `sqlite` 和 `postgres`
  - 默认值为 `sqlite`
- `AGENT_CHECKPOINT_DB`
  - `sqlite` backend 使用的 checkpoint 文件路径
  - 默认值为 `data/langgraph_checkpoints.sqlite3`
- `AGENT_CHECKPOINT_DSN`
  - `postgres` backend 专用 DSN
  - 如果未提供，会回退读取 `MOYUAN_POSTGRES_DSN` / `database.postgres_dsn`
- `AGENT_CHECKPOINT_MAX_PER_THREAD`
  - 每个 `thread_id + checkpoint_ns` 保留的最大 checkpoint 数
- `AGENT_CHECKPOINT_COMPACTION_INTERVAL`
  - 触发一次 compaction 检查前允许的写入次数

`postgres` backend 当前对应专用表：

- `agent_checkpoints`
- `agent_checkpoint_blobs`
- `agent_checkpoint_writes`
- `agent_checkpoint_meta`

运维脚本现在也复用这套 factory：

```bash
python scripts/dev.py agent-replay --replay-session-id <session_id> --replay-db data/langgraph_checkpoints.sqlite3
python scripts/dev.py agent-replay --replay-session-id <session_id> --replay-checkpoint-backend postgres --replay-db 'postgresql://user:password@localhost:5432/moyuan'
python scripts/dev.py runtime-prune --prune-vacuum-checkpoints --prune-checkpoint-backend postgres --prune-checkpoint-db 'postgresql://user:password@localhost:5432/moyuan'
```

行为说明：

- `agent_replay.py`
  - `--db` 现在既可传 SQLite 文件路径，也可传 PostgreSQL DSN
  - 如果未显式传 `--checkpoint-backend`，会优先从 `--db` 推断 backend，再回退到环境变量
- `runtime_prune.py`
  - `--vacuum-checkpoints` 现在表示“执行 checkpoint backend maintenance”
  - `sqlite` backend 下会先做 compaction，再执行 SQLite `VACUUM`
  - `postgres` backend 下会触发同一套 checkpointer compaction sweep，不再假定只能操作本地 SQLite 文件
- `runtime_backup.py` / `runtime_restore.py`
  - backup manifest 会写入 `checkpoint_runtime` 和 `restore_instructions`
  - `postgres` backend 只记录 redacted checkpoint target，不会把外部 checkpoint 表直接打进 zip

## LLM 相关配置

LLM 配置路径由 [`backend/moyuan_web/config/runtime.py`](../../backend/moyuan_web/config/runtime.py) 统一解析：

- 默认路径：`backend/config/llm_config.yaml`
- 解析实现固定收口到 [`backend/moyuan_web/config/config_manager.py`](../../backend/moyuan_web/config/config_manager.py)，不再保留额外 delegate/fallback 路径

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
  - 浏览器侧 API 根地址，默认 `http://localhost:38083`
- `INTERNAL_API_BASE`
  - Next.js server/runtime rewrite 使用的内部 API 地址
- `NEXT_PUBLIC_APP_NAME`
  - 可选，应用名展示

对应代码路径：

- [`frontend/src/services/api/chatClient.ts`](../../frontend/src/services/api/chatClient.ts)
- [`frontend/src/services/api/chatStreamParser.ts`](../../frontend/src/services/api/chatStreamParser.ts)
- [`frontend/next.config.js`](../../frontend/next.config.js)

## Agent 运行时配置分组（可灰度启停）

以下变量由 [`runtime_config.py`](../../agent/travel_agent/graph/runtime_config.py) 统一读取。

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

以下变量由 [`chat_service.py`](../../backend/moyuan_web/services/chat_service.py) 使用：

- `AGENT_HEALTH_WINDOW_MINUTES`
- `AGENT_SLO_TIMEOUT_RATE_THRESHOLD`
- `AGENT_SLO_FAILURE_RATE_THRESHOLD`
- `AGENT_SLO_FALLBACK_RATE_THRESHOLD`

## 启动校验相关行为

readiness 检查的核心实现：

- [`backend/moyuan_web/startup_checks.py`](../../backend/moyuan_web/startup_checks.py)
- [`backend/moyuan_web/routes/health.py`](../../backend/moyuan_web/routes/health.py)

启动后建议立即检查：

```bash
curl http://localhost:38083/api/health
curl http://localhost:38083/api/ready
curl http://localhost:38083/api/metrics
```

如果 `/api/ready` 返回 `503`，优先检查：

- `backend/config/llm_config.yaml`
- `backend/config/server_config.yaml`
- `data/` 目录权限
- `MOYUAN_FAIL_FAST_STARTUP_VALIDATION`
- 启动日志中的 `startup_validation`
