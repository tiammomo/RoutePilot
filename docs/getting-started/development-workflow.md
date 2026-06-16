# Development Workflow

这份文档面向日常开发、联调、提交前自检和基础设施改动同步，默认环境为 macOS / Linux / Windows 终端。

## 1. 日常开发顺序

1. 确保本地依赖已就绪：`python scripts/bootstrap.py`
2. 检查配置文件：
   - `backend\config\llm_config.yaml`
   - `backend\config\server_config.yaml`
3. 启动 Backend API：

```bash
python scripts/dev.py backend-dev
```

4. 启动前端：

```bash
python scripts/dev.py frontend-dev
```

5. 启动后先检查：
   - `/api/health`
   - `/api/ready`
   - `/api/metrics`
6. 改动完成后执行对应验证，并同步相关文档。

建议本地开发环境安装：

```bash
uv pip install -r requirements-dev.txt
```

## 2. 统一命令入口

根目录的 [`scripts/dev.py`](../../scripts/dev.py) 是本地开发、测试和基础设施校验的统一入口，推荐优先使用。

```bash
python scripts/dev.py backend-dev
python scripts/dev.py frontend-dev
python scripts/dev.py help
```

当前最常用的任务有：

- `test`
  - 后端 `unit/local` pytest
  - 前端 `lint/test/build`
- `infra-check`
  - `ruff`
  - `mypy`
  - `docstring_audit --strict`（覆盖率 + 低信息量治理）
  - `complexity_budget --strict`（热点文件只减不增）
- `decision_record_audit --strict`（ADR / RFC / Design Review 结构审计）
- `skills_market_audit --strict`（skills 的 `schema + tests + docs + eval` 四件套治理）
- `runtime_contract_audit --strict`（typed runtime seam 治理）
  - `runtime_doctor --json`
    当 runtime 数据文件被占用时会降级报告具体文件问题，而不是直接让整条 `infra-check` 中断
  - OpenAPI / SSE snapshot 导出
  - release harness scorecard
  - release manifest 导出
  - 如果 Docker 可用，再附带默认和 `observability` profile 的 compose 渲染校验
- `snapshots`
  - 导出 OpenAPI 和 SSE 契约快照
- `support-bundle`
  - 导出运行态支持包
- `compose-config`
  - 渲染默认和 `observability` profile 的 Compose 配置
- `container-smoke`
  - 本地构建 backend / frontend 镜像

## 3. 什么时候优先用 Compose

如果你正在改这些内容，优先直接跑容器联调：

- 端口
- 环境变量注入
- 容器网络
- volume 挂载
- Next.js rewrite / API base
- readiness / metrics 暴露
- release 镜像构建参数
- Prometheus / Grafana 观测栈

推荐命令：

```bash
docker compose --file deploy/compose/compose.yaml up --build
docker compose --file deploy/compose/compose.yaml --profile observability up --build
```

在真正启动前，先做一次渲染校验会更稳：

```bash
python scripts/dev.py compose-config
```

如果当前网络拉取 Docker Hub 较慢，可以直接把镜像站作为基础镜像传进来：

```bash
python scripts/dev.py compose-up \
  --python-base-image "5ykpmdvdg6to97.xuanyuan.run/library/python:3.13-slim" \
  --node-base-image "5ykpmdvdg6to97.xuanyuan.run/library/node:22-alpine"
```

## 4. 常用命令

### 4.1 后端与前端验证

```bash
python scripts/dev.py backend-test --pytest-slice unit
python scripts/dev.py backend-test --pytest-slice local
python scripts/dev.py ruff
python scripts/dev.py mypy
python scripts/dev.py docstring
python scripts/dev.py complexity
python scripts/dev.py decision-records
python scripts/dev.py skills-market
python scripts/dev.py runtime-contracts
python scripts/dev.py frontend-lint
python scripts/dev.py frontend-test
python scripts/dev.py frontend-build
```

说明：

- `python scripts/dev.py backend-test` 是当前推荐的后端回归入口，支持 `--pytest-slice unit|local|runtime|ops|all`
- 如果只想回归少量后端用例，可以重复传 `--pytest-path tests/...`
- `docstring_audit --strict` 现在同时拦截缺失 docstring 和新增低信息量模板 docstring
- 当前存量低信息量项由 `docs/reference/docstring-audit.low-info-baseline.json` 记录，后续改动应只减不增
- `complexity_budget --strict` 会对热点文件执行“只减不增”预算门禁，当前预算基线由 `docs/reference/complexity-budget.json` 记录
- `decision_record_audit --strict` 会检查 `docs/governance/` 下的 ADR / RFC / Design Review 是否包含统一状态和必填章节
- `skills_market_audit --strict` 会检查默认 skill catalog 是否补齐 `schema + tests + docs + eval` 四件套，并验证 `docs_path / test_fixture / eval_fixture / onboarding_doc`
- `runtime_contract_audit --strict` 会检查 `AgentRuntime -> runtime_driver -> runtime_flow` 是否仍通过显式 supervisor contract 协作，防止 runtime seam 退化回 loose kwargs 和直接 graph import
- `export_runtime_doctor_snapshot.py` 会把 `runtime_doctor` 的 typed report contract 固化到 `docs/reference/runtime-doctor.snapshot.json`，供 support bundle / release manifest / release harness scorecard / release evidence / CI 复用
- 当前前端默认验证入口已经稳定化：`python scripts/dev.py frontend-test` 会触发 `npm run test:run`，`python scripts/dev.py frontend-build` 默认走 `next build --webpack`
- `scripts/dev.py` 当前也会自动解析跨平台 npm 可执行文件，在 Windows 上优先命中 `npm.cmd`

### 4.2 运行态与契约维护

```bash
python scripts/dev.py runtime-backup
python scripts/dev.py runtime-backup --backup-label before-upgrade
python scripts/dev.py runtime-restore --restore-archive artifacts/runtime_backups/runtime_backup_<timestamp>.zip
python scripts/dev.py runtime-doctor --runtime-doctor-json
python scripts/dev.py runtime-doctor --base-url http://localhost:38083 --runtime-doctor-strict
python scripts/dev.py runtime-prune --prune-keep-latest-backups 10 --prune-max-backup-age-days 14
python scripts/dev.py agent-replay --replay-session-id <session_id> --replay-dry-run
python scripts/dev.py runtime-maintenance --prune-keep-latest-backups 10 --prune-max-backup-age-days 14
python scripts/dev.py checkpoint-maintenance --replay-session-id <session_id> --prune-checkpoint-backend postgres --prune-checkpoint-db 'postgresql://user:password@localhost:5432/moyuan'
python scripts/dev.py snapshots
python scripts/dev.py benchmark-report
python scripts/dev.py golden-report
python scripts/dev.py benchmark-trend
python scripts/dev.py release-scorecard
python scripts/dev.py quality-gate
python scripts/dev.py release-manifest --git-sha local --git-ref refs/heads/main --owner local
python scripts/dev.py support-bundle --base-url http://localhost:38083
```

### 4.3 对应的统一入口

```bash
python scripts/dev.py test
python scripts/dev.py infra-check
python scripts/dev.py snapshots
python scripts/dev.py benchmark-report
python scripts/dev.py golden-report
python scripts/dev.py benchmark-trend
python scripts/dev.py quality-gate
python scripts/dev.py runtime-backup
python scripts/dev.py runtime-prune --prune-vacuum-checkpoints
python scripts/dev.py agent-replay --replay-session-id <session_id> --replay-dry-run
python scripts/dev.py runtime-maintenance --prune-keep-latest-backups 10 --prune-max-backup-age-days 14
python scripts/dev.py checkpoint-maintenance --replay-session-id <session_id>
python scripts/dev.py runtime-doctor --runtime-doctor-json
python scripts/dev.py release-manifest --git-sha local --git-ref refs/heads/main --owner local
python scripts/dev.py support-bundle
python scripts/dev.py container-smoke
```

组合任务说明：

- `runtime-maintenance`
  - 适合常规运行面维护，固定执行 `backup -> doctor(json) -> prune`
- `checkpoint-maintenance`
  - 适合 checkpoint 清理和回放核对，固定执行 `prune(vacuum checkpoints) -> optional replay(dry-run) -> doctor(json)`
  - 如果传 `--replay-session-id`，`dev.py` 会自动补上 dry-run 语义，避免把排障流程变成写路径

## 5. 提交前检查建议

### 5.1 改 Backend API / Agent / startup / observability

1. `/api/health` 正常
2. `/api/ready` 返回 `200`，或者你明确知道为什么是 `503`
3. `/api/metrics` 可访问
4. 跑后端 `unit/local`
5. 跑 `ruff`、`mypy`、`docstring_audit --strict`、`complexity_budget --strict`、`decision_record_audit --strict`、`skills_market_audit --strict`、`runtime_contract_audit --strict`
6. 跑 `python scripts/dev.py runtime-doctor --base-url http://localhost:38083 --runtime-doctor-strict`
7. 刷新 `runtime doctor / OpenAPI / SSE` 快照
8. 跑 `python scripts/dev.py release-scorecard`
9. 如改契约，确认快照与 support bundle / release evidence 一致

### 5.2 改前端 / SSE / 接口契约

1. `cd frontend && npm run lint`
2. `cd frontend && npm run test:run`
3. `cd frontend && npm run build`
4. 检查 `/api/chat/stream` 是否仍然返回 `text/event-stream`
5. 检查 `X-Request-ID / X-Trace-ID`
6. 如有运行态异常，导出 support bundle
7. 如改了 share / delivery contract，补跑 `tests/test_share_service_unit.py`、`tests/test_share_route_local.py`、`frontend/tests/features/trip-plan/travelPlanDeliverySnapshot.test.ts` 与 `frontend/tests/features/chat/useChatSessionHydration.test.tsx`

### 5.3 改 Docker / compose / release / dashboard / alert

1. `python scripts/dev.py compose-config`
2. 检查 [`deploy/compose/compose.yaml`](../../deploy/compose/compose.yaml)
3. 检查 [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) 的 `container-validate`
4. 检查 [`.github/workflows/release.yml`](../../.github/workflows/release.yml)
5. 检查 [`extend/observability/grafana-dashboard.json`](../../extend/observability/grafana-dashboard.json)
6. 检查 [`extend/observability/prometheus-alerts.yml`](../../extend/observability/prometheus-alerts.yml)
7. 必要时用 Compose 真实拉起服务

额外规则：

- 正式发布镜像禁止使用 `latest`
- 手动 release 必须显式提供 `release_tag`
- 导出的 release manifest 应检查 `image_tag / image_ref`

如果只是 Docker Hub 拉取问题，优先改用镜像站复现：

```bash
python scripts/dev.py container-smoke \
  --python-base-image "5ykpmdvdg6to97.xuanyuan.run/library/python:3.13-slim" \
  --node-base-image "5ykpmdvdg6to97.xuanyuan.run/library/node:22-alpine"
```

## 6. 文档同步最小清单

如果这次改动涉及基础设施层，至少同步：

- [../../README.md](../../README.md)
- [../README.md](../README.md)
- [../reference/configuration-reference.md](../reference/configuration-reference.md)
- [../reference/api-reference.md](../reference/api-reference.md)
- [../reference/project-structure.md](../reference/project-structure.md)
- [../reference/backend-maintainer-playbook.md](../reference/backend-maintainer-playbook.md)
- [../testing/testing-guide.md](../testing/testing-guide.md)
- [../architecture/infrastructure-foundations.md](../architecture/infrastructure-foundations.md)

如果这次改的是仓库规范或命令入口，再额外确认：

- `/.editorconfig`
- `/.gitattributes`
- `/scripts/dev.py`

## 7. 推荐阅读

- [quick-start.md](quick-start.md)
- [../reference/project-structure.md](../reference/project-structure.md)
- [../testing/testing-guide.md](../testing/testing-guide.md)
- [../architecture/infrastructure-foundations.md](../architecture/infrastructure-foundations.md)
