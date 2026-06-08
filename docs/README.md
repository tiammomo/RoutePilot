# Documentation Index

当前文档入口按“最新设计优先、治理记录次之、教学与历史最后”的顺序组织。

如果几份文档说法不同，优先级按下面执行：

1. `docs/reference/` 与 `docs/architecture/` 中描述当前实现的文档
2. `docs/governance/` 中已生效的 ADR / RFC
3. `README.md`
4. `docs/getting-started/`
5. `docs/teaching/`、路线图、历史总结

北京旅游数据 demo 的补充文档来自 `feature/hotel-data-demo-ready`，入口是：

- [project-structure.md](project-structure.md)
- [local-generated-files.md](local-generated-files.md)
- [troubleshooting.md](troubleshooting.md)

## 当前主线

这些是当前维护最该看的文档：

- [../README.md](../README.md)
- [getting-started/quick-start.md](getting-started/quick-start.md)
- [getting-started/development-workflow.md](getting-started/development-workflow.md)
- [architecture/system-architecture.md](architecture/system-architecture.md)
- [architecture/data-storage.md](architecture/data-storage.md)
- [architecture/infrastructure-foundations.md](architecture/infrastructure-foundations.md)
- [reference/api-reference.md](reference/api-reference.md)
- [reference/configuration-reference.md](reference/configuration-reference.md)
- [reference/project-structure.md](reference/project-structure.md)
- [reference/backend-maintainer-playbook.md](reference/backend-maintainer-playbook.md)
- [testing/testing-guide.md](testing/testing-guide.md)
- [project-structure.md](project-structure.md)
- [local-generated-files.md](local-generated-files.md)
- [troubleshooting.md](troubleshooting.md)

按场景建议：

- 本地启动与开发：
  [getting-started/quick-start.md](getting-started/quick-start.md)
  [getting-started/development-workflow.md](getting-started/development-workflow.md)
- 新人培训、带教或面试复习：
  先用 [teaching/README.md](teaching/README.md) 找入口，再重点看 [teaching/06-interview-highlights-and-system-evolution.md](teaching/06-interview-highlights-and-system-evolution.md) 和 [teaching/07-thinking-questions-homework-and-answers.md](teaching/07-thinking-questions-homework-and-answers.md)
- 改后端接口、错误码、契约：
  [reference/api-reference.md](reference/api-reference.md)
  [reference/error-code-reference.md](reference/error-code-reference.md)
- 改运行态、数据库、备份恢复、checkpoint：
  [architecture/data-storage.md](architecture/data-storage.md)
  [reference/configuration-reference.md](reference/configuration-reference.md)
  [reference/backend-maintainer-playbook.md](reference/backend-maintainer-playbook.md)
- 改 CI、发布、观测、运维脚本：
  [architecture/infrastructure-foundations.md](architecture/infrastructure-foundations.md)
  [testing/testing-guide.md](testing/testing-guide.md)
- 改北京旅游数据 demo、酒店/POI 数据或根目录 Next.js 工作台：
  [project-structure.md](project-structure.md)
  [local-generated-files.md](local-generated-files.md)
  [troubleshooting.md](troubleshooting.md)

## 治理与设计

这些文档定义“当前应遵守的决策”，不是背景材料：

- [governance/README.md](governance/README.md)
- [governance/adr/ADR-0002-versioned-release-images.md](governance/adr/ADR-0002-versioned-release-images.md)
- [governance/rfcs/RFC-0001-postgresql-migration-baseline.md](governance/rfcs/RFC-0001-postgresql-migration-baseline.md)
- [governance/rfcs/RFC-0002-checkpoint-sql-boundary.md](governance/rfcs/RFC-0002-checkpoint-sql-boundary.md)
- [architecture/backend-database-devops-maintenance-plan.md](architecture/backend-database-devops-maintenance-plan.md)

## 参考与产物

- 契约快照：
  [reference/openapi.snapshot.json](reference/openapi.snapshot.json)
  [reference/sse-contract.snapshot.json](reference/sse-contract.snapshot.json)
  [reference/runtime-doctor.snapshot.json](reference/runtime-doctor.snapshot.json)
- 质量与发布产物：
  [benchmarks/agent_benchmark_latest.md](benchmarks/agent_benchmark_latest.md)
  [benchmarks/agent_benchmark_trend_latest.md](benchmarks/agent_benchmark_trend_latest.md)
  [benchmarks/release_harness_scorecard_latest.md](benchmarks/release_harness_scorecard_latest.md)

## 路线图与历史归档

下面这些仍然保留，但默认不作为“当前实现真相源”：

- `docs/teaching/`
- `docs/getting-started/ai-travel-agent-zero-to-one.md`
- `docs/architecture/agent-subagent-skills-architecture-roadmap.md`
- `docs/architecture/harness-engineering-runtime-source-roadmap.md`
- `docs/architecture/agent-p0-hardening-roadmap.md`
- `docs/architecture/agent-dialogue-4-week-execution-plan.md`
- `docs/benchmarks/agent_iteration_summary_2026-04-05.md`

使用规则：

- 要理解背景、培训新人、复盘历史，可以看这些文档。
- 如果目标是面试速通、项目复盘或带教模拟，优先从 `docs/teaching/README.md` 进入，再回跳到 `docs/reference/`、`docs/architecture/` 校对当前实现细节。
- 要改代码、定 contract、做维护，不要先从这些文档下手。
- 如果历史路线图和当前实现说法冲突，以 `docs/reference/`、`docs/architecture/` 当前主线文档和已生效 ADR / RFC 为准。

## 脚本入口

当前推荐统一从 [`scripts/dev.py`](../scripts/dev.py) 进入：

- `python scripts/dev.py help`
- `python scripts/dev.py backend-test --pytest-slice unit`
- `python scripts/dev.py runtime-maintenance`
- `python scripts/dev.py checkpoint-maintenance`
- `python scripts/dev.py infra-check`

运行态 contract 治理入口：

- `scripts/runtime_contract_audit.py`: 审计 `AgentRuntime -> runtime_driver -> runtime_flow -> runtime_sources -> runtime_event_emitters` 的 typed seam
- `scripts/runtime_ops_contracts.py`: 统一 runtime doctor / support bundle / release manifest / release scorecard 的 typed report contract

## 维护约定

- 新功能或结构调整，至少同步更新：
  - `README.md`
  - `docs/README.md`
  - 受影响的 `docs/reference/*` 或 `docs/architecture/*`
- 如果改的是运行态、数据库、发布链或运维脚本，额外同步：
  - `docs/testing/testing-guide.md`
  - `docs/reference/backend-maintainer-playbook.md`
  - `docs/reference/configuration-reference.md`
