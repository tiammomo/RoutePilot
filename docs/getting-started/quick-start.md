# Quick Start

这份文档面向第一次本地运行 moyuan-travel-agent 的开发者，默认环境为 macOS / Linux / Windows 终端。

## 前置条件

- Python 3.13+
- Node.js 20+
- uv
- npm
- 一份可用的 LLM 配置
- Docker / Docker Compose（可选）

## 1. 安装 Python 依赖

```bash
uv python install 3.13
uv venv .venv --python 3.13
python scripts/bootstrap.py
uv pip install -r requirements-dev.txt
```

当前本地开发噪音约定是：

- `.venv` 保留在项目根目录
- `pytest / mypy / Ruff` 的缓存统一写到 `.cache/`

安装完成后，建议先看一眼统一命令入口：

```bash
python scripts/dev.py help
python scripts/dev.py backend-dev
python scripts/dev.py frontend-dev
python scripts/dev.py backend-test --pytest-slice unit
```

如果你只是想最低成本跑起来，不打算本地执行 `ruff / mypy / pip-audit`，也可以只安装：

```bash
uv pip install -r requirements.txt
```

## 2. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

## 3. 准备模型配置

```bash
python scripts/bootstrap.py --skip-frontend
```

根据你的模型服务填写：

- `provider`
- `api_base`
- `api_key`
- `model`
- `default_model`

更多配置说明见 [../reference/configuration-reference.md](../reference/configuration-reference.md)。

`server_config.yaml` 建议至少确认这些字段：

- `web.host`
- `web.port`
- `frontend.port`
- `middleware.request_timeout_seconds`
- `middleware.rate_limit_max_requests`
- `observability.metrics_enabled`
- `startup.fail_fast_validation`

## 4. 启动后端 API

```bash
python scripts/dev.py backend-dev
```

启动成功后可访问：

- `http://localhost:38083/api/health`
- `http://localhost:38083/api/ready`
- `http://localhost:38083/api/metrics`
- `http://localhost:38083/rapidoc`

## 5. 启动前端

```bash
python scripts/dev.py frontend-dev
```

启动成功后访问：

- `http://localhost:33003`

## 6. Docker Compose 启动（可选）

如果想跳过本地手动拉起两个进程，直接以统一容器方式联调：

```bash
docker compose --file deploy/compose/compose.yaml up --build
```

如果要同时把 Prometheus 和 Grafana 也拉起来，方便看 dashboard 和 alert 资产：

```bash
docker compose --file deploy/compose/compose.yaml --profile observability up --build
```

Compose 默认会：

- 暴露前端 `33003`
- 暴露后端 `38083`
- 挂载 `backend/config/`、`data/`、`logs/`
- 为前端注入 `NEXT_PUBLIC_API_BASE`
- 为后端注入 `MOYUAN_WEB_PORT`、`MOYUAN_FRONTEND_PORT`、`MOYUAN_METRICS_ENABLED`

对应文件：

- [../../deploy/compose/compose.yaml](../../deploy/compose/compose.yaml)
- [../../deploy/docker/backend.Dockerfile](../../deploy/docker/backend.Dockerfile)
- [../../deploy/docker/frontend.Dockerfile](../../deploy/docker/frontend.Dockerfile)
- [../../extend/observability/README.md](../../extend/observability/README.md)

如果你这次改的是端口、环境变量、镜像 build 参数或 observability profile，建议先做一次本地渲染校验：

```bash
python scripts/dev.py compose-config
```

如果当前网络拉取 Docker Hub 较慢，也可以显式指定镜像站：

```bash
python scripts/dev.py compose-up \
  --python-base-image "5ykpmdvdg6to97.xuanyuan.run/library/python:3.13-slim" \
  --node-base-image "5ykpmdvdg6to97.xuanyuan.run/library/node:22-alpine"
```

## 7. 首次体验建议

1. 打开首页后，先确认左侧模型下拉可正常展示
2. 在对话体验中选择 `ReAct` 或 `Plan` 模式
3. 点击“行程约束”，补充预算、亲子、少走路、无车等条件
4. 输入类似下面的问题：

```text
请规划上海周末 2 天轻松游，地铁可达，预算 1500 元以内。
```

5. 观察生成过程中的：
   - 阶段状态
   - 工具调用时间线
   - 最终行程卡
   - 预算滑杆
   - 多方案对比与冲突检测
6. 进入“城市探索”页，尝试按标签筛选并继续生成某座城市的完整方案

## 8. 启动后优先检查

建议启动后先跑这 3 个地址：

```bash
curl http://localhost:38083/api/health
curl http://localhost:38083/api/ready
curl http://localhost:38083/api/metrics
```

判断方法：

- `/api/health`：确认服务已起来
- `/api/ready`：确认配置、数据目录、容器、Chat runtime 真正可用
- `/api/metrics`：确认 Prometheus 指标可被采集

如果 `/api/ready` 返回 `503`，优先检查：

- `backend/config/llm_config.yaml` 是否存在、是否至少有一个 active model
- `data/` 目录是否可写
- `backend/config/server_config.yaml` 是否有非法值
- 启动日志里是否出现 `startup_validation`

如果需要把现场状态导出给维护者排查，建议再执行：

```bash
python scripts/dev.py support-bundle --base-url http://localhost:38083
```

## 9. 常用地址

- Frontend: `http://localhost:33003`
- API: `http://localhost:38083`
- API Docs: `http://localhost:38083/rapidoc`
- Health: `http://localhost:38083/api/health`
- Ready: `http://localhost:38083/api/ready`
- Metrics: `http://localhost:38083/api/metrics`
- Prometheus: `http://localhost:39090`
- Grafana: `http://localhost:33002`

## 10. 常见问题

### API 起不来

先检查：

```bash
curl http://localhost:38083/api/health
curl http://localhost:38083/api/ready
```

再检查：

- Python 虚拟环境是否正确激活
- `backend/config/llm_config.yaml` 是否可读
- `backend/config/server_config.yaml` 是否存在非法端口或路径
- 控制台里是否打印出 `startup_validation`

### 前端能打开但没有回答

优先排查：

- `NEXT_PUBLIC_API_BASE` 是否指向 `http://localhost:38083`
- 浏览器网络面板中 `/api/chat/stream` 是否返回 `text/event-stream`
- `/api/chat/stream` 响应头是否带 `X-Request-ID / X-Trace-ID`
- 后端控制台是否有模型调用失败或工具执行报错
- SSE payload 中是否包含 `request_id / trace_id`

### 城市探索列表不对

优先检查：

- `/api/cities`
- `/api/regions`
- `/api/tags`

### 图片导出失败

常见原因：

- 页面仍在流式生成中
- 浏览器权限或跨域图片资源限制
- 导出目标 DOM 尚未完整渲染

## 11. 下一步阅读

- [development-workflow.md](development-workflow.md)
- [../architecture/system-architecture.md](../architecture/system-architecture.md)
- [../architecture/infrastructure-foundations.md](../architecture/infrastructure-foundations.md)
- [../reference/api-reference.md](../reference/api-reference.md)
