# Testing Guide

## 测试分层

### 1. 后端 pytest markers

当前 marker 定义见：

- `pytest.ini`
- `tests/conftest.py`

主要分层：

- `unit`
  - 纯逻辑、模块级、脚本级测试。
- `integration`
  - 跨层协作测试，覆盖 Web API、Agent、存储和事件链路。
- `local`
  - 本地 ASGI smoke、本地运行依赖、自检脚本与契约快照测试。
- `external_api`
  - 依赖外部 provider 或在线服务。
- `quality`
  - 与 benchmark、golden eval、quality gate 相关。

### 2. 前端验证

目录：`frontend/`

推荐命令：

```bash
cd frontend
npm run lint
npm run test:run
npm run build
```

说明：

- `npm run lint` 当前承担 TypeScript 类型检查职责。
- `npm run test:run` 主要保护流式消息处理、组件行为和工具栏逻辑。
- `npm run build` 用于发现 SSR、rewrite、路由和编译期问题。

## 推荐的本地回归顺序

### 1. 日常前端改动

```bash
cd frontend
npm run lint
npm run test:run
npm run build
```

### 2. 改 Web API、startup、health、metrics、trace、SSE 协议

```bash
python -m pytest tests -m "unit and not local and not external_api" -q
python -m pytest tests -m "local and not external_api" -q
python scripts/docstring_audit.py --strict
mypy --config-file mypy.ini scripts/export_openapi_snapshot.py scripts/export_release_manifest.py scripts/export_support_bundle.py scripts/export_sse_contract_snapshot.py scripts/runtime_backup.py scripts/runtime_data_utils.py scripts/runtime_doctor.py scripts/runtime_prune.py scripts/runtime_restore.py web/shuai_web/app_meta.py web/shuai_web/main.py web/shuai_web/middleware/__init__.py web/shuai_web/observability.py web/shuai_web/routes/chat.py web/shuai_web/routes/health.py web/shuai_web/services/share_service.py web/shuai_web/startup_checks.py
cd frontend
npm run lint
npm run build
```

### 3. 改运行时运维脚本、契约快照、发布与观测资产

```bash
python -m pytest tests/test_runtime_data_lifecycle_unit.py tests/test_runtime_doctor_unit.py tests/test_export_openapi_snapshot_script_unit.py tests/test_export_sse_contract_snapshot_script_unit.py tests/test_export_release_manifest_script_unit.py tests/test_observability_assets_unit.py -q
python scripts/export_openapi_snapshot.py
python scripts/export_sse_contract_snapshot.py
python scripts/export_release_manifest.py --git-sha local --git-ref refs/heads/main --owner local
python scripts/runtime_doctor.py --json
python scripts/export_support_bundle.py
```

### 4. 发版前建议

```bash
python -m pytest tests -m "unit and not local and not external_api" -q
python -m pytest tests -m "local and not external_api" -q
python scripts/docstring_audit.py --strict
python scripts/export_openapi_snapshot.py
python scripts/export_sse_contract_snapshot.py
python scripts/export_release_manifest.py --git-sha local --git-ref refs/tags/dev --owner local
cd frontend
npm run lint
npm run test:run
npm run build
cd ..
python scripts/agent_benchmark.py --output-dir docs/benchmarks
python scripts/agent_golden_eval.py --dataset tests/golden/agent_react_golden.json --report docs/benchmarks/agent_golden_eval_latest.json --min-pass-rate 0.0
python scripts/agent_quality_gate.py --golden-report docs/benchmarks/agent_golden_eval_latest.json --benchmark-report docs/benchmarks/agent_benchmark_latest.json --baseline-benchmark-report docs/benchmarks/agent_benchmark_baseline.json
```

## 契约快照

当前已经纳入仓库和 CI 的契约快照包括：

```bash
python scripts/export_openapi_snapshot.py
python scripts/export_sse_contract_snapshot.py
```

产物：

- `docs/reference/openapi.snapshot.json`
- `docs/reference/sse-contract.snapshot.json`

建议在这些场景同步刷新：

- 改 `/api/health`、`/api/ready`、`/api/live`
- 改 `/api/chat/stream` 的事件顺序、事件类型或字段
- 改 `session`、`share`、`model`、`city` 等返回结构
- 改 OpenAPI schema 或响应模型

## 运行时维护脚本

当前运行时基础设施脚本：

```bash
python scripts/runtime_backup.py
python scripts/runtime_restore.py --archive <archive.zip>
python scripts/runtime_prune.py --keep-latest 5
python scripts/runtime_doctor.py --json
python scripts/runtime_doctor.py --base-url http://localhost:38000 --strict
python scripts/export_support_bundle.py --base-url http://localhost:38000
```

这些脚本主要保护：

- `data/` 运行时资产备份与恢复
- `sessions`、`agent_memory`、`share_links`、`checkpoint` 的生命周期维护
- OpenAPI / SSE 快照存在性与可解析性
- 本地 `/api/health`、`/api/ready`、`/api/metrics` 可达性

## 静态质量门禁

当前后端静态门禁包括：

```bash
python scripts/docstring_audit.py --strict
ruff check --config ruff.toml scripts web/shuai_web
mypy --config-file mypy.ini scripts/export_openapi_snapshot.py scripts/export_release_manifest.py scripts/export_support_bundle.py scripts/export_sse_contract_snapshot.py scripts/runtime_backup.py scripts/runtime_data_utils.py scripts/runtime_doctor.py scripts/runtime_prune.py scripts/runtime_restore.py web/shuai_web/app_meta.py web/shuai_web/main.py web/shuai_web/middleware/__init__.py web/shuai_web/observability.py web/shuai_web/routes/chat.py web/shuai_web/routes/health.py web/shuai_web/services/share_service.py web/shuai_web/startup_checks.py
```

说明：

- `docstring_audit.py --strict` 拦截新增缺失 docstring 的 Python 文件。
- `ruff` 当前主要负责基础语法与常见错误检查。
- `mypy` 当前重点覆盖发布、运维、观测和 Web 主链上的关键脚本与模块。

## 关键测试文件和它们在保护什么

### Web / API / startup

- `tests/test_api_smoke_local.py`
  - 保护 `/`、`/api/health`、`/api/ready`、`/api/live`、`/api/metrics`
  - 同时覆盖 build metadata 是否暴露正确
- `tests/test_chat_stream_local.py`
  - 保护 `/api/chat/stream`
  - 保护 SSE headers、payload 里的 `request_id / trace_id`

### 运行时基础设施

- `tests/test_runtime_data_lifecycle_unit.py`
  - 保护 backup / restore / prune 行为
- `tests/test_runtime_doctor_unit.py`
  - 保护 runtime doctor 的离线和在线检查逻辑
- `tests/test_share_service_unit.py`
  - 保护 share 数据原子写与恢复策略

### 契约与发布资产

- `tests/test_export_openapi_snapshot_script_unit.py`
  - 保护 OpenAPI 快照导出脚本
- `tests/test_export_sse_contract_snapshot_script_unit.py`
  - 保护 SSE 契约快照导出脚本
- `tests/test_export_release_manifest_script_unit.py`
  - 保护 release manifest 结构和镜像命名
- `tests/test_export_support_bundle_script_unit.py`
  - 保护 support bundle 归档结构与诊断输出
- `tests/test_observability_assets_unit.py`
  - 保护 Grafana dashboard 和 Prometheus alert 资产

## CI 当前如何跑

CI 配置见：`.github/workflows/ci.yml`

后端主要步骤：

1. 安装 Python 依赖与静态分析工具
2. 准备 `llm_config.yaml` 和 `server_config.yaml`
3. 跑 `unit` 与 `local` pytest
4. 跑 `docstring_audit.py --strict`
5. 跑 `ruff` 和 `mypy`
6. 跑 `pip-audit` 和 `gitleaks`
7. 导出并校验 OpenAPI / SSE 快照
8. 跑 benchmark / golden eval / trend / quality gate
9. 上传质量产物并写入 Step Summary

前端主要步骤：

1. `npm ci`
2. `npm run lint`
3. `npm run test:run`
4. `npm run build`

## CI 产物与排查路径

当前后端会上传这些质量产物：

- `artifacts/ci/pip-audit-report.json`
- `artifacts/ci/gitleaks-report.json`
- `docs/benchmarks/agent_benchmark_latest.json`
- `docs/benchmarks/agent_benchmark_latest.md`
- `docs/benchmarks/agent_benchmark_trend_latest.md`
- `docs/benchmarks/agent_golden_eval_latest.json`

如果 CI 失败，推荐按这个顺序排查：

1. 是 `unit` 失败还是 `local` 失败
2. `/api/ready` 或 `/api/metrics` 是否在 smoke 中失败
3. `ruff` / `mypy` 是否拦住了基础设施脚本
4. OpenAPI / SSE 快照是否没有同步更新
5. `pip-audit` 或 `gitleaks` 是否发现了安全问题
6. benchmark / golden eval / quality gate 是否回归
7. Step Summary 是否已经给出具体失败层

## 发布与观测资产验证

当前发布与观测资产包括：

- `.github/workflows/release.yml`
- `scripts/export_release_manifest.py`
- `scripts/export_support_bundle.py`
- `ops/observability/grafana-dashboard.json`
- `ops/observability/prometheus-alerts.yml`
- `ops/observability/prometheus.yml`

推荐最小验证：

```bash
python scripts/export_release_manifest.py --git-sha local --git-ref refs/tags/dev --owner local
python scripts/export_support_bundle.py
python -m pytest tests/test_export_release_manifest_script_unit.py tests/test_export_support_bundle_script_unit.py tests/test_observability_assets_unit.py -q
```

## 常见失败点

### 1. 编码问题

典型表现：

- `invalid utf-8 sequence`
- 文档或源代码在 CI 中读取失败

建议：

- 统一使用 UTF-8 保存
- 不要通过乱码终端直接覆盖中文源码或文档
- 改动后至少跑一次 `npm run build` 或目标 pytest

### 2. readiness / 配置问题

优先检查：

- `config/llm_config.yaml` 是否存在且可解析
- `config/server_config.yaml` 是否存在且可解析
- `/api/ready` 失败的是哪一项 check
- `SHUAI_FAIL_FAST_STARTUP_VALIDATION` 是否使启动直接失败

### 3. SSE / 流式测试不稳定

优先检查：

- `/api/chat/stream` 是否返回 `text/event-stream`
- headers 是否包含 `X-Request-ID / X-Trace-ID`
- SSE payload 是否带 `request_id / trace_id`
- 模型 provider 或工具调用是否超时

### 4. 契约快照失败

优先检查：

- 改动后是否重新执行了快照导出脚本
- 新字段是否同步更新了文档和测试断言
- SSE 事件顺序或类型是否发生变化

### 5. 发布资产失败

优先检查：

- `APP_VERSION`、`APP_BUILD_SHA`、`APP_BUILD_CREATED_AT` 是否注入
- `export_release_manifest.py` 是否能拿到 frontend/backend 版本
- workflow 中的镜像命名是否和 owner/tag 一致

## 浏览器联调建议

如果需要做真实界面验收，建议至少覆盖：

- 首页是否正常打开
- `/api/chat/stream` 是否返回 `text/event-stream`
- 前端日志是否能看到 request / trace id
- 城市探索和 session 列表是否能正常加载
- 分享、导出、路线预览是否仍然可用
