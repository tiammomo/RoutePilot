# Development Workflow

这份文档面向日常开发、联调、提交前自检和基础设施改动同步，默认环境为 Windows + PowerShell。

## 1. 日常开发顺序

1. 激活虚拟环境：`.\.venv\Scripts\activate`
2. 检查配置文件：
   - `config\llm_config.yaml`
   - `config\server_config.yaml`
3. 启动 Web API：

```bash
.\.venv\Scripts\python.exe -m uvicorn moyuan_web.main:app --host 0.0.0.0 --port 38000 --app-dir web
```

4. 启动前端：

```bash
cd frontend
npm run dev
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

根目录的 [`dev.ps1`](/D:/moyuan/moyuan-travel-agent/dev.ps1) 是本地开发、测试和基础设施校验的统一入口，推荐优先使用。

```bash
powershell -ExecutionPolicy Bypass -File .\dev.ps1 help
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
  - `runtime_doctor --json`
  - OpenAPI / SSE snapshot 导出
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
docker compose up --build
docker compose --profile observability up --build
```

在真正启动前，先做一次渲染校验会更稳：

```bash
powershell -ExecutionPolicy Bypass -File .\dev.ps1 compose-config
```

如果当前网络拉取 Docker Hub 较慢，可以直接把镜像站作为基础镜像传进来：

```bash
powershell -ExecutionPolicy Bypass -File .\dev.ps1 compose-up `
  -PythonBaseImage "5ykpmdvdg6to97.xuanyuan.run/library/python:3.13-slim" `
  -NodeBaseImage "5ykpmdvdg6to97.xuanyuan.run/library/node:22-alpine"
```

## 4. 常用命令

### 4.1 后端与前端验证

```bash
python -m pytest tests -m "unit and not local and not external_api" -q
python -m pytest tests -m "local and not external_api" -q
python -m ruff check --config ruff.toml scripts web/moyuan_web
python -m mypy --config-file mypy.ini scripts/export_openapi_snapshot.py scripts/export_release_manifest.py scripts/export_support_bundle.py scripts/export_sse_contract_snapshot.py scripts/runtime_backup.py scripts/runtime_data_utils.py scripts/runtime_doctor.py scripts/runtime_prune.py scripts/runtime_restore.py web/moyuan_web/app_meta.py web/moyuan_web/main.py web/moyuan_web/middleware/__init__.py web/moyuan_web/observability.py web/moyuan_web/routes/chat.py web/moyuan_web/routes/health.py web/moyuan_web/services/share_service.py web/moyuan_web/startup_checks.py
python scripts/docstring_audit.py --strict
python scripts/complexity_budget.py --strict
python scripts/decision_record_audit.py --strict
cd frontend
npm run lint
npm run test:run
npm run build
```

说明：

- `docstring_audit --strict` 现在同时拦截缺失 docstring 和新增低信息量模板 docstring
- 当前存量低信息量项由 `docs/reference/docstring-audit.low-info-baseline.json` 记录，后续改动应只减不增
- `complexity_budget --strict` 会对热点文件执行“只减不增”预算门禁，当前预算基线由 `docs/reference/complexity-budget.json` 记录
- `decision_record_audit --strict` 会检查 `docs/governance/` 下的 ADR / RFC / Design Review 是否包含统一状态和必填章节

### 4.2 运行态与契约维护

```bash
python scripts/runtime_backup.py
python scripts/runtime_doctor.py --json
python scripts/runtime_doctor.py --base-url http://localhost:38000 --strict
python scripts/runtime_prune.py --keep-latest-backups 10 --max-backup-age-days 14
python scripts/export_openapi_snapshot.py
python scripts/export_sse_contract_snapshot.py
python scripts/export_release_manifest.py --git-sha local --git-ref refs/heads/main --owner local
python scripts/export_support_bundle.py --base-url http://localhost:38000
```

### 4.3 对应的统一入口

```bash
powershell -ExecutionPolicy Bypass -File .\dev.ps1 test
powershell -ExecutionPolicy Bypass -File .\dev.ps1 infra-check
powershell -ExecutionPolicy Bypass -File .\dev.ps1 snapshots
powershell -ExecutionPolicy Bypass -File .\dev.ps1 support-bundle
powershell -ExecutionPolicy Bypass -File .\dev.ps1 container-smoke
```

## 5. 提交前检查建议

### 5.1 改 Web API / Agent / startup / observability

1. `/api/health` 正常
2. `/api/ready` 返回 `200`，或者你明确知道为什么是 `503`
3. `/api/metrics` 可访问
4. 跑后端 `unit/local`
5. 跑 `ruff`、`mypy`、`docstring_audit --strict`、`complexity_budget --strict`、`decision_record_audit --strict`
6. 跑 `runtime_doctor --strict`
7. 如改契约，刷新 OpenAPI / SSE 快照

### 5.2 改前端 / SSE / 接口契约

1. `cd frontend && npm run lint`
2. `cd frontend && npm run test:run`
3. `cd frontend && npm run build`
4. 检查 `/api/chat/stream` 是否仍然返回 `text/event-stream`
5. 检查 `X-Request-ID / X-Trace-ID`
6. 如有运行态异常，导出 support bundle

### 5.3 改 Docker / compose / release / dashboard / alert

1. `powershell -ExecutionPolicy Bypass -File .\dev.ps1 compose-config`
2. 检查 [`compose.yaml`](/D:/moyuan/moyuan-travel-agent/compose.yaml)
3. 检查 [`.github/workflows/ci.yml`](/D:/moyuan/moyuan-travel-agent/.github/workflows/ci.yml) 的 `container-validate`
4. 检查 [`.github/workflows/release.yml`](/D:/moyuan/moyuan-travel-agent/.github/workflows/release.yml)
5. 检查 [`ops/observability/grafana-dashboard.json`](/D:/moyuan/moyuan-travel-agent/ops/observability/grafana-dashboard.json)
6. 检查 [`ops/observability/prometheus-alerts.yml`](/D:/moyuan/moyuan-travel-agent/ops/observability/prometheus-alerts.yml)
7. 必要时用 Compose 真实拉起服务

如果只是 Docker Hub 拉取问题，优先改用镜像站复现：

```bash
powershell -ExecutionPolicy Bypass -File .\dev.ps1 container-smoke `
  -PythonBaseImage "5ykpmdvdg6to97.xuanyuan.run/library/python:3.13-slim" `
  -NodeBaseImage "5ykpmdvdg6to97.xuanyuan.run/library/node:22-alpine"
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
- `/dev.ps1`

## 7. 推荐阅读

- [quick-start.md](quick-start.md)
- [../reference/project-structure.md](../reference/project-structure.md)
- [../testing/testing-guide.md](../testing/testing-guide.md)
- [../architecture/infrastructure-foundations.md](../architecture/infrastructure-foundations.md)
