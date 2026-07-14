# RoutePilot V1 平台手册

本文描述当前 V1 单机开发栈与单节点预发评估栈。生产高可用、托管密钥和跨区恢复不在 Compose 范围内。

## 服务边界

```text
Browser -> Next.js Web/BFF -> FastAPI /api/v1 -> PostgreSQL 17
                                  |                 ^
                                  v                 |
                         transactional outbox      |
                                  |                 |
                                  v                 |
                            Redis Streams -> Run Worker
                                                |
                           A2A Research/Planner/Validation/Verifier
                                                |
                                      RAG + Provider Gateway
```

- PostgreSQL 是 Trip、Product Run、Artifact version、A2A Task、RAG 与 public event 的真相源。
- Redis Streams 只做投递；消费者必须先取得数据库租约，并以 attempt fencing 提交。
- 浏览器只访问同源 BFF。数据库、Redis、OIDC、AMap、embedding 与 share pepper 都是 server-only。
- 浏览器不接收模型推理、工具原始输出、内部异常或 secret。
- 只读分享由已发布 `TripSnapshot` 显式投影为不可变 `ShareSnapshot`；capability 放在 URL fragment，一次性交换为 15 分钟 HttpOnly session。轮换或撤销立即使旧 capability 和 session 失效。

## 固定组件

| 组件 | V1 基线 |
| --- | --- |
| PostgreSQL | 17 + PostGIS 3.5 + pgvector 0.8.5 |
| Redis | 8.2.7 Alpine，AOF everysec |
| API/Worker | Python 3.13、FastAPI、Pydantic v2 |
| Web | Node.js 24、Next.js 16、React 19 |
| Agent | A2A SDK 1.x、RoutePilot Runtime V2 |

## 本地启动

```bash
cp deploy/compose/v1.env.example deploy/compose/.env.v1.local
```

每个数据库密码、Redis 密码、BFF secret、OIDC cookie key 与 `ROUTEPILOT_SHARE_PEPPER` 都必须独立生成。建议：

```bash
openssl rand -hex 32
node -e "console.log(require('crypto').randomBytes(32).toString('base64url'))"
```

高德 Web Service Key 是可选的 server-only 配置。真实值只写入被 Git 忽略的 `deploy/compose/.env.v1.local`：

```dotenv
ROUTEPILOT_AMAP_WEB_KEY=你的_Web_服务_Key
```

不得写入 Compose YAML、示例文件、前端 `NEXT_PUBLIC_*` 变量、日志或 Artifact。未配置时 Provider Gateway 显式报告 `configured: false`，运行时使用受审降级路径，不会伪装成实时高德事实。随后渲染并启动：

常用可调参数：

| 参数 | 默认值 | 作用 |
| --- | --- | --- |
| `ROUTEPILOT_PROVIDER_ALLOWLIST` | `amap` | 固定 Provider allowlist；未知 ID 启动失败 |
| `ROUTEPILOT_AMAP_HTTP_TIMEOUT_SECONDS` | `3.0` | 高德 socket timeout，范围 0.1–15 秒 |
| `ROUTEPILOT_V1_RUN_LEASE_SECONDS` | `60` | Worker 数据库租约 |
| `ROUTEPILOT_V1_RUN_RECLAIM_IDLE_MILLISECONDS` | `60000` | Redis pending reclaim 最小空闲时间 |
| `ROUTEPILOT_LOG_LEVEL` | `INFO` | 独立 Run Worker 日志级别 |

调整租约和 reclaim 必须结合 Provider deadline、heartbeat 和恢复演练，不能把缩短 reclaim 当作处理慢任务的通用方法。

```bash
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml config --quiet
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml up --build --detach
```

默认入口：

| 服务 | 地址 |
| --- | --- |
| Web | `http://127.0.0.1:33003` |
| API live | `http://127.0.0.1:38083/api/live` |
| API ready | `http://127.0.0.1:38083/api/ready` |
| API health | `http://127.0.0.1:38083/api/health` |
| OpenAPI | `http://127.0.0.1:38083/docs` |
| PostgreSQL | `127.0.0.1:35434` |
| Redis | `127.0.0.1:36379` |

`migration` 是成功后退出的一次性任务。应用启动不会调用 `create_all`。

## 本地身份与预发 OIDC

本地 BFF 只在以下条件全部成立时添加服务端开发身份：

1. Web `ROUTEPILOT_DEPLOYMENT_ENV=local`；
2. Web `ROUTEPILOT_BFF_DEV_AUTH=1`；
3. API `ROUTEPILOT_V1_DEV_AUTH=1` 且环境不是 staging/production；
4. 两端至少 32 字节的 `ROUTEPILOT_V1_DEV_BFF_SECRET` 完全一致。

浏览器提交的开发身份 header 和 Authorization header 都被忽略。

预发叠加安全覆盖：

```bash
docker compose --env-file /run/routepilot/preprod.env \
  --file deploy/compose/v1.yaml \
  --file deploy/compose/v1.preprod.yaml config --quiet
```

预发必须配置 HTTPS public origin、OIDC issuer/audience、authorization/token/JWKS/end-session URL、client id/secret 与 32 字节 cookie key。Web 使用 Authorization Code + PKCE，API 独立校验 access JWT；ID Token 不能当 API access token。

## 数据库角色、RLS 与迁移

| 角色 | 权限 |
| --- | --- |
| `routepilot_migrator` | Alembic schema 变更；仅一次性任务使用 |
| `routepilot_api` | tenant-scoped API DML；share exact resolver；无 BYPASSRLS |
| `routepilot_worker` | Run/A2A/RAG tenant-scoped DML；无 share 管理权限、无 BYPASSRLS |
| `routepilot_outbox` | 仅 outbox SELECT/UPDATE；没有业务表权限 |

顺序固定为 PostgreSQL healthy → Alembic upgrade → reviewed grants → API/Worker/Dispatcher。授权脚本撤销 PUBLIC 权限并对租户表执行 `FORCE ROW LEVEL SECURITY`。

安全分享的公开 ID 映射表不能被运行时角色枚举；API 只可 INSERT，并通过 exact-match `SECURITY DEFINER` 函数解析租户。share session 只额外授予 API DELETE，用于轮换/撤销即时 fencing。

## Run、A2A 与恢复

- `trip.replan` 必须携带当前已发布快照的 Artifact ID 和 version；存储层原子比较 Trip 指针，过期基线返回冲突。
- 交互 Run 将有界 typed input schema 和 expiry 持久化到 PostgreSQL；resume 使用 CAS、request ID 和 idempotency key。
- Run Worker 使用数据库租约、heartbeat、execution attempt 和晚到写 fencing。
- 每个 A2A Task 有独立状态、租约、事件游标、输入恢复和取消；Product Run 状态不能覆盖 A2A Task 状态。
- Redis pending reclaim 只能触发重新竞争数据库租约，不能授予执行权。

## RAG 与实时事实

RAG 使用 PostgreSQL FTS 和可选 pgvector 混合检索。每条结果保留 source、version、license、freshness、trust 与 retrieval trace。未配置 embedding 时明确降级为 lexical-only。

地理编码、POI、路线、营业和天气经 Provider Gateway 获取。Provider 文本与摄取文档都是不可信证据，不能改变系统指令；密钥不进入 Artifact 或 public event。

## 数据持久化与备份边界

Compose 只有 PostgreSQL 与 Redis 两个 named volume。以下命令会永久删除本地 V1 数据：

```bash
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml down --volumes
```

生产必须另行实现 PostgreSQL PITR/WAL、备份恢复演练、Redis 投递恢复 SLO、托管 secret、跨区副本与故障切换。

## 容器与健康检查

- API、Worker、Dispatcher、Migration 与 Web 使用 non-root、只读 root filesystem、`cap_drop: ALL`、`no-new-privileges` 和有界 tmpfs。
- PostgreSQL/Redis 只写 named volume，主机端口默认绑定 loopback。
- `/api/live` 只表示进程存活；`/api/ready` 并发探测 PostgreSQL/Redis，任一缺失、超时或不可用均返回 `503`；`/api/health` 只返回 API 状态与版本。Worker、Provider、OIDC 与复制健康仍需独立门禁。
- 配置至少 32 字符的 `ROUTEPILOT_METRICS_TOKEN` 才会启用 `/api/metrics`；未配置时端点返回 `404`。指标端点只允许从受信运维网络抓取。
- Worker 在 SIGTERM 后停止拉取并释放/结束当前租约；租约丢失会取消执行协程。

完整信号语义、生产指标和告警建议见[可观测性与告警基线](observability.md)。

## 验证与交付

```bash
python scripts/v1_quality_gate.py
git diff --check
```

统一门禁覆盖 contracts、backend、A2A、Provider、RAG、Runtime、Web、文档、安全和 migration offline SQL。文档门禁校验必需覆盖、内部链接和 env/Compose 一致性。CI 另外执行真实 PostgreSQL/Redis/RLS/恢复测试、Compose 渲染、镜像构建、dependency audit、gitleaks、SBOM 和镜像漏洞扫描。

当前 Compose 不是生产 HA：它不包含托管 OIDC、TLS/WAF、网络策略、autoscaling、PDB、集中日志告警、跨区数据库或签名 admission policy。

知识摄取参阅[RAG Runbook](rag-ingestion.md)，常见问题参阅[故障排查](troubleshooting.md)，数据保护参阅[备份与恢复](backup-restore.md)。
