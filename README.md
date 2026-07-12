# RoutePilot V1

RoutePilot 是一个面向旅行决策的 Artifact-first 多 Agent 工作台。它把用户约束、检索证据、候选方案、行程计划、约束校验和最终快照组织成严格版本化的 Artifact，而不是把一段模型文本当作产品真相。

仓库当前只有 V1 产品主线。旧前端、旧业务 API 和旧 Agent 运行时不属于运行时或兼容面；历史数据只能通过显式的离线迁移工具导入为只读归档。

## 核心能力

- 响应式 Next.js 旅行工作台，以及同源 BFF 身份边界。
- FastAPI Trip、Run、Artifact、成员管理和公开事件 API。
- 基于正式 TripSnapshot 的结构化重规划、CAS 防过期覆盖和持久 typed-input 恢复。
- capability + 短期 HttpOnly session 的脱敏只读分享，支持即时轮换与撤销。
- Research、Planner、Validation、Semantic Verifier 四类 A2A 1.0 Agent 接口。
- PostgreSQL 持久化 Product Run、A2A Task、Artifact version、RAG 与事务 outbox。
- Redis Streams 外部执行队列；Run/A2A 数据库租约、attempt fencing、重投递和跨进程取消。
- PostgreSQL FTS + 可选 pgvector 的租户隔离 RAG，保留来源、版本、许可、时效与检索轨迹。
- 受控 Provider Gateway：高德地理编码、POI、路线矩阵、营业时间与天气事实。
- OIDC Authorization Code + PKCE Web 登录；API 独立校验 access JWT。
- JSON Schema、Python 与 TypeScript 共享契约，以及统一质量门禁。

## 架构

```text
Browser
  |
  v
Next.js Web / same-origin BFF ----> OIDC Provider
  |
  v
FastAPI /api/v1
  |                PostgreSQL (system of record)
  +---- command ---> Run + outbox + Artifact + A2A Task + RAG
                         |
                  outbox-dispatcher
                         |
                    Redis Streams
                         |
                     run-worker
                         |
          Research -> Planner -> Validation -> Verifier
              |                             |
           RAG search                Provider Gateway
```

浏览器只接收白名单化的 public event 与结构化 Artifact，不接收模型私有推理、工具原始返回或服务端凭据。Redis 负责投递，不是 Run 状态的真相源。

## 目录

| 路径 | 职责 |
| --- | --- |
| `apps/web/` | Next.js 16 / React 19 工作台、同源 BFF、OIDC 会话 |
| `backend/moyuan_web/v1/` | FastAPI V1 产品 API、控制平面、存储与 Worker |
| `agent/travel_agent/a2a/` | A2A 1.0 协议边界与持久 Task |
| `agent/travel_agent/runtime_v2/` | 旅行编排、Research、规划与校验链路 |
| `agent/travel_agent/rag/` | 知识摄取、混合检索与 provenance |
| `agent/travel_agent/providers/` | 实时旅行事实 Provider Gateway |
| `packages/`、`schemas/` | Python/TypeScript 契约与 JSON Schema |
| `deploy/` | Alembic、Compose、容器与最小权限数据库配置 |
| `scripts/` | Worker、outbox、质量门禁和离线数据迁移入口 |
| `tests/` | 契约、单元、集成、恢复与垂直切片测试 |

## 本地启动

要求 Docker Engine、Docker Compose v2；如需本地运行质量门禁，还需要 Python 3.13、Node.js 24 和 npm。

```bash
cp deploy/compose/v1.env.example deploy/compose/.env.v1.local
```

为 `.env.v1.local` 中每个密码和 BFF secret 生成独立随机值。示例中的必填 secret 留空时 Compose 会 fail closed；高德 Key 是可选项，未配置时系统保守降级，不会向浏览器注入任何地图密钥。

### 配置高德 Web Service Key

1. 在[高德开放平台](https://lbs.amap.com/api/webservice/create-project-and-key)创建应用并添加 Key，服务平台必须选择“Web 服务”，不要选择 Web 端 JS API、Android 或 iOS Key。
2. 打开本地且已被 Git 忽略的 `deploy/compose/.env.v1.local`，只填写下面这一项：

   ```dotenv
   ROUTEPILOT_AMAP_WEB_KEY=你的_Web_服务_Key
   ```

3. 重新创建 API 和 Run Worker，使服务端读取新配置：

   ```bash
   docker compose \
     --env-file deploy/compose/.env.v1.local \
     --file deploy/compose/v1.yaml \
     up --build --detach api run-worker
   ```

4. 通过服务端能力接口确认是否生效。配置状态只以 `configured: true/false` 表示，响应不会返回 Key：

   ```bash
   curl http://127.0.0.1:33003/api/v1/providers/capabilities
   ```

安全边界：不要把真实 Key 写入 README、`.env.example`、Compose YAML、前端代码或任何 `NEXT_PUBLIC_*` 变量；不要使用已废弃的 `AMAP_API_KEY` 别名。真实 Key 只应存在于被忽略的本地 env 文件或生产 secret manager 中。若 Key 曾进入 Git 历史、日志、Issue 或聊天记录，应立即在高德控制台撤销并轮换。

```bash
docker compose \
  --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml \
  config --quiet

docker compose \
  --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml \
  up --build --detach
```

默认入口：

- Web：`http://127.0.0.1:33003`
- API：`http://127.0.0.1:38083`
- OpenAPI UI：`http://127.0.0.1:38083/docs`
- 健康检查：`http://127.0.0.1:38083/api/health`

Compose 会先运行一次 Alembic migration 和数据库授权，再启动 API、Run Worker、Outbox Dispatcher 与 Web。详细配置见 [V1 平台手册](docs/operations/v1-platform.md)。

## 验证

```bash
python -m pip install -r requirements-dev.txt
npm ci --prefix apps/web --ignore-scripts
python scripts/v1_quality_gate.py
```

统一门禁覆盖契约、后端、A2A、Provider、RAG、Runtime、Web、安全边界和 Alembic 离线 SQL。需要真实 PostgreSQL/Redis 的测试由 CI 的 stateful integration job 执行；本地也可提供对应的 `ROUTEPILOT_*_TEST_*` DSN 运行。

## 数据库与历史数据

V1 schema 只通过 Alembic 管理：

```bash
docker compose \
  --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml \
  run --rm migration
```

历史 session/share 数据不是产品兼容面，也不会被应用自动读取。需要保留时，由管理员显式运行 `python -m scripts.migration_v1`，完成 inventory、dry-run/backfill 与 verify；输出是只读 `ImportedTripArchive@1`，工具不会自动删除或改写源数据。操作步骤见 [V1 数据迁移 Runbook](docs/operations/v1-migration-runbook.md)。

## 文档

- [文档索引](docs/README.md)
- [V1 已实现架构 RFC](docs/governance/rfcs/RFC-0003-routepilot-full-rebuild-v1.md)
- [V1 平台与预发说明](docs/operations/v1-platform.md)
- [V1 离线数据迁移 Runbook](docs/operations/v1-migration-runbook.md)

## License

见 [LICENSE](LICENSE)。
