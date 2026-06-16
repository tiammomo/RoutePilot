# Backend Maintainer Playbook

这份手册面向维护 `agent/` 与 `backend/` 的开发者，目标是帮助你快速定位改动入口、减少回归风险、缩短排障路径。

## 1. 一条请求如何流转

以 `POST /api/chat/stream` 为例：

1. `backend/moyuan_web/routes/chat.py`
2. `backend/moyuan_web/services/chat_service.py`
3. `agent/travel_agent/runtime/agent_runtime.py`
4. `agent/travel_agent/runtime/runtime_driver.py`
5. `agent/travel_agent/graph/runtime_flow.py`
6. `agent/travel_agent/graph/builder.py` / `agent/travel_agent/graph/nodes.py`
7. `agent/travel_agent/tools/travel_tools.py` / `agent/travel_agent/tools/travel_api.py`
8. 返回 SSE 事件到前端

排障建议：

1. 先确认 route 是否拿到预期参数（`mode`、`session_id`、`message`）。
2. 再确认 service 层是否正确写入会话、推送 SSE 事件。
3. 再确认 runtime seam 是否把请求正确收口到 graph execution flow。
4. 最后看 graph/tool 层是否因 timeout、fallback、verify 导致结果偏差。

## 2. 核心模块职责

| 区域 | 主要入口 | 职责 |
| --- | --- | --- |
| Agent graph | `graph/builder.py`、`graph/nodes.py`、`graph/memory_integration.py` | 组装 LangGraph、执行节点路由、管理记忆摘要与画像合并。 |
| Checkpoint | `graph/persistent_checkpointer.py`、`graph/postgres_checkpointer.py` | 统一承接 sqlite / postgres checkpoint 持久化与压缩。 |
| Tool provider | `tools/travel_api.py` | provider 访问、缓存、failover、结果标准化。 |
| Web route | `routes/*` | 请求校验与 HTTP / SSE 出口。 |
| Web service | `services/*` | 业务流程编排、聚合、错误降级、健康指标。 |
| Persistence | `repositories/*`、`persistence/*` | 持久化抽象、`file | postgres` 切换与 schema bootstrap。 |
| Middleware | `middleware/*` | 请求日志、限流、超时控制。 |

## 3. 高风险变更清单

以下变更建议至少补测试 + 回放：

1. `nodes.py` 中的 `execute/verify/self_check` 路由分支。
2. `travel_api.py` 的 provider 优先级、缓存策略、fallback 判定。
3. `chat_service.py` 的 SSE 事件顺序与字段命名。
4. `session` 相关持久化格式与恢复语义。
5. `share_service.py` 的本地 JSON 落盘与 `.bak` 恢复逻辑。

## 4. 常见故障与定位建议

维护时最常见的 4 类问题可以直接按这张表排：

| 现象 | 先看什么 |
| --- | --- |
| 前端“卡住不出答案” | 是否收到 `reasoning_start` / `answer_start`、最终是否有 `done`、`onError` 分支是否触发。 |
| 工具结果为空或明显过期 | `execution_stats.steps[*].error_code`、`fallback_used / is_stale / refresh_attempted`、provider down 环境变量与配置文件。 |
| 健康指标异常 | `GET /api/health/tools`、`GET /api/health/tools/intents`、`chat_service.py` 的 `_record_run_metrics` 与 `_build_health_metrics_snapshot`。 |
| 一键运行态自检 | 先跑 `python scripts/dev.py runtime-doctor --runtime-doctor-json`、`python scripts/dev.py runtime-doctor --base-url http://localhost:38083 --runtime-doctor-strict`、`python scripts/dev.py support-bundle --base-url http://localhost:38083`；重点看配置可用性、`data/` 可写性、`checkpoint_runtime` 视图、backup 目录、OpenAPI / SSE 快照、live `/api/health` `/api/ready` `/api/metrics`。 |

## 5. 注释与文档约定

后端代码保持以下约定：

1. 模块、类、函数都应有 docstring。
2. Docstring 首句描述“职责”，不要写模板句（例如 `Execute ...`）。
3. `Args` 与 `Returns` 使用业务语义，不使用泛化占位文本。
4. 复杂分支可加少量内联注释，解释“为什么这样做”。

文档同步建议：

| 改动类型 | 至少同步哪些文档 |
| --- | --- |
| API 协议变更 | `docs/reference/api-reference.md` |
| 错误码或验证规则变更 | `docs/reference/error-code-reference.md` |
| 结构变更 | `docs/reference/project-structure.md` |
| 新增配置 | `docs/reference/configuration-reference.md` |
| 运行脚本、契约快照或 CI 安全扫描 | `docs/testing/testing-guide.md`、`docs/architecture/infrastructure-foundations.md` |

checkpoint 相关维护约定：

1. runtime 默认 checkpointer 与脚本入口统一收口到 `agent/travel_agent/runtime_sources.py`。
2. 不要在脚本里直接 new `PersistentSqliteSaver` 作为长期方案；优先复用同一套 checkpoint factory。
3. 如果改了 replay / prune / checkpoint backend 行为，至少同步：
   - `docs/reference/configuration-reference.md`
   - `docs/architecture/data-storage.md`
   - `docs/architecture/infrastructure-foundations.md`
   - `docs/getting-started/development-workflow.md`
4. backup / restore manifest 必须继续明确 checkpoint backend、restore strategy 与外部恢复说明，不能再默认“checkpoint 一定是本地 SQLite 单文件”。
5. `runtime_doctor.py` 和 `export_support_bundle.py` 也必须继续暴露同一份 `checkpoint_runtime` 视图，避免排障时 manifest / doctor / support bundle 三套口径不一致。
6. 如果改了 `runtime-maintenance` / `checkpoint-maintenance` 的顺序或默认行为，必须同步 README 和测试指南里的维护流程说明。

## 6. 提交前最小检查

| 场景 | 最小检查 |
| --- | --- |
| 通用后端改动 | `python -m compileall -q agent web scripts`、`python scripts/dev.py backend-test --pytest-slice all`、`python scripts/dev.py runtime-doctor --runtime-doctor-json` |
| 改 checkpoint backend | `python scripts/dev.py agent-replay --replay-session-id <session_id> --replay-dry-run`、`python scripts/dev.py runtime-prune --prune-vacuum-checkpoints`、`python scripts/dev.py runtime-backup --backup-label checkpoint-change`、`python scripts/dev.py runtime-maintenance --prune-keep-latest-backups 10`、`python scripts/dev.py checkpoint-maintenance --replay-session-id <session_id>` |
| 改前端 SSE 渲染 | `cd frontend && npm run lint` |

## 7. release 与观测资产

如果这次改动涉及发布链路、镜像标签或运行面板，优先看下面这组资产：

- [`.github/workflows/release.yml`](../../.github/workflows/release.yml)
- [`scripts/export_release_manifest.py`](../../scripts/export_release_manifest.py)
- [`scripts/export_support_bundle.py`](../../scripts/export_support_bundle.py)
- [`extend/observability/README.md`](../../extend/observability/README.md)
- [`extend/observability/grafana-dashboard.json`](../../extend/observability/grafana-dashboard.json)
- [`extend/observability/prometheus-alerts.yml`](../../extend/observability/prometheus-alerts.yml)
- [`extend/observability/prometheus.yml`](../../extend/observability/prometheus.yml)

最小核对顺序只要记住 4 步：

1. 先确认 `/api/health` 与 `/` 的 `build` 元数据是否符合预期。
2. 再确认 release manifest 里的 backend / frontend 版本、`image_tag` 和 `image_ref` 是否正确；正式发布镜像不要再使用 `latest`。
3. 最后确认 dashboard / alert 用到的 Prometheus 指标名和当前代码一致。
4. 如果要交接问题现场，补导出一次 support bundle，至少检查 `manifest.json.runtime_health.checkpoint_*` 和 `checkpoint-runtime.json`。

如果你是在做长期维护规划，而不是单次排障，继续看：

- [`../architecture/backend-database-devops-maintenance-plan.md`](../architecture/backend-database-devops-maintenance-plan.md)
- [`../governance/adr/ADR-0002-versioned-release-images.md`](../governance/adr/ADR-0002-versioned-release-images.md)

## 8. 统一命令入口

如果你是维护者，优先从 [`scripts/dev.py`](../../scripts/dev.py) 进入，而不是每次手敲零散命令：

| 命令 | 适合场景 |
| --- | --- |
| `python scripts/dev.py help` | 先看统一命令面。 |
| `python scripts/dev.py backend-dev` | 本地起后端。 |
| `python scripts/dev.py frontend-dev` | 本地起前端。 |
| `python scripts/dev.py infra-check` | 提交前做一轮基础设施门禁检查。 |
| `python scripts/dev.py support-bundle` | 需要把现场状态导出交给其他维护者。 |
| `python scripts/dev.py compose-config` | 改端口、环境变量、volume、镜像参数后先本地预检查。 |
| `python scripts/dev.py container-smoke` | 本地重现 backend / frontend 镜像构建，或需要临时切换镜像站。 |
