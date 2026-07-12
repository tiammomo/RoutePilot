# 本地开发指南

本文面向需要修改 Web、API、Agent、RAG 或契约的开发者。推荐使用 Compose 运行完整状态服务，使用本机工具执行快速测试。

## 工具基线

- Docker Engine 与 Docker Compose v2；
- Python 3.13；
- Node.js 24.17；
- npm；
- Git。

安装本机依赖：

```bash
python -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements-dev.txt
npm ci --prefix apps/web --ignore-scripts
```

## 启动完整本地栈

创建只属于本机的配置文件：

```bash
cp deploy/compose/v1.env.example deploy/compose/.env.v1.local
chmod 600 deploy/compose/.env.v1.local
```

为每个空密码、BFF secret 和 share pepper 分别生成随机值，不得复用：

```bash
openssl rand -hex 32
```

OIDC cookie key 使用无填充 base64url：

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"
```

本地 Compose 不要求 OIDC client secret/cookie key；预发覆盖要求它们。高德、LLM 和 embedding 配置均可留空，系统会使用显式降级路径。

先渲染，再启动：

```bash
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml config --quiet
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml up --build --detach
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml ps
```

不要使用 `down --volumes` 处理普通启动问题，该命令会永久删除本地 PostgreSQL 和 Redis volume。

## 常用开发循环

只调试 Web 时，可以保留 Compose API，并在本机启动 Next.js：

```bash
cp apps/web/.env.example apps/web/.env.local
npm --prefix apps/web run dev
```

如启用本地开发身份，Web 和 API 必须使用相同的 `ROUTEPILOT_V1_DEV_BFF_SECRET`，且该路径只允许 local/dev 环境。

运行 API 的正式组合入口：

```bash
PYTHONPATH=backend:. .venv/bin/uvicorn moyuan_web.main:app \
  --host 127.0.0.1 --port 38083
```

本机 API 仍需要有效的 PostgreSQL、Redis、身份和执行模式环境变量。日常开发更推荐 Compose，避免不完整的环境组合。

## 分领域验证

```bash
python scripts/v1_quality_gate.py --only backend --only a2a --skip-web-build
python scripts/v1_quality_gate.py --only docs
npm --prefix apps/web run typecheck
npm --prefix apps/web run test
npm --prefix apps/web run build
git diff --check
```

完整提交前门禁：

```bash
python scripts/v1_quality_gate.py
```

真实 PostgreSQL/Redis 集成测试默认由 CI 执行。不要为了让本机测试变绿而把 integration marker 改成单元测试或引入内存兼容分支。

## 数据库变更

1. 只在 `deploy/migrations/versions/` 添加 Alembic revision；
2. 同步修改 SQLAlchemy Core table 定义；
3. 检查 grants 和 RLS；
4. 执行 migration tests 和离线 SQL 渲染；
5. 不得在应用启动中调用 `create_all`。

```bash
python scripts/v1_quality_gate.py --only migration
```

## 契约变更

Artifact 或 public event 变更必须同时更新 Pydantic、JSON Schema、生成的 TypeScript 类型和 contract tests。完整步骤见 [Artifact 与事件契约扩展](artifact-contracts.md)。

## 工作区清理

```bash
python scripts/clean_workspace.py
python scripts/clean_workspace.py --apply
```

清理器只删除审核过的缓存、日志和可再生构建结果，不删除 env、虚拟环境、依赖、数据库 volume 或用户数据。

遇到 Compose、migration、Worker 或 OIDC 问题时，按[故障排查手册](../operations/troubleshooting.md)收集证据，不要先删除数据卷。
