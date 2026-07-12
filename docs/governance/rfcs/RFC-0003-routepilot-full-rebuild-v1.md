# RFC-0003 RoutePilot 全量重构 V1

## Status

- 状态：Accepted / Implemented
- 日期：2026-07-12
- 范围：产品体验、Web、API、Agent/A2A、RAG、Provider、数据、安全与交付

本 RFC 描述仓库当前唯一产品主线。它不是迁移中的双轨目标，也不定义旧 API、旧前端或旧 Agent 兼容层。历史数据只允许由 `scripts/migration_v1/` 离线导入为只读 `ImportedTripArchive@1`。

## 1. 决策摘要

RoutePilot V1 是 Artifact-first 的多 Agent 旅行决策工作台：

1. 产品主对象是 Trip、Run 和 Artifact，不是聊天消息。
2. Web 使用 Next.js 同源 BFF；浏览器不直接访问后端 origin、A2A 或第三方 Provider。
3. FastAPI 模块化单体管理控制平面、权限、持久化和 Worker 协议。
4. PostgreSQL 是全部业务状态真相源；Redis Streams 只负责投递。
5. Product Run、A2A Task 和 Artifact version 是三个独立生命周期。
6. Agent 间通过 A2A 1.x 交换版本化、有界 typed Artifact。
7. RAG 负责带 provenance 的历史/知识召回；实时事实只经过 Provider Gateway。
8. 浏览器只接收白名单 public event 与结构化 Artifact。
9. 所有 schema 变更只通过 Alembic；应用启动不创建表。
10. 重规划基于已发布 TripSnapshot 的 ID+version 做 CAS；分享基于显式最小化投影。

## 2. 产品模型

工作台围绕一次旅行展示：

- 当前约束：目的地、日期、同行人、预算、偏好、无障碍需求；
- 正式方案与历史版本；
- 每日时间块、地图、预算、证据和风险；
- Run 实时状态、断线恢复、取消和待输入恢复；
- 候选 Artifact 的校验、发布、撤销；
- 正式方案的脱敏只读分享。

自然语言是提交命令的入口，但不能作为业务状态。每次规划输出一组契约化 Artifact：

```text
TripBrief
  -> EvidenceBundle
  -> CandidateSet
  -> ItineraryPlan
  -> ConstraintReport + SemanticRiskReport
  -> ValidationReport
  -> TripSnapshot
  -> ShareSnapshot (仅显式分享时生成)
```

校验失败时保留 candidate 和报告，不发布 TripSnapshot。

## 3. 系统结构

```text
Browser
  |
  v
Next.js Web / same-origin BFF ---- OIDC Provider
  |
  v
FastAPI /api/v1
  |                 PostgreSQL 17 / PostGIS / pgvector
  +-- command ----> Trip + Run + Artifact + A2A Task + RAG
                           |
                    transactional outbox
                           |
                           v
                      Redis Streams
                           |
                       Run Worker
                           |
        Orchestrator -> Research -> Planner -> Validation -> Verifier
                           |                         |
                      RAG retrieval           Provider Gateway
```

代码所有权固定为：

| 路径 | 职责 |
| --- | --- |
| `apps/web/` | 工作台、BFF、OIDC 浏览器会话、公开分享页 |
| `backend/moyuan_web/v1/` | `/api/v1`、控制平面、持久化、Worker、分享投影 |
| `agent/travel_agent/a2a/` | A2A Task、dispatch、事件与恢复 |
| `agent/travel_agent/runtime_v2/` | Research/Planner/Validation/Verifier 编排 |
| `agent/travel_agent/rag/` | ingestion、混合检索、provenance |
| `agent/travel_agent/providers/` | 实时事实 Provider Gateway |
| `packages/`、`schemas/` | 跨语言契约 |
| `deploy/migrations/` | 唯一 schema 变更入口 |
| `scripts/migration_v1/` | 历史数据只读离线导入 |

## 4. 生命周期与一致性

### Product Run

Product Run 面向用户，状态为 queued、running、waiting_input、waiting_approval、cancel_requested、completed、failed、canceled。它持有独立 control version、public event cursor、执行租约与 attempt。

创建、取消和恢复都使用 idempotency key。控制变更使用 CAS；同 key 不同请求拒绝。外部 Worker 必须先取得数据库租约，heartbeat 续租；晚到 attempt 的 Run transition 和 Artifact 写入在同一事务中被拒绝。

交互式补充信息以有界 `RunPendingInput` 持久化，包含 request ID、typed fields 和 expiry。resume 必须同时匹配 Run version、request ID 和字段 schema。

### A2A Task

A2A Task 是 Agent 间协议状态，不能用 Product Run 状态代替。dispatch inbox 以确定性 key 去重；Task 事件可重放；Task 支持租约、attempt fencing、输入恢复和取消。

Product Run 取消先持久化控制状态，再传播到关联 Task。远端执行器观察到取消或租约失效后主动终止 Provider/RAG 协程。

### Artifact version

Artifact 采用 immutable version 与显式状态转换。发布在一个事务内完成：当前正式版本 supersede、新版本 publish、Trip 指针更新、public event 与 outbox 写入。

Product Run 完成不覆盖 Artifact 历史；A2A Task 完成也不等于 Product Run 可发布。

## 5. 规划与重规划

首次 `trip.plan` 接收结构化 `trip_request`，转换为 TripBrief 后进入 Runtime V2。

`trip.replan` 必须携带当前正式 TripSnapshot 的 `base_artifact_id` 和 `base_artifact_version`，以及结构化 patch：

- dates；
- budget；
- preference add/remove；
- exclude places；
- retain places。

服务端读取固定快照、验证契约、保留未修改约束并生成新 TripBrief。存储事务再次比较 Trip 当前指针；在读取与提交之间发生发布时，重规划以 version conflict 失败，不会基于过期方案静默覆盖。

Planner 把 hard avoid 作为过滤条件，把 retain place 提升到候选顺序前部；若过滤后无候选则安全失败，Validation/Verifier 仍负责最终硬约束判断。

## 6. Agent 与 A2A

V1 采用一个 Orchestrator 和四个清晰角色：

- Research：组合 RAG 与实时 Provider，输出 EvidenceBundle/CandidateSet；
- Planner：将约束和证据转换为 ItineraryPlan；
- Validation：执行确定性日期、预算、路线与硬约束校验；
- Verifier：评估证据覆盖、时效、冲突和语义风险。

Agent 之间不交换任意对话历史、私有推理或工具原始结果，只交换带 schema version、大小限制、tenant/run/task reference 和 provenance 的 Artifact。A2A host 暴露标准 Agent Card 与 Task 接口，持久层提供跨进程恢复。

确定性能力不为了“多 Agent”而 Agent 化：预算求和、时间区间、坐标距离、route matrix 解析和契约验证仍是领域函数/工具。

## 7. RAG 与 Provider

### RAG

摄取流程记录：

- tenant、document/chunk ID；
- source kind/name/URI；
- source version、publisher、license；
- observed/retrieved/valid time；
- trust、content hash、corpus revision；
- embedding model/version/dimension。

检索组合 PostgreSQL FTS 和可选 pgvector，相同 tenant predicate 应用于 lexical、vector 与 hydration。结果携带 retrieval trace；缺少 embedding 时明确报告 lexical-only degradation。

所有外部文档视为不可信证据。摄取文本不能覆盖系统指令、触发任意工具或泄露其他租户数据。

### Provider Gateway

实时地理编码、POI、路线、营业状态和天气只通过 Gateway。V1 provider allowlist 为 AMap。Gateway 负责 timeout、响应尺寸、重试边界、标准化、freshness 和 provenance；server key 不进入 Web bundle、Artifact、public event 或日志。

RAG 不宣称实时价格/营业/天气权威，Provider 失败时不得伪造事实。

## 8. API、事件和浏览器边界

Web BFF 只代理显式 allowlist 的 `/api/v1` 路由，拒绝绝对 URL、未知路径和超限 body。mutation 要求同源 Origin、CSRF 和必要的 idempotency/If-Match header。

public event 采用封闭 type 列表和逐 type 字段白名单。未知字段在后端和浏览器两次投影中丢弃。禁止字段包括：reasoning、prompt、tool raw output、内部 exception/traceback、credential 和任意私有 diagnostics。

SSE 使用单调 seq 和 Last-Event-ID/after_seq 恢复。重新连接只读取事件，不重复创建 Run。

## 9. 身份、租户与 RLS

预发/生产使用 OIDC Authorization Code + PKCE。Web 保存 HttpOnly 会话 cookie，API 独立验证 access JWT 的签名、issuer、audience、expiry 和算法 allowlist。

tenant ID 从服务端认证 principal 派生；浏览器 tenant header 永不可信。每次 Trip/Run/Artifact/A2A/RAG 查询同时包含 tenant predicate，数据库表启用并强制 RLS。

数据库角色分为 migrator、API、Worker、Outbox。Outbox BYPASSRLS 角色仅有 outbox 表权限；Worker 没有安全分享管理表权限。

## 10. 安全分享

只有 Trip 当前已发布的 TripSnapshot 可以分享。创建时在事务内再次验证 Trip 指针并生成不可变 ShareSnapshot，明确删除 travelers、精确预算、私人文本和内部字段，坐标降精度。

分享采用两段式能力：

1. 管理 API 返回一次 capability secret，完整链接格式为 `/share/{public_id}#{secret}`；
2. fragment 不发送给服务器；页面清除 fragment 后，通过同源 CSRF POST 一次性交换；
3. BFF 把返回 token 写入 15 分钟 HttpOnly、SameSite=Strict cookie；
4. public snapshot 只接受该短期 session。

数据库只保存 capability/session 的 keyed hash，不保存明文。secret 可从 server-only pepper + 幂等上下文确定性重建，因此 create/rotate 重放可以返回同一结果而无需落明文。

公开 ID 解析使用 exact-match SECURITY DEFINER 函数，运行时角色不能枚举映射表。失败尝试持久计数并限流。rotate/revoke 增加 capability epoch 并删除全部旧 session。

## 11. 数据与迁移

schema 只通过 `deploy/migrations/` 的 Alembic revision 变更。质量门禁必须离线渲染全部 SQL，并检查核心表、RLS、pgvector、执行 fencing、typed recovery 和安全分享标记。

历史数据不由应用读取。管理员可离线执行 inventory → dry-run/backfill → verify，导入只读 `ImportedTripArchive@1`。导入工具没有流量切换、在线双写、兼容读取或删除源数据能力。

## 12. 交付门禁

`python scripts/v1_quality_gate.py` 是唯一汇总入口，覆盖：

- JSON Schema/Python/TypeScript contract parity；
- Backend、Artifact、Run、replan/resume、share；
- A2A protocol、recovery、cancel；
- Provider、RAG retrieval quality、Runtime V2；
- Web typecheck/test/production build；
- 必需文档、内部链接和 env/Compose 配置一致性；
- OIDC、public projection、secret/error boundary；
- migration tests 与 offline SQL。

CI 额外在真实 PostgreSQL/Redis 上执行 RLS、租约、A2A、RAG、Artifact 和安全分享测试，并验证 migration upgrade→downgrade→upgrade、Compose、容器、SBOM、依赖与 secret scan。

## 13. 明确不包含

- 旧 API、旧 Web、旧 Agent 或旧事件协议兼容；
- 在线双写、shadow read、cohort 切流；
- 浏览器直连 A2A/Provider/数据库；
- 用 Redis 作为业务真相源；
- 在应用启动时自动建表；
- 将模型文本或 reasoning 当作正式行程；
- 在单机 Compose 中宣称生产 HA。

## 14. 不变量

1. PostgreSQL 是唯一业务真相源，Redis 只做投递。
2. Run、A2A Task、Artifact version 生命周期独立。
3. 异步写入使用 idempotency、CAS、数据库租约和 attempt fencing。
4. tenant 来自服务端 principal，并同时受 predicate 与 RLS 保护。
5. 浏览器只接收 public 白名单和结构化 Artifact。
6. Agent 只交换版本化、有界 typed Artifact。
7. RAG 结果保留 provenance，外部内容视为不可信证据。
8. 实时事实只经过 Provider Gateway，secret 永远 server-only。
9. schema 只通过 Alembic 修改。
10. 不恢复任何已移除的旧运行时或临时兼容开关。
