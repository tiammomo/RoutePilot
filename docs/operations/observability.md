# 可观测性与告警基线

本文区分当前已实现信号与生产必须补充的能力。仓库已提供依赖级 readiness 和 token 保护的基础 Prometheus endpoint；当前仍没有集中日志管道、trace backend、Worker 聚合指标或现成 dashboard。单节点 Compose 只能提供基础运行信号。

## 当前已实现信号

| 信号 | 当前语义 | 限制 |
| --- | --- | --- |
| `/api/live` | FastAPI 进程可以响应 | 不检查数据库或 Redis |
| `/api/ready` | PostgreSQL 与 Redis 均可在 2 秒边界内响应 | 结果缓存约 1 秒；不主动探测 Provider/OIDC 上游 |
| `/api/health` | 返回 API 状态与版本 | 不汇总 Worker、DB、Redis、Provider 上游 |
| `/api/metrics` | HTTP 模板/状态类/延迟与依赖 ready gauge | 未配置 `ROUTEPILOT_METRICS_TOKEN` 时为 404；不聚合独立 Worker 进程 |
| Compose health | 各容器本地 healthcheck | 只适用于单机 Compose |
| Provider `/health` | configured、allowlisted、circuit metadata | 不主动调用上游 |
| `X-Request-ID`/`trace_id` | HTTP 与 Run 公开关联标识 | 尚无分布式 trace backend |
| 容器 stdout/stderr | API、Worker 和组件日志 | 尚无集中保留、索引和脱敏流水线 |

`/api/ready` 可作为 API 接流量的必要门禁，但不是整个平台健康的充分条件。Worker、outbox dispatcher、Provider、OIDC 和数据库复制仍需独立探针。

## Prometheus 抓取

生成至少 32 字节的独立 bearer token，只放入 secret manager 或权限为 `600` 的 Compose env：

```bash
openssl rand -hex 32
```

配置 `ROUTEPILOT_METRICS_TOKEN` 后，通过 API 内网端口抓取：

```bash
curl --fail-with-body --silent --show-error \
  -H "Authorization: Bearer $ROUTEPILOT_METRICS_TOKEN" \
  http://127.0.0.1:38083/api/metrics
```

不要经浏览器 BFF 或公网暴露该端点。当前 label 只包含 method、FastAPI route template、HTTP 状态类和固定 dependency 名，不包含原始 URL、资源 ID、tenant 或用户。

## 安全日志规则

可以记录：

- 时间、组件、级别、稳定错误码；
- trace ID、Run ID、Task ID、Artifact ID；
- phase、状态、版本、attempt 和耗时；
- Provider ID、能力、标准化结果码和 circuit 状态。

禁止记录：

- access/refresh token、Cookie、API key、DSN；
- prompt、reasoning 和工具原始输出；
- 完整私人旅行文本；
- A2A 原始 Task payload；
- Provider 原始错误体和带 key 的 URL。

日志采集器必须在出口再次执行 secret/PII 过滤，并设置按环境和数据分类的保留期。

## 生产指标建议

当前已经暴露 HTTP request count、request duration 和 PostgreSQL/Redis readiness。以下指标仍需由各独立进程或平台采集，不代表当前 API metrics 已经暴露：

- HTTP request count、latency、status 和 timeout；
- Run 按 lifecycle/phase 的数量、耗时、失败和取消；
- outbox 未发布数量、最老事件年龄、publish attempts；
- Redis stream lag、pending 数量和 reclaim 次数；
- Worker lease acquisition/renew/lost、attempt fencing rejection；
- A2A Task 状态、恢复、取消传播失败和事件重放延迟；
- Artifact candidate/publish/revoke/version conflict；
- RAG lexical/vector candidates、degraded mode、零结果率和检索耗时；
- Provider latency、timeout、rate limit、circuit open、stale fallback；
- DB 连接、事务、锁等待、存储、WAL 和复制延迟；
- OIDC 登录失败、JWKS 获取失败和 share capability 限流。

指标 label 不得包含 tenant 原文、用户 ID、query、token 或无限基数资源 ID。需要 tenant 视角时使用受控聚合或不可逆分桶。

## 初始告警建议

以下阈值只能作为单节点预发的起点，生产应根据 SLO 和基线调整：

| 告警 | 建议条件 |
| --- | --- |
| API 不可用 | live 连续 2 分钟失败 |
| 依赖不可用 | PostgreSQL/Redis 独立探针连续 1 分钟失败 |
| Run 堆积 | queued 最老年龄超过 2 个正常执行周期 |
| outbox 堆积 | 最老未发布事件超过 60 秒 |
| lease 异常 | 5 分钟内连续 lease lost/reclaim 激增 |
| Provider 退化 | timeout/rate-limit/circuit-open 比例持续超过基线 |
| RAG 退化 | vector 从 used 变为 unavailable 或零结果率异常上升 |
| 数据库风险 | 磁盘、WAL、连接或锁等待达到托管平台安全阈值 |
| 安全事件 | secret scan、跨租户拒绝或异常 capability 尝试出现 |

## Dashboard 最小视图

1. 用户入口：请求量、错误率、P50/P95/P99、登录失败；
2. 控制平面：Run 各状态、phase latency、版本冲突；
3. 执行平面：outbox、Redis lag、Worker lease、A2A Task；
4. 事实层：RAG mode/zero result、Provider latency/circuit；
5. 数据层：PostgreSQL 健康、连接、锁、WAL、备份状态；
6. 安全：401/403/429、分享轮换撤销、secret scan。

## 事件响应关联

排障工单至少记录：UTC/本地时间、环境、版本/commit、trace ID、Run/Task/Artifact ID、公开错误码、影响范围和已执行动作。不要复制完整请求或凭据。

备份成功不能只看任务退出码；需要恢复演练结果。具体步骤见[备份与恢复 Runbook](backup-restore.md)。
