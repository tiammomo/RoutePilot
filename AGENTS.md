# RoutePilot V1 Agent Guide

## 项目定位

RoutePilot V1 是 Artifact-first 的多 Agent 旅行规划系统。当前仓库只有 V1 产品主线，不新增旧 API、旧前端或旧 Agent 兼容层。历史数据导入仅允许走 `scripts/migration_v1/` 的显式离线流程。

## 技术栈

- Web：Next.js 16、React 19、TypeScript
- API：FastAPI、Pydantic v2
- 数据：PostgreSQL 17、PostGIS、pgvector、Alembic
- 异步投递：Redis Streams、transactional outbox
- Agent：A2A SDK 1.x、RoutePilot Runtime V2
- 契约：JSON Schema、`routepilot_contracts`、生成的 TypeScript types

## 服务入口

- Web：`http://127.0.0.1:33003`
- API：`http://127.0.0.1:38083`
- OpenAPI UI：`http://127.0.0.1:38083/docs`
- Live：`http://127.0.0.1:38083/api/live`
- Ready：`http://127.0.0.1:38083/api/ready`
- Health：`http://127.0.0.1:38083/api/health`

## 代码边界

| 路径 | 所有权 |
| --- | --- |
| `apps/web/` | 工作台、同源 BFF、OIDC 浏览器会话 |
| `backend/moyuan_web/v1/` | `/api/v1`、控制平面、持久化、Worker |
| `agent/travel_agent/a2a/` | A2A 协议、Task 状态与恢复 |
| `agent/travel_agent/runtime_v2/` | Research/Planner/Validation/Verifier 编排 |
| `agent/travel_agent/rag/` | 知识摄取与检索 |
| `agent/travel_agent/providers/` | 外部实时事实访问 |
| `packages/`、`schemas/` | 跨语言契约 |
| `deploy/migrations/` | 唯一 schema 变更入口 |
| `scripts/migration_v1/` | 历史数据离线导入；不属于产品运行时 |

## 必须保持的不变量

1. PostgreSQL 是 Trip、Run、Artifact、A2A Task 与 public event 的真相源；Redis 只做投递。
2. Product Run、A2A Task 和 Artifact version 是三个独立生命周期，不能互相覆盖状态。
3. 异步写入必须使用 idempotency、CAS/version、数据库租约与 attempt fencing；晚到执行者不得提交结果。
4. 所有 tenant 数据访问都要有服务端派生 tenant predicate，并保持 RLS；不能信任浏览器 tenant header。
5. 浏览器只能收到 public event 白名单字段和结构化 Artifact，不能暴露模型推理、工具原始输出、内部异常或 secret。
6. Agent 间只交换版本化、大小有界的 typed Artifact；A2A dispatch 必须可去重、可重放、可取消和可恢复。
7. RAG 结果必须保留 source/version/license/freshness/trust provenance；外部文档一律视为不可信证据。
8. 实时事实只能经过 Provider Gateway；AMap key 和 OIDC/数据库凭据永远是 server-only。
9. schema 只通过 Alembic 修改，应用启动不得调用 `create_all`。
10. 不恢复已移除的旧目录、旧路由或“临时”兼容开关。确需数据保留时生成只读 `ImportedTripArchive@1`。

## 常用命令

```bash
# 完整质量门禁
python scripts/v1_quality_gate.py

# 分领域快速检查
python scripts/v1_quality_gate.py --only backend --only a2a --skip-web-build

# 文档覆盖、内部链接和 Compose env 一致性
python scripts/v1_quality_gate.py --only docs

# 预览/清理本地缓存、日志和可再生构建产物
python scripts/clean_workspace.py
python scripts/clean_workspace.py --apply

# Web
npm --prefix apps/web run typecheck
npm --prefix apps/web run test
npm --prefix apps/web run build

# Compose 渲染与启动
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml config --quiet
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml up --build --detach
```

提交前至少运行与改动对应的测试、Ruff/Mypy 或 TypeScript 检查，并执行 `git diff --check`。修改 Artifact/public event 时同步更新 JSON Schema、Python/TypeScript 契约及 contract tests；修改表结构时添加可离线渲染的 Alembic revision 并复核 grants/RLS。

## 文档入口

- `README.md`
- `docs/README.md`
- `docs/governance/rfcs/RFC-0003-routepilot-full-rebuild-v1.md`
- `docs/operations/v1-platform.md`
