# 故障排查手册

本手册用于本地和单节点预发。排障目标是先保存证据、确定故障域，再执行可逆操作。不要把删除 volume、清空 Redis 或修改数据库状态当作第一步。

## 首轮证据

```bash
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml ps
curl --fail-with-body http://127.0.0.1:38083/api/live
curl --fail-with-body http://127.0.0.1:38083/api/ready
curl --fail-with-body http://127.0.0.1:38083/api/health
curl --fail-with-body http://127.0.0.1:33003/api/auth/session
```

记录时间、服务状态、HTTP 状态、`X-Request-ID`/`trace_id` 和最近一次变更。分享日志前先检查是否含私人问题、token、DSN 或 Provider key。

查看有限日志：

```bash
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml logs --since=15m --tail=300 api run-worker outbox-dispatcher web
```

## Compose 渲染失败

常见原因：`.env.v1.local` 不存在、必填值为空、secret 长度不足或变量拼写错误。

```bash
test -f deploy/compose/.env.v1.local
stat -c '%a %n' deploy/compose/.env.v1.local
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml config --quiet
```

env 文件权限建议为 `600`。不要把渲染后的完整 Compose 配置上传到 Issue，因为其中可能包含 secret。

## PostgreSQL 或 migration 失败

```bash
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml ps postgres migration
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml logs --tail=200 postgres migration
```

检查：

- PostgreSQL volume 是否来自当前 V1，而非旧项目；
- 初始化角色密码是否在首次建卷后被修改；修改 env 不会自动修改卷中已有数据库密码；
- migration 是否到达 Alembic head；
- grants/RLS 脚本是否成功执行。

不要在应用启动代码增加 `create_all`，不要手工关闭 RLS。恢复前先参考[备份与恢复 Runbook](backup-restore.md)。

## API 正常但页面无法使用

1. 检查 Web `/api/auth/session`；
2. 检查 Web 和 API 的 `ROUTEPILOT_V1_DEV_BFF_SECRET` 是否完全一致；
3. 确认本地身份只在 local/dev 启用；
4. 预发检查 public origin、OIDC issuer/audience、回调 URL、JWKS 和 cookie key；
5. 浏览器只访问 Web origin，不直接把 token 写入 localStorage。

OIDC 错误页不会显示上游原始 token 响应。使用 identity provider 的审计日志和 RoutePilot `trace_id` 对账。

## Run 一直 queued

检查 `outbox-dispatcher`、Redis 和 `run-worker`：

```bash
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml ps redis outbox-dispatcher run-worker
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml logs --since=15m --tail=300 outbox-dispatcher run-worker
```

PostgreSQL outbox 是可恢复投递来源。Redis pending 只能触发重新竞争数据库租约，不能直接授予执行权。不要手工把 Run 改成 running/completed，也不要删除 pending entry 掩盖问题。

## Run 卡在 running 或取消中

- 核对 Worker 是否仍持有数据库租约；
- 等待至少一个 lease/reclaim 窗口再判断是否无法恢复；
- 检查 Provider timeout 和 A2A Task 状态；
- 取消操作必须先持久化 `cancel_requested`，再传播到 Task；
- 晚到 executor 会被 attempt fencing 拒绝，不要绕过 fencing 强行提交。

调整 `ROUTEPILOT_V1_RUN_LEASE_SECONDS` 和 reclaim idle 前，要保证 reclaim 不短于合理 heartbeat/请求时间，并在故障演练中验证。

## 高德未生效

```bash
curl --fail-with-body http://127.0.0.1:33003/api/v1/providers/capabilities
```

只检查 `configured`/`allowlisted`，接口不会返回 key。确认使用 `ROUTEPILOT_AMAP_WEB_KEY`，并在修改 env 后重新创建 API 和 Worker。不要把 key 打印到终端、日志或截图。

Provider health 是本地配置和 circuit metadata，不会主动探测高德。真实调用仍可能因 quota、网络、上游错误或超时失败。

## DeepSeek 或 Embedding 未生效

- LLM 未配置时问答使用确定性证据摘要，不应伪造模型输出；
- 检查 Worker 是否重新创建并读取了 server-only env；
- RAG trace 为 `lexical/disabled` 表示未配置 embedding；
- `provider_not_semantic` 不能当成向量召回；
- 不要通过提高 token 上限掩盖证据不足。

## 页面显示版本冲突

这是预期的并发保护。读取响应中的 `current_version`，刷新 Artifact/Trip，核对最新版后重新执行。不要自动把旧 mutation 改成新版本重试。

## 安全停止与重启

```bash
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml stop web api run-worker outbox-dispatcher
docker compose --env-file deploy/compose/.env.v1.local \
  --file deploy/compose/v1.yaml up --detach web api run-worker outbox-dispatcher
```

Worker 有 graceful shutdown 和租约恢复。普通重启不需要删除 PostgreSQL/Redis volume。

## 升级为事件处理

满足任一条件应停止反复重试并进入人工事件处理：

- tenant 隔离或 RLS 可能失效；
- secret 进入日志、Git、Issue 或浏览器 bundle；
- Artifact/public event 暴露禁止字段；
- 数据库恢复点不明确；
- migration 部分执行且无法确定 schema；
- 同一幂等请求产生不同业务结果。

立即保存只读证据、限制访问、轮换受影响凭据，并记录时间线。不要在未保留证据前清理日志或数据。
