# Agent 与 A2A 扩展指南

RoutePilot 使用 A2A 1.0 Task 作为 Agent 协作边界。新增 Agent 的目标是增加一个职责清晰、输入输出可验证的专业能力，不是把普通领域函数包装成 Agent。

## 何时应该新增 Agent

适合 Agent：

- 需要独立任务生命周期、取消、恢复或远程执行；
- 需要一组明确的 Artifact 输入和输出；
- 失败后可以由 Orchestrator 安全降级或停止；
- 有独立权限、资源或服务边界。

不适合 Agent：预算求和、日期区间、坐标距离、JSON Schema 校验、CAS 和数据库租约。这些应保持确定性领域函数或基础设施能力。

## 当前接口

| interface ID | 输入 | 输出 |
| --- | --- | --- |
| `answering` | `TravelQuestion@1` | `TravelAnswer@1` |
| `research` | `TripBrief@1` | `EvidenceBundle@1`、`CandidateSet@1` |
| `planner` | Brief + Evidence + Candidate | `ItineraryPlan@1` |
| `validation` | Brief + Plan + Evidence | `ConstraintReport@1` |
| `semantic-verifier` | Brief + Plan + Evidence + Constraint | `SemanticRiskReport@1` |

注册表位于 `agent/travel_agent/a2a/registry.py`，执行器位于 `agent/travel_agent/runtime_v2/a2a_executors.py`，编排位于 `agent/travel_agent/runtime_v2/orchestrator.py`。

## 扩展步骤

1. **先定义契约**：新增或复用版本化 Artifact，明确最大尺寸、必填 provenance 和禁止字段。
2. **增加 Agent profile**：为 interface ID、skill ID、输入和输出建立稳定映射；禁止运行时接受任意 interface。
3. **实现 executor**：实现 `AgentExecutor`，只接收已验证 invocation，并只返回 allowlist 中的 Artifact。
4. **注入 composition root**：在 Runtime V2 组合处显式注入 executor；未配置时必须使用 fail-closed executor。
5. **加入 Orchestrator**：使用确定性 `dispatch_id` 和稳定 `dispatch_key`，保存 Product Run 与 A2A Task 引用。
6. **处理恢复与取消**：执行器必须响应 lease 丢失和 Task 取消，停止正在进行的 Provider/RAG 调用。
7. **增加 public projection**：如需用户可见进度，只增加封闭 public event 字段，不传 Task 原始消息。
8. **补齐测试**：覆盖 profile、contract rejection、幂等 dispatch、事件重放、租约 fencing、取消和恢复。

## Executor 安全要求

- 不接受浏览器直接提供的 tenant；使用服务端 `A2AActor`。
- 不把对话历史、prompt、reasoning 或工具原始响应放入 Task Artifact。
- 输入和输出都经过 `validate_contract`。
- 远端文本、RAG 文档和 Provider 字段都视为不可信数据。
- Provider 只能通过 Gateway；不得在 Agent 内直接读取 AMap key 或调用任意 URL。
- 所有等待必须有截止时间，并在取消时传播到子协程。
- Task 完成不能直接写 Product Run 状态；由协调层翻译结果。

## A2A 持久化不变量

- 去重键是 `(tenant_id, agent_interface_id, dispatch_id)`；
- inbox、Task 和初始事件必须在一个事务中创建；
- transition 使用单调 version/CAS；
- submitted/working Task 只有数据库租约持有者可以执行；
- execution attempt 是提交结果的 fencing token；
- 事件可从游标重放；
- typed input 在恢复前保存在 PostgreSQL；
- Product Run 取消需要传播到所有关联 Task。

## 当前远程编排边界

V1 的 `LocalA2AAgentMesh` 使用与 HTTP A2A 路由相同的 `TaskService`，因此没有绕过协议生命周期，但注册表仍是本地、静态、受信的。当前没有通用远程 Agent discovery、动态下载 Agent Card 或跨组织 federation。

若增加远程 Agent，必须另行设计：

- Agent Card 域名和证书 allowlist；
- OIDC/mTLS 服务身份；
- DNS/IP 重检、禁止私网 SSRF 和重定向；
- 输入输出大小与 content type 限制；
- timeout、retry、circuit breaker 和调用审计；
- 远端 Task 与本地 Product Run 的恢复对账；
- 数据驻留、许可和跨租户边界。

在这些控制完成前，不要把模型生成的 URL 或未经审核的 Agent Card 接入 registry。

## 最小测试集合

```bash
python -m pytest -q tests/a2a
python -m pytest -q tests/runtime_v2
python -m mypy agent/travel_agent/a2a agent/travel_agent/runtime_v2 \
  --config-file pyproject.toml
python scripts/v1_quality_gate.py --only a2a --only runtime --only contracts
```

如果扩展改变 Artifact 或 public event，继续执行 [Artifact 与事件契约扩展](artifact-contracts.md)中的同步步骤。
