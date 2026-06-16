# Infrastructure Foundations

这份文档专门记录本项目当前已经落地的基础建设能力，以及后续继续演进时应优先维护的约束。

适合在这些场景进入：

- 需要统一本地启动、Docker 启动和 CI 行为
- 需要排查为什么 `/api/ready` 返回 `503`
- 需要定位一次请求在前端、Backend API、Agent 之间的 `request_id / trace_id`
- 需要查看 CI 当前如何分层跑测试、产出 benchmark / golden eval / quality gate
- 需要确认改动某个基础设施文件后，应该同步哪些文档

## 1. 本轮基础建设交付概览

当前基础建设分成 4 个交付面：

1. 运行与部署收敛
2. 配置与 readiness 治理
3. CI 与测试分层
4. 全链路 trace + metrics

在此基础上，本轮又补了两类维护资产：

5. 数据生命周期治理
6. 仓库安全与契约治理基础

对应核心代码路径：

- 运行与部署
  - [`deploy/compose/compose.yaml`](../../deploy/compose/compose.yaml)
  - [`deploy/docker/backend.Dockerfile`](../../deploy/docker/backend.Dockerfile)
  - [`deploy/docker/frontend.Dockerfile`](../../deploy/docker/frontend.Dockerfile)
  - [`deploy/compose/frontend.local.yml`](../../deploy/compose/frontend.local.yml)
- 配置与 readiness
  - [`backend/config/__init__.py`](../../backend/config/__init__.py)
  - [`backend/config/server_config.yaml.example`](../../backend/config/server_config.yaml.example)
  - [`backend/moyuan_web/startup_checks.py`](../../backend/moyuan_web/startup_checks.py)
  - [`backend/moyuan_web/routes/health.py`](../../backend/moyuan_web/routes/health.py)
- CI 与测试分层
  - [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml)
  - [`pyproject.toml`](../../pyproject.toml)
  - [`tests/conftest.py`](../../tests/conftest.py)
- Trace 与 metrics
  - [`backend/moyuan_web/observability.py`](../../backend/moyuan_web/observability.py)
  - [`backend/moyuan_web/middleware/__init__.py`](../../backend/moyuan_web/middleware/__init__.py)
  - [`backend/moyuan_web/routes/chat.py`](../../backend/moyuan_web/routes/chat.py)
  - [`backend/moyuan_web/services/chat_service.py`](../../backend/moyuan_web/services/chat_service.py)
  - [`frontend/src/services/api/chatClient.ts`](../../frontend/src/services/api/chatClient.ts)
  - [`frontend/src/services/api/chatStreamParser.ts`](../../frontend/src/services/api/chatStreamParser.ts)
- 数据生命周期
  - [`scripts/runtime_backup.py`](../../scripts/runtime_backup.py)
  - [`scripts/runtime_restore.py`](../../scripts/runtime_restore.py)
  - [`scripts/runtime_prune.py`](../../scripts/runtime_prune.py)
  - [`scripts/runtime_doctor.py`](../../scripts/runtime_doctor.py)
  - [`docs/architecture/data-storage.md`](data-storage.md)
- 安全与契约治理
  - [`.github/SECURITY.md`](../../.github/SECURITY.md)
  - [`.github/dependabot.yml`](../../.github/dependabot.yml)
  - [`deploy/security/gitleaks.toml`](../../deploy/security/gitleaks.toml)
  - [`scripts/export_openapi_snapshot.py`](../../scripts/export_openapi_snapshot.py)
  - [`scripts/export_sse_contract_snapshot.py`](../../scripts/export_sse_contract_snapshot.py)
  - [`docs/reference/openapi.snapshot.json`](../reference/openapi.snapshot.json)
  - [`docs/reference/sse-contract.snapshot.json`](../reference/sse-contract.snapshot.json)

## 2. 运行与部署收敛

### 2.1 统一端口

当前统一端口基线是：

- Frontend: `33003`
- Backend API: `38083`

这组端口同时体现在：

- 根 README
- Quick Start
- `deploy/compose/compose.yaml`
- `deploy/compose/frontend.local.yml`
- `backend/config/server_config.yaml.example`
- 前端 Next.js 启动脚本与 rewrite

如果未来要改端口，至少要同步这些文件，不要只改某一层。

### 2.2 Docker / Compose 资产

推荐优先使用根目录 Compose：

```bash
docker compose --file deploy/compose/compose.yaml up --build
```

对应职责：

- [`deploy/docker/backend.Dockerfile`](../../deploy/docker/backend.Dockerfile)
  - 安装 Python 依赖
  - 拷贝 `agent/`、`backend/`、`scripts/`
  - 以 `uvicorn` 启动 `moyuan_web.main:app`
- [`deploy/docker/frontend.Dockerfile`](../../deploy/docker/frontend.Dockerfile)
  - 先 `npm ci`
  - 再 `next build`
  - 最后以 standalone 模式运行前端
- [`deploy/compose/compose.yaml`](../../deploy/compose/compose.yaml)
  - 把 `backend` 与 `frontend` 放进统一网络
  - 对外暴露 `38083/33003`
  - 挂载 `backend/config/`、`data/`、`logs/`

当前两份 Dockerfile 都支持通过 build args 覆盖基础镜像：

- `PYTHON_BASE_IMAGE`
- `NODE_BASE_IMAGE`

这样在 Docker Hub 拉取受限时，可以直接切换到镜像站，例如：

```bash
python scripts/dev.py compose-up \
  --python-base-image "5ykpmdvdg6to97.xuanyuan.run/library/python:3.13-slim" \
  --node-base-image "5ykpmdvdg6to97.xuanyuan.run/library/node:22-alpine"
```

### 2.3 运行方式建议

建议把运行方式统一成 3 类：

1. 本地开发
   - 手动启动前后端
   - 适合改代码和调试
2. Docker 联调
   - `docker compose --file deploy/compose/compose.yaml up --build`
   - 适合复现部署环境和验证配置
3. CI 运行
   - 由 [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) 自动准备配置、跑测试、跑质量门禁

## 3. 配置与 readiness 治理

### 3.1 配置来源优先级

当前 `ServerConfig` 的配置优先级是：

`环境变量 > backend/config/server_config.yaml > 代码默认值`

实现入口在 [`backend/config/__init__.py`](../../backend/config/__init__.py)。

其中重点字段包括：

- `web.host`
- `web.port`
- `frontend.port`
- `web.cors_origins`
- `middleware.request_timeout_seconds`
- `middleware.rate_limit_max_requests`
- `middleware.rate_limit_window_seconds`
- `observability.metrics_enabled`
- `observability.metrics_path`
- `observability.structured_logging`
- `startup.fail_fast_validation`

### 3.2 启动校验

启动校验在 [`backend/moyuan_web/startup_checks.py`](../../backend/moyuan_web/startup_checks.py)。

当前会检查：

1. `server_config` 能否解析出有效配置
2. `data/` 是否可写
3. `backend/config/llm_config.yaml` 是否存在且是否至少有一个 active model
4. 依赖容器能否 resolve 出 `SessionRepository` 和 `ChatService`
5. 聊天运行时能否初始化

校验结果会写入：

- `app.state.readiness_snapshot`
- Prometheus readiness gauge
- 结构化日志 `startup_validation`

### 3.3 `/api/ready`

[`backend/moyuan_web/routes/health.py`](../../backend/moyuan_web/routes/health.py) 里的 `/api/ready` 现在返回真实检查结果，不再是静态 `ok`。

返回规则：

- `200`: `status == "ready"`
- `503`: `status == "not_ready"` 或 `status == "starting"`

响应结构包含：

- `status`
- `validated_at`
- `checks`

每个 `check` 都有：

- `name`
- `status`
- `message`
- `details`

### 3.4 fail-fast

如果设置：

```bash
MOYUAN_FAIL_FAST_STARTUP_VALIDATION=true
```

那么应用在启动校验失败时会直接抛错退出，而不是“服务起来了但 readiness 一直不通过”。

## 4. CI 与测试分层

### 4.1 pytest markers

当前后端测试分成：

- `unit`
- `integration`
- `local`
- `external_api`
- `quality`

定义位置：

- [`pyproject.toml`](../../pyproject.toml)
- [`tests/conftest.py`](../../tests/conftest.py)

### 4.2 当前 CI 分层

[`ci.yml`](../../.github/workflows/ci.yml) 里当前主要分成下面这些 lane：

| CI lane | 统一入口 | 主要目的 |
| --- | --- | --- |
| Backend unit | `python scripts/dev.py backend-test --pytest-slice unit` | 跑稳定的后端单测层。 |
| Backend local smoke | `python scripts/dev.py backend-test --pytest-slice local` | 跑本地契约和轻量 smoke。 |
| Docstring audit | `python scripts/dev.py docstring` | 检查缺失 docstring 与新增低信息量模板 docstring；历史存量由 `docs/reference/docstring-audit.low-info-baseline.json` 管理。 |
| Complexity budget | `python scripts/dev.py complexity` | 守住 Agent / Backend API / Frontend 热点文件“只减不增”的复杂度预算；基线在 `docs/reference/complexity-budget.json`。 |
| Decision record audit | `python scripts/dev.py decision-records` | 检查 `docs/governance/` 下 ADR / RFC / Design Review 的统一状态和必填章节。 |
| Benchmark / golden / trend / gate | `python scripts/dev.py benchmark-report`、`golden-report`、`benchmark-trend`、`quality-gate` | 收口质量基线、趋势和最终门禁。 |
| Frontend quality | frontend lint / test / build | 守住前端质量与构建成功。 |
| Dependency / secret audit | `pip-audit`、Dockerized `gitleaks` | 做依赖和 secret 基线检查。 |
| Contract snapshots | `python scripts/dev.py snapshots` | 校验 `openapi / sse-contract / runtime-doctor` 三份快照无漂移。 |

当前 backend pytest 已与本地入口统一：

- CI 不再直接写 `pytest tests ...`
- backend slice 统一收口到 `python scripts/dev.py backend-test --pytest-slice ...`
- docstring / complexity / governance audit / ruff / mypy / snapshots 也优先复用 `scripts/dev.py`
- benchmark / golden eval / trend / quality gate / release scorecard 也收口到 `scripts/dev.py`
- 这样本地回归和 CI 分层复用的是同一套命令面

### 4.3 CI 产物

当前 CI 会上传并总结这些质量产物：

- `docs/benchmarks/agent_benchmark_latest.json`
- `docs/benchmarks/agent_benchmark_latest.md`
- `docs/benchmarks/agent_benchmark_trend_latest.md`
- `docs/benchmarks/agent_golden_eval_latest.json`
- GitHub Step Summary 中的 backend / frontend summary

## 5. 全链路 trace 与 metrics

### 5.1 request_id / trace_id 主链

完整链路现在是：

```mermaid
flowchart LR
    A["chatClient.ts + chatStreamParser.ts"] -->|"X-Request-ID / X-Trace-ID"| B["FastAPI middleware"]
    B --> C["routes/chat.py"]
    C --> D["ChatService.stream_chat"]
    D --> E["SSE payloads"]
    E --> A
```

关键行为：

- 前端 REST 和 SSE 都会主动生成 `X-Request-ID` / `X-Trace-ID`
- 中间件会把它们绑定到 request state 和 contextvars
- ChatService 会把它们写进结构化日志和 SSE payload
- 前端会把 SSE 里的 `request_id` / `trace_id` 继续带回调试信息

### 5.2 结构化日志

结构化日志入口在 [`backend/moyuan_web/observability.py`](../../backend/moyuan_web/observability.py)。

目前会输出这些事件：

- `http_request`
- `http_request_failed`
- `http_request_timeout`
- `startup_validation`
- `chat_stream_started`
- `chat_stream_completed`
- `chat_stream_failed`

如果配置：

```bash
MOYUAN_STRUCTURED_LOGGING=false
```

则会回退成普通日志文本，而不是 JSON 日志。

### 5.3 Prometheus metrics

Prometheus 指标同样由 [`backend/moyuan_web/observability.py`](../../backend/moyuan_web/observability.py) 统一定义。

当前主要指标：

- `moyuan_http_requests_total`
- `moyuan_http_request_duration_seconds`
- `moyuan_http_in_flight_requests`
- `moyuan_chat_stream_requests_total`
- `moyuan_sse_events_total`
- `moyuan_readiness_state`

指标出口：

- 默认：`GET /api/metrics`
- 可通过 `observability.metrics_path` 或 `MOYUAN_METRICS_PATH` 添加别名路径
- 可通过 `MOYUAN_METRICS_ENABLED=false` 关闭

## 6. 推荐的运维自检顺序

### 6.1 启动后优先检查

```bash
curl http://localhost:38083/api/health
curl http://localhost:38083/api/ready
curl http://localhost:38083/api/metrics
```

如果 `/api/ready` 返回 `503`，优先看：

1. `backend/config/llm_config.yaml` 是否存在、是否至少有一个 active model
2. `data/` 目录是否可写
3. 启动日志中的 `startup_validation`
4. ChatService 初始化是否失败

### 6.2 流式对话异常时优先检查

1. 浏览器或前端日志中是否打印了 `request_id / trace_id`
2. `/api/chat/stream` 响应头是否带 `X-Request-ID / X-Trace-ID`
3. SSE payload 中是否有 `request_id / trace_id`
4. `/api/metrics` 中 `moyuan_sse_events_total` 是否增长

## 7. 数据生命周期治理

### 7.1 维护动作速查

| 动作 | 推荐命令 | 重点输出 / 行为 |
| --- | --- | --- |
| 备份 | `python scripts/dev.py runtime-backup` | 归档 session、agent memory、share links、failure clusters，以及 checkpoint runtime metadata。 |
| 带标签备份 | `python scripts/dev.py runtime-backup --backup-label before-upgrade` | 给升级前或排障前的备份打显式标签。 |
| doctor | `python scripts/dev.py runtime-doctor --runtime-doctor-json` | 暴露 `checkpoint_runtime.backend / restore_strategy / requires_external_snapshot / restore_instructions`。 |
| 严格 doctor | `python scripts/dev.py runtime-doctor --base-url http://localhost:38083 --runtime-doctor-strict` | 对活服务做更严格的 readiness / metrics / contract 检查。 |
| 组合维护 | `python scripts/dev.py runtime-maintenance --prune-keep-latest-backups 10 --prune-max-backup-age-days 14` | 固定串起 `runtime-backup -> runtime-doctor --json -> runtime-prune`。 |
| 恢复 | `python scripts/dev.py runtime-restore --restore-archive artifacts/runtime_backups/runtime_backup_<timestamp>.zip` | 先做 `pre-restore` 安全备份，再覆盖运行文件，并打印 checkpoint 恢复说明。 |
| 运行态清理 | `python scripts/dev.py runtime-prune --prune-max-session-age-seconds 2592000 --prune-max-failure-age-days 30 --prune-vacuum-checkpoints` | 清理旧 session / failure，并做 checkpoint compaction。 |
| PostgreSQL checkpoint 清理 | `python scripts/dev.py runtime-prune --prune-vacuum-checkpoints --prune-checkpoint-backend postgres --prune-checkpoint-db 'postgresql://user:password@localhost:5432/moyuan'` | 同样走 checkpoint factory，只是目标换成 SQL-backed maintenance。 |
| Checkpoint 组合维护 | `python scripts/dev.py checkpoint-maintenance --replay-session-id <session_id> --prune-checkpoint-backend postgres --prune-checkpoint-db 'postgresql://user:password@localhost:5432/moyuan'` | 固定串起 `runtime-prune --vacuum-checkpoints -> optional agent-replay --dry-run -> runtime-doctor --json`。 |

checkpoint 相关规则只要记住两点：

- `sqlite` backend 会在项目目录内归档 SQLite 文件，并在清理时执行 compaction + `VACUUM`。
- `postgres` backend 不会导出外部数据库内容；restore 时仍需要先恢复外部 PostgreSQL 快照。

## 8. 安全与契约治理基础

### 8.1 安全基线

当前仓库已经补上：

- [`.github/SECURITY.md`](../../.github/SECURITY.md)
- [`.github/dependabot.yml`](../../.github/dependabot.yml)
- [`deploy/security/gitleaks.toml`](../../deploy/security/gitleaks.toml)

这代表项目已经至少有：

- 安全问题上报入口说明
- Python / npm 依赖更新建议机制
- secret scan allowlist 与示例 token 例外规则
- 敏感配置文件与模板文件边界说明
- CI 中的 `pip-audit` 依赖审计
- CI 中的 Dockerized `gitleaks` secret scan

### 8.2 OpenAPI 快照

契约治理的第一步已经补上：

```bash
python scripts/export_openapi_snapshot.py
```

默认产物：

- [`docs/reference/openapi.snapshot.json`](../reference/openapi.snapshot.json)

这个文件的用途不是“给用户看”，而是：

- 评审接口变更
- 做 schema diff
- 未来接入契约回归检查

### 8.3 SSE 快照

流式契约现在也会导出稳定快照：

```bash
python scripts/export_sse_contract_snapshot.py
```

默认产物：

- [`docs/reference/sse-contract.snapshot.json`](../reference/sse-contract.snapshot.json)

它重点保护：

- `direct / react / plan` 三种模式的事件顺序
- `session_id / reasoning_* / stage / tool_* / metadata / done` 的字段形状
- `request_id / trace_id / run_id` 等动态值在快照中的归一化方式

## 9. 改基础设施时的文档同步矩阵

### 改运行端口 / Docker / Compose

至少同步：

- [`README.md`](../../README.md)
- [`docs/getting-started/quick-start.md`](../getting-started/quick-start.md)
- [`docs/reference/configuration-reference.md`](../reference/configuration-reference.md)
- [`docs/reference/project-structure.md`](../reference/project-structure.md)

### 改 readiness / health / startup check

至少同步：

- [`docs/reference/api-reference.md`](../reference/api-reference.md)
- [`docs/architecture/system-architecture.md`](system-architecture.md)
- [`docs/architecture/infrastructure-foundations.md`](infrastructure-foundations.md)

### 改 trace / metrics / 日志

至少同步：

- [`README.md`](../../README.md)
- [`docs/reference/api-reference.md`](../reference/api-reference.md)
- [`docs/testing/testing-guide.md`](../testing/testing-guide.md)
- [`docs/architecture/system-architecture.md`](system-architecture.md)

### 改 CI / pytest marker / quality gate

至少同步：

- [`README.md`](../../README.md)
- [`docs/getting-started/development-workflow.md`](../getting-started/development-workflow.md)
- [`docs/testing/testing-guide.md`](../testing/testing-guide.md)

## 10. P1 基础设施继续完善

### 10.1 P1 继续完善速查

| 方向 | 当前资产 | 维护者最该记住什么 |
| --- | --- | --- |
| 编码与仓库规范 | [`.editorconfig`](../../.editorconfig)、[`.gitattributes`](../../.gitattributes) | 统一编码、缩进、换行和二进制识别，减少跨平台 diff 噪音。 |
| 本地命令入口 | [`scripts/dev.py`](../../scripts/dev.py) | 优先把它当成本地维护入口，常用任务已收口到 `test / ruff / mypy / docstring / snapshots / release-manifest / support-bundle / infra-check / compose-config / compose-up / compose-observability / container-smoke`。 |
| 静态质量门禁 | [`pyproject.toml`](../../pyproject.toml)、[`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) | CI 已对基础设施相关核心文件执行 `ruff` / `mypy`，策略是先覆盖 release / observability / startup / contract / runtime maintenance 热点。 |
| 容器与发布闭环 | [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) `container-validate`、[`.github/workflows/release.yml`](../../.github/workflows/release.yml)、[`scripts/export_release_manifest.py`](../../scripts/export_release_manifest.py) | 本地先跑 `python scripts/dev.py compose-config`；正式发布禁止 `latest`，手动 release 必须显式给 `release_tag`，manifest 必须带 `image_tag / image_ref`。 |
| Dashboard / alert | [`extend/observability/README.md`](../../extend/observability/README.md)、[`extend/observability/grafana-dashboard.json`](../../extend/observability/grafana-dashboard.json)、[`extend/observability/prometheus-alerts.yml`](../../extend/observability/prometheus-alerts.yml) | 重点看 HTTP 请求速率、p95、in-flight、chat stream outcome、SSE event rate、readiness state，以及 `MoyuanReadinessDown / MoyuanHttp5xxSpike / MoyuanChatStreamFailures / MoyuanSseEventStall`。 |
| Local observability / support bundle | `deploy/compose/compose.yaml` observability profile、`extend/observability/prometheus.yml`、`extend/observability/grafana-provisioning/`、[`scripts/export_support_bundle.py`](../../scripts/export_support_bundle.py) | `docker compose --file deploy/compose/compose.yaml --profile observability up --build` 启本地观测栈；`python scripts/dev.py support-bundle --base-url http://localhost:38083` 打排障包；support bundle 会额外带 `manifest.json.runtime_health.*` 和 `checkpoint-runtime.json` 两层 checkpoint 视图。 |
