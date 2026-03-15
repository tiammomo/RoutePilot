# Development Workflow

## 日常开发顺序

1. 激活环境：`.\.venv\Scripts\activate`
2. 确认配置：
   - `config\llm_config.yaml`
   - `config\server_config.yaml`
3. 启动 API：

```bash
.\.venv\Scripts\python.exe -m uvicorn shuai_web.main:app --host 0.0.0.0 --port 38000 --app-dir web
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
6. 改动后执行对应测试，并同步相关文档。

## 另一种联调方式：Compose

如果你正在改部署、环境变量、容器网络、Next.js rewrite、readiness、metrics 或 release 相关内容，优先直接跑：

```bash
docker compose up --build
```

如果你这次还要联调 Prometheus/Grafana：

```bash
docker compose --profile observability up --build
```

对应资产：

- [../../compose.yaml](../../compose.yaml)
- [../../Dockerfile.backend](../../Dockerfile.backend)
- [../../frontend/Dockerfile](../../frontend/Dockerfile)
- [../../ops/observability/README.md](../../ops/observability/README.md)

## 常用命令

```bash
# 后端 unit
python -m pytest tests -m "unit and not local and not external_api" -q

# 后端本地 smoke
python -m pytest tests -m "local and not external_api" -q

# Python 注释覆盖率
python scripts/docstring_audit.py --strict

# 运行态维护
python scripts/runtime_backup.py
python scripts/runtime_doctor.py --json
python scripts/runtime_doctor.py --base-url http://localhost:38000 --strict
python scripts/runtime_prune.py --keep-latest-backups 10 --max-backup-age-days 14
python scripts/export_support_bundle.py --base-url http://localhost:38000

# 契约与发布资产
python scripts/export_openapi_snapshot.py
python scripts/export_sse_contract_snapshot.py
python scripts/export_release_manifest.py --git-sha local --git-ref refs/heads/main --owner local

# benchmark / golden / quality gate
python scripts/agent_benchmark.py --output-dir docs/benchmarks
python scripts/agent_golden_eval.py --dataset tests/golden/agent_react_golden.json --report docs/benchmarks/agent_golden_eval_latest.json --min-pass-rate 0.0
python scripts/agent_quality_gate.py --golden-report docs/benchmarks/agent_golden_eval_latest.json --benchmark-report docs/benchmarks/agent_benchmark_latest.json --baseline-benchmark-report docs/benchmarks/agent_benchmark_baseline.json

# 前端
cd frontend
npm run lint
npm run test:run
npm run build
```

## 推荐提交前检查

### 改 Web / Agent / startup / observability

1. `/api/health` 正常
2. `/api/ready` 返回 `200`，或者你明确知道为什么是 `503`
3. `/api/metrics` 可访问
4. `python -m pytest tests -m "unit and not local and not external_api" -q`
5. `python -m pytest tests -m "local and not external_api" -q`
6. `python scripts/docstring_audit.py --strict`
7. `python scripts/runtime_doctor.py --base-url http://localhost:38000 --strict`

### 改前端 / SSE / 接口契约

1. `cd frontend && npm run lint`
2. `cd frontend && npm run test:run`
3. `cd frontend && npm run build`
4. 检查 `/api/chat/stream` 是否仍返回 `text/event-stream`
5. 检查 `X-Request-ID / X-Trace-ID`
6. 如有运行态异常，补导出 support bundle

### 改 CI / release / dashboard / alert

1. 检查 [`.github/workflows/ci.yml`](/D:/projects/shuai/ShuaiTravelAgent/.github/workflows/ci.yml)
2. 检查 [`.github/workflows/release.yml`](/D:/projects/shuai/ShuaiTravelAgent/.github/workflows/release.yml)
3. 检查 [`web/shuai_web/observability.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/observability.py)
4. 检查 [`web/shuai_web/routes/health.py`](/D:/projects/shuai/ShuaiTravelAgent/web/shuai_web/routes/health.py)
5. 检查 [`ops/observability/grafana-dashboard.json`](/D:/projects/shuai/ShuaiTravelAgent/ops/observability/grafana-dashboard.json)
6. 检查 [`ops/observability/prometheus-alerts.yml`](/D:/projects/shuai/ShuaiTravelAgent/ops/observability/prometheus-alerts.yml)
7. 检查 [`scripts/export_support_bundle.py`](/D:/projects/shuai/ShuaiTravelAgent/scripts/export_support_bundle.py)

## 文档同步最小清单

如果这次改动涉及基础设施层，至少同步：

- [../../README.md](../../README.md)
- [../README.md](../README.md)
- [../reference/configuration-reference.md](../reference/configuration-reference.md)
- [../reference/api-reference.md](../reference/api-reference.md)
- [../reference/backend-maintainer-playbook.md](../reference/backend-maintainer-playbook.md)
- [../testing/testing-guide.md](../testing/testing-guide.md)
- [../architecture/infrastructure-foundations.md](../architecture/infrastructure-foundations.md)
