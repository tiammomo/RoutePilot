# Testing Guide

## 1. 测试分层

### 1.1 后端 pytest markers

当前 marker 定义见：

- [`pytest.ini`](/D:/moyuan/moyuan-travel-agent/pytest.ini)
- [`tests/conftest.py`](/D:/moyuan/moyuan-travel-agent/tests/conftest.py)

主要分层：

- `unit`
  - 纯逻辑、模块级、脚本级测试
- `integration`
  - 跨层协作测试，覆盖 Web API、Agent、存储和事件链路
- `local`
  - 本地 ASGI smoke、本地运行依赖、自检脚本与契约快照测试
- `external_api`
  - 依赖外部 provider 或在线服务
- `quality`
  - benchmark、golden eval、quality gate

### 1.2 前端验证

目录：`frontend/`

推荐命令：

```bash
cd frontend
npm run lint
npm run test:run
npm run build
```

## 2. 推荐的本地回归顺序

### 2.1 优先走统一入口

```bash
uv pip install -r requirements-dev.txt
powershell -ExecutionPolicy Bypass -File .\dev.ps1 help
powershell -ExecutionPolicy Bypass -File .\dev.ps1 test
powershell -ExecutionPolicy Bypass -File .\dev.ps1 infra-check
powershell -ExecutionPolicy Bypass -File .\dev.ps1 compose-config
powershell -ExecutionPolicy Bypass -File .\dev.ps1 container-smoke
```

### 2.2 改 Web API、startup、health、metrics、trace、SSE 协议

```bash
python -m pytest tests -m "unit and not local and not external_api" -q
python -m pytest tests -m "local and not external_api" -q
python -m pytest tests/test_agent_runtime_phase1_unit.py tests/test_agent_subagent_phase2_unit.py tests/test_chat_stream_local.py tests/test_chat_service_health_metrics_unit.py tests/test_langchain_1x_agent_unit.py -q
python -m ruff check --config ruff.toml scripts web/moyuan_web
python scripts/docstring_audit.py --strict
python scripts/complexity_budget.py --strict
python scripts/decision_record_audit.py --strict
python -m mypy --config-file mypy.ini scripts/export_openapi_snapshot.py scripts/export_release_manifest.py scripts/export_support_bundle.py scripts/export_sse_contract_snapshot.py scripts/runtime_backup.py scripts/runtime_data_utils.py scripts/runtime_doctor.py scripts/runtime_prune.py scripts/runtime_restore.py web/moyuan_web/app_meta.py web/moyuan_web/main.py web/moyuan_web/middleware/__init__.py web/moyuan_web/observability.py web/moyuan_web/routes/chat.py web/moyuan_web/routes/health.py web/moyuan_web/services/share_service.py web/moyuan_web/startup_checks.py
cd frontend
npm run lint
npm run build
```

说明：

- `python scripts/docstring_audit.py --strict` 当前会同时检查缺失 docstring 与新增低信息量 docstring
- 历史存量低信息量项通过 `docs/reference/docstring-audit.low-info-baseline.json` 管理，后续变更应避免新增
- `python scripts/complexity_budget.py --strict` 会对热点文件执行“只减不增”预算门禁，避免复杂区重新无序膨胀
- `python scripts/decision_record_audit.py --strict` 会审计 ADR / RFC / Design Review 的基础结构，保证大改动有稳定记录入口

### 2.3 改运行维护脚本、契约快照、发布与观测资产

```bash
python -m pytest tests/test_runtime_data_lifecycle_unit.py tests/test_runtime_doctor_unit.py tests/test_export_openapi_snapshot_script_unit.py tests/test_export_sse_contract_snapshot_script_unit.py tests/test_export_release_manifest_script_unit.py tests/test_export_support_bundle_script_unit.py tests/test_observability_assets_unit.py -q
python scripts/export_openapi_snapshot.py
python scripts/export_sse_contract_snapshot.py
python scripts/export_release_manifest.py --git-sha local --git-ref refs/heads/main --owner local
python scripts/runtime_doctor.py --json
python scripts/export_support_bundle.py
```

### 2.4 改 Docker / compose / release

```bash
powershell -ExecutionPolicy Bypass -File .\dev.ps1 compose-config
docker build -f Dockerfile.backend .
docker build -f frontend/Dockerfile ./frontend
```

如果 Docker Hub 拉取较慢，可以改用镜像站作为基础镜像：

```bash
powershell -ExecutionPolicy Bypass -File .\dev.ps1 container-smoke `
  -PythonBaseImage "5ykpmdvdg6to97.xuanyuan.run/library/python:3.13-slim" `
  -NodeBaseImage "5ykpmdvdg6to97.xuanyuan.run/library/node:22-alpine"
```

## 3. 契约快照

当前已经纳入仓库和 CI 的契约快照包括：

```bash
python scripts/export_openapi_snapshot.py
python scripts/export_sse_contract_snapshot.py
```

产物：

- [`docs/reference/openapi.snapshot.json`](/D:/moyuan/moyuan-travel-agent/docs/reference/openapi.snapshot.json)
- [`docs/reference/sse-contract.snapshot.json`](/D:/moyuan/moyuan-travel-agent/docs/reference/sse-contract.snapshot.json)

## 4. 运行维护脚本

```bash
python scripts/runtime_backup.py
python scripts/runtime_restore.py --archive <archive.zip>
python scripts/runtime_prune.py --keep-latest 5
python scripts/runtime_doctor.py --json
python scripts/runtime_doctor.py --base-url http://localhost:38000 --strict
python scripts/export_support_bundle.py --base-url http://localhost:38000
```

## 5. 静态质量门禁

```bash
python scripts/docstring_audit.py --strict
python scripts/complexity_budget.py --strict
python scripts/decision_record_audit.py --strict
ruff check --config ruff.toml scripts web/moyuan_web
mypy --config-file mypy.ini scripts/export_openapi_snapshot.py scripts/export_release_manifest.py scripts/export_support_bundle.py scripts/export_sse_contract_snapshot.py scripts/runtime_backup.py scripts/runtime_data_utils.py scripts/runtime_doctor.py scripts/runtime_prune.py scripts/runtime_restore.py web/moyuan_web/app_meta.py web/moyuan_web/main.py web/moyuan_web/middleware/__init__.py web/moyuan_web/observability.py web/moyuan_web/routes/chat.py web/moyuan_web/routes/health.py web/moyuan_web/services/share_service.py web/moyuan_web/startup_checks.py
```

这条 docstring 门禁不再只是“有没有写”，而是同时检查“写得是不是还有信息量”；complexity budget gate 会继续保护热点复杂文件不被无序长回去；decision record audit 则保证大改动不会再次退回到“只有 PR 描述、没有正式设计记录”的状态。

## 6. 关键测试文件保护什么

- [`tests/test_api_smoke_local.py`](/D:/moyuan/moyuan-travel-agent/tests/test_api_smoke_local.py)
  - 保护 `/`、`/api/health`、`/api/ready`、`/api/live`、`/api/metrics`
- [`tests/test_chat_stream_local.py`](/D:/moyuan/moyuan-travel-agent/tests/test_chat_stream_local.py)
  - 保护 `/api/chat/stream` 和 `request_id / trace_id`
- [`tests/test_agent_runtime_phase1_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_agent_runtime_phase1_unit.py)
  - 保护 phase-1 `AgentRuntime / Skills / Artifact` 兼容层
- [`tests/test_agent_subagent_phase2_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_agent_subagent_phase2_unit.py)
  - 保护 phase-2 `Research / Planning / Verification` subagent 映射与事件编排
- [`tests/test_runtime_data_lifecycle_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_runtime_data_lifecycle_unit.py)
  - 保护 backup / restore / prune
- [`tests/test_runtime_doctor_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_runtime_doctor_unit.py)
  - 保护 runtime doctor
- [`tests/test_export_openapi_snapshot_script_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_export_openapi_snapshot_script_unit.py)
  - 保护 OpenAPI 快照导出
- [`tests/test_export_sse_contract_snapshot_script_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_export_sse_contract_snapshot_script_unit.py)
  - 保护 SSE 快照导出
- [`tests/test_export_release_manifest_script_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_export_release_manifest_script_unit.py)
  - 保护 release manifest
- [`tests/test_export_support_bundle_script_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_export_support_bundle_script_unit.py)
  - 保护 support bundle
- [`tests/test_observability_assets_unit.py`](/D:/moyuan/moyuan-travel-agent/tests/test_observability_assets_unit.py)
  - 保护 dashboard 和 alert 资产

## 7. CI 当前如何跑

CI 配置见：[`.github/workflows/ci.yml`](/D:/moyuan/moyuan-travel-agent/.github/workflows/ci.yml)

主要任务包括：

1. backend unit / local
2. docstring audit
3. `ruff` / `mypy`
4. `pip-audit` / `gitleaks`
5. OpenAPI / SSE 快照校验
6. benchmark / golden eval / quality gate
7. frontend lint / test / build
8. `container-validate`

`container-validate` 会执行：

- 导出 release manifest
- `docker compose config`
- `docker compose --profile observability config`
- `docker build -f Dockerfile.backend .`
- `docker build -f frontend/Dockerfile ./frontend`
- 上传 `deployment-validation-artifacts`

## 8. CI 产物与排查路径

关键产物：

- `artifacts/ci/pip-audit-report.json`
- `artifacts/ci/gitleaks-report.json`
- `artifacts/ci/compose-default.rendered.yaml`
- `artifacts/ci/compose-observability.rendered.yaml`
- `artifacts/release/release-manifest.json`
- `docs/benchmarks/agent_benchmark_latest.json`
- `docs/benchmarks/agent_golden_eval_latest.json`

排查顺序建议：

1. 先看 `unit` 还是 `local` 失败
2. 再看 `ruff` / `mypy`
3. 再看契约快照是否未同步
4. 再看 `pip-audit` / `gitleaks`
5. 最后看 `container-validate` 是否卡在 compose 渲染或镜像构建
6. 如果只是 Docker Hub 拉取失败，先改用镜像站再复现一遍本地构建

## 9. 常见失败点

- 编码与换行问题：优先检查 [`.editorconfig`](/D:/moyuan/moyuan-travel-agent/.editorconfig) 和 [`.gitattributes`](/D:/moyuan/moyuan-travel-agent/.gitattributes)
- readiness / 配置问题：优先检查 `config/llm_config.yaml`、`config/server_config.yaml` 和 `/api/ready`
- SSE 流式不稳定：优先检查 `/api/chat/stream`、headers、payload 和 timeout
- 契约快照失败：优先检查是否刷新 OpenAPI / SSE 快照
- 容器验证失败：优先检查 `compose.yaml`、Dockerfile 和 release manifest

## 10. 推荐阅读

- [../getting-started/development-workflow.md](../getting-started/development-workflow.md)
- [../architecture/infrastructure-foundations.md](../architecture/infrastructure-foundations.md)
- [../reference/backend-maintainer-playbook.md](../reference/backend-maintainer-playbook.md)
## Frontend Phase 3 Coverage

The frontend artifact-first slice is currently covered by:

- [`frontend/tests/unit/components/MessageList.test.tsx`](/D:/moyuan/moyuan-travel-agent/frontend/tests/unit/components/MessageList.test.tsx)
  - protects assistant rendering, diagnostics, markdown blocks, and artifact-backed toolkit summary
- [`frontend/tests/unit/utils/agentArtifacts.test.ts`](/D:/moyuan/moyuan-travel-agent/frontend/tests/unit/utils/agentArtifacts.test.ts)
  - protects artifact patch merge semantics
- [`frontend/tests/unit/utils/travelPlan.test.ts`](/D:/moyuan/moyuan-travel-agent/frontend/tests/unit/utils/travelPlan.test.ts)
  - protects free-text itinerary fallback parsing

Recommended local regression after changing artifact/subagent UI behavior:

```bash
cd frontend
npm run lint
npm run test:run
npm run build
```
## Session Hydration Coverage

这轮改动新增了两类验证：

- 后端本地 smoke
  - `tests/test_chat_stream_local.py`
  - 验证 SSE 结束后 assistant message 已持久化 `diagnostics.artifact` 与 `diagnostics.subagentEvents`
- 前端单测
  - `frontend/tests/unit/context/AppContext.test.tsx`
  - `frontend/tests/unit/utils/sessionMessages.test.ts`
  - 验证刷新恢复时 `AppContext` 能重新拉取 session messages，并让 artifact 继续驱动界面
