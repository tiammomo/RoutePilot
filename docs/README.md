# Documentation Index

这套文档按“先上手、再理解、再查表”的顺序组织，方便不同读者快速找到入口。

## 建议阅读顺序

### 如果你是第一次接触项目

1. [../README.md](../README.md): 先看项目概览、能力范围和界面截图
2. [getting-started/quick-start.md](getting-started/quick-start.md): 按步骤启动前后端
3. [getting-started/ai-travel-agent-zero-to-one.md](getting-started/ai-travel-agent-zero-to-one.md): 用一条完整链路理解 AI 旅游 Agent 的设计
4. [reference/project-structure.md](reference/project-structure.md): 了解目录职责

### 如果你要继续开发或排查问题

1. [architecture/system-architecture.md](architecture/system-architecture.md): 理解前端、API、Agent 调用链
2. [getting-started/ai-travel-agent-zero-to-one.md](getting-started/ai-travel-agent-zero-to-one.md): 先建立 Agent 心智模型，再深入代码
3. [reference/api-reference.md](reference/api-reference.md): 查看接口与 SSE 事件协议
4. [testing/testing-guide.md](testing/testing-guide.md): 跑测试、benchmark 和 replay
5. [reference/configuration-reference.md](reference/configuration-reference.md): 查配置与环境变量

## 文档分区

### Teaching

#### 按任务场景跳转

- 系统学习整个项目：
  先看 [teaching/README.md](teaching/README.md)
- `30 分钟速览`：
  看 [teaching/01-total-plan-and-learning-method.md](teaching/01-total-plan-and-learning-method.md)
- `半天上手`：
  依次看 [teaching/01-total-plan-and-learning-method.md](teaching/01-total-plan-and-learning-method.md)、[teaching/02-chat-mainline-and-frontend.md](teaching/02-chat-mainline-and-frontend.md)、[teaching/03-web-api-session-and-storage.md](teaching/03-web-api-session-and-storage.md)
- `改 Bug 前先找主链`：
  先看 [teaching/02-chat-mainline-and-frontend.md](teaching/02-chat-mainline-and-frontend.md)，再按故障落点跳到 [teaching/03-web-api-session-and-storage.md](teaching/03-web-api-session-and-storage.md)、[teaching/04-agent-core-tools-memory-checkpoint.md](teaching/04-agent-core-tools-memory-checkpoint.md)、[teaching/05-testing-debugging-and-change-practice.md](teaching/05-testing-debugging-and-change-practice.md)
- `我要改前端`：
  优先看 [teaching/02-chat-mainline-and-frontend.md](teaching/02-chat-mainline-and-frontend.md) 和 [teaching/05-testing-debugging-and-change-practice.md](teaching/05-testing-debugging-and-change-practice.md)
- `我要改 Web API`：
  优先看 [teaching/03-web-api-session-and-storage.md](teaching/03-web-api-session-and-storage.md) 和 [teaching/05-testing-debugging-and-change-practice.md](teaching/05-testing-debugging-and-change-practice.md)
- `我要改 Agent`：
  优先看 [teaching/04-agent-core-tools-memory-checkpoint.md](teaching/04-agent-core-tools-memory-checkpoint.md) 和 [teaching/05-testing-debugging-and-change-practice.md](teaching/05-testing-debugging-and-change-practice.md)
- `我要看部署 / 配置 / readiness / trace / CI`：
  优先看 [architecture/infrastructure-foundations.md](architecture/infrastructure-foundations.md)、[reference/configuration-reference.md](reference/configuration-reference.md)、[testing/testing-guide.md](testing/testing-guide.md)
- `我要看仓库规范 / 命令入口 / 容器校验`：
  优先看 [getting-started/development-workflow.md](getting-started/development-workflow.md)、[reference/project-structure.md](reference/project-structure.md)、[architecture/infrastructure-foundations.md](architecture/infrastructure-foundations.md)
- `我要发起大改动 / 补 ADR / 写设计评审`：
  优先看 [governance/README.md](governance/README.md)、[architecture/harness-engineering-runtime-source-roadmap.md](architecture/harness-engineering-runtime-source-roadmap.md)
- `我要做 Agent 架构升级 / agent-subagent-skills 规划`：
  优先看 [architecture/agent-subagent-skills-architecture-roadmap.md](architecture/agent-subagent-skills-architecture-roadmap.md)、[architecture/system-architecture.md](architecture/system-architecture.md)、[teaching/04-agent-core-tools-memory-checkpoint.md](teaching/04-agent-core-tools-memory-checkpoint.md)
- `我要接新 skill / 看 skills market 规范`：
  优先看 [reference/skills-market-catalog.md](reference/skills-market-catalog.md)、[governance/skills-market-onboarding.md](governance/skills-market-onboarding.md)、[teaching/04-agent-core-tools-memory-checkpoint.md](teaching/04-agent-core-tools-memory-checkpoint.md)
- `我要看 release / dashboard / alert`：
  优先看 [architecture/infrastructure-foundations.md](architecture/infrastructure-foundations.md)、[reference/backend-maintainer-playbook.md](reference/backend-maintainer-playbook.md)、[../ops/observability/README.md](../ops/observability/README.md)
- `面试前 2 小时复习`：
  优先看 [teaching/01-total-plan-and-learning-method.md](teaching/01-total-plan-and-learning-method.md)、[teaching/06-interview-highlights-and-system-evolution.md](teaching/06-interview-highlights-and-system-evolution.md)、[teaching/07-thinking-questions-homework-and-answers.md](teaching/07-thinking-questions-homework-and-answers.md)

#### 教学文件总表

- [teaching/README.md](teaching/README.md): 教学总入口，适合按课程方式系统学习整个项目
- [teaching/01-total-plan-and-learning-method.md](teaching/01-total-plan-and-learning-method.md): 总规划、学习顺序、能力分级与 7 天 / 14 天 / 4 周路线
- [teaching/02-chat-mainline-and-frontend.md](teaching/02-chat-mainline-and-frontend.md): 聊天主链路、SSE、前端状态流和结果加工
- [teaching/03-web-api-session-and-storage.md](teaching/03-web-api-session-and-storage.md): Web API 分层、session 生命周期和存储设计
- [teaching/04-agent-core-tools-memory-checkpoint.md](teaching/04-agent-core-tools-memory-checkpoint.md): Agent 状态机、tools、memory、checkpoint 与验证机制
- [teaching/05-testing-debugging-and-change-practice.md](teaching/05-testing-debugging-and-change-practice.md): 测试阅读、调试路径、回归矩阵和改动实战
- [teaching/06-interview-highlights-and-system-evolution.md](teaching/06-interview-highlights-and-system-evolution.md): 面试难点、答题框架和系统演进方向
- [teaching/07-thinking-questions-homework-and-answers.md](teaching/07-thinking-questions-homework-and-answers.md): 思考题、作业和参考答案

### Getting Started

- [getting-started/quick-start.md](getting-started/quick-start.md): 本地启动、配置、访问地址
- [getting-started/ai-travel-agent-zero-to-one.md](getting-started/ai-travel-agent-zero-to-one.md): 面向新人的 AI 旅游 Agent 从 0 到 1 教程
- [getting-started/development-workflow.md](getting-started/development-workflow.md): 日常开发流程与提交前检查

### Product

- [product/product-requirements.md](product/product-requirements.md): 产品目标、用户价值、当前功能范围
- [agent-optimization-roadmap.md](agent-optimization-roadmap.md): Agent 优化方向与路线图

### Architecture

- [architecture/system-architecture.md](architecture/system-architecture.md): 整体系统架构与链路说明
- [architecture/harness-engineering-runtime-source-roadmap.md](architecture/harness-engineering-runtime-source-roadmap.md): 当前活动规划，聚焦 typed runtime seam、runtime source 替换与 ops/delivery contract 收口；其中 memory-aware source adapter 与 contract-first event emitter 迁移已于 2026-03-29 完成
- [architecture/agent-subagent-skills-architecture-roadmap.md](architecture/agent-subagent-skills-architecture-roadmap.md): Agent 应用层与 `Supervisor -> Subagents -> Skills` 演进路线图
- [architecture/infrastructure-foundations.md](architecture/infrastructure-foundations.md): 运行与部署、配置、readiness、CI、trace、metrics 总览
- [architecture/data-storage.md](architecture/data-storage.md): 数据落盘与持久化策略
- [architecture/agent-memory-mechanisms.md](architecture/agent-memory-mechanisms.md): Agent memory 的原子持久化、Top-K 注入与冲突澄清闭环
- [architecture/agent-p0-hardening-roadmap.md](architecture/agent-p0-hardening-roadmap.md): Agent 稳定性治理路线图
- [architecture/agent-dialogue-4-week-execution-plan.md](architecture/agent-dialogue-4-week-execution-plan.md): 对话链路迭代排期

### Governance

- [governance/README.md](governance/README.md): ADR / RFC / Design Review 统一入口与使用规则
- [governance/skills-market-onboarding.md](governance/skills-market-onboarding.md): 新 skill 接入 `schema + tests + docs + eval` 四件套清单
- [governance/adr/ADR-0001-governance-record-flow.md](governance/adr/ADR-0001-governance-record-flow.md): 统一治理记录流程的初始 ADR
- [governance/adr/ADR-0000-template.md](governance/adr/ADR-0000-template.md): ADR 模板
- [governance/rfcs/RFC-0000-template.md](governance/rfcs/RFC-0000-template.md): RFC 模板
- [governance/design-reviews/DR-0000-template.md](governance/design-reviews/DR-0000-template.md): Design Review 模板

### Reference

- [reference/api-reference.md](reference/api-reference.md): REST / SSE / 城市探索 / 分享接口
- [reference/openapi.snapshot.json](reference/openapi.snapshot.json): 当前 OpenAPI 契约快照
- [reference/sse-contract.snapshot.json](reference/sse-contract.snapshot.json): 当前 SSE 契约快照
- [reference/configuration-reference.md](reference/configuration-reference.md): 配置文件与环境变量
- [reference/project-structure.md](reference/project-structure.md): 目录结构与关键模块职责
- [reference/skills-market-catalog.md](reference/skills-market-catalog.md): 当前默认 skills market 的 owner、输入输出、selection policy 与治理字段
- [reference/naming-conventions.md](reference/naming-conventions.md): 命名约定
- [reference/backend-maintainer-playbook.md](reference/backend-maintainer-playbook.md): 后端维护与排障手册
- [reference/frontend-message-rendering.md](reference/frontend-message-rendering.md): 前端消息渲染与 `<think>` 折叠机制
- [../ops/observability/README.md](../ops/observability/README.md): Grafana dashboard 与 Prometheus alerts 资产

### Testing & Quality

- [testing/testing-guide.md](testing/testing-guide.md): 单测、集成测试、benchmark、回放
- `scripts/runtime_backup.py`: 运行数据备份
- `scripts/runtime_restore.py`: 运行数据恢复
- `scripts/runtime_prune.py`: 运行数据清理
- `scripts/runtime_doctor.py`: 运行态一键自检
- `scripts/runtime_ops_contracts.py`: runtime doctor / support bundle / release evidence 共享 report contract
- `scripts/export_openapi_snapshot.py`: OpenAPI 契约快照导出
- `scripts/export_sse_contract_snapshot.py`: SSE 契约快照导出
- `scripts/export_runtime_doctor_snapshot.py`: runtime doctor 契约快照导出
- `scripts/export_release_manifest.py`: release manifest 导出
- `scripts/release_harness_scorecard.py`: 发布前收口 benchmark / delivery / skills / subagent 质量证据
- `scripts/export_support_bundle.py`: 运行态支持包导出
- `scripts/bootstrap.py`: 跨平台本地依赖、虚拟环境与配置模板初始化入口
- `scripts/dev.py`: 本地开发、测试、infra 检查、compose 校验统一入口
- `scripts/docstring_audit.py`: Python docstring 覆盖率 + 低信息量治理审计脚本
- `frontend/tests/features/trip-plan/travelPlanDeliverySnapshot.test.ts`: 复用 frontend runtime golden fixture 回放最终 HTML 交付结果
- `scripts/agent_subagent_scorecard.py`: 生成 `research / planning / budget / verification` 的 replay scorecard 基线
- `reference/docstring-audit.low-info-baseline.json`: 当前低信息量 docstring 存量基线
- `scripts/complexity_budget.py`: 热点文件“只减不增”复杂度门禁脚本
- `reference/complexity-budget.json`: 当前热点文件复杂度预算基线
- `scripts/decision_record_audit.py`: ADR / RFC / Design Review 记录结构审计脚本
- `scripts/skills_market_audit.py`: 审计默认 skills market 是否补齐 `schema + tests + docs + eval` 四件套
- `scripts/runtime_contract_audit.py`: 审计 `AgentRuntime -> legacy_bridge -> legacy_runtime -> runtime_sources/runtime_event_emitters` 的 typed seam 是否保持显式 contract，并阻止 memory source-state 或 event assembly 漂回 shim
- `reference/runtime-doctor.snapshot.json`: runtime doctor typed report contract 快照
- `compose.yaml` / `Dockerfile*`: 支持通过 `PYTHON_BASE_IMAGE`、`NODE_BASE_IMAGE` 切换基础镜像
- [benchmarks/agent_benchmark_latest.md](benchmarks/agent_benchmark_latest.md): 最新 benchmark 报告
- [benchmarks/agent_benchmark_trend_latest.md](benchmarks/agent_benchmark_trend_latest.md): benchmark 趋势报告
- [benchmarks/agent_subagent_scorecard_latest.md](benchmarks/agent_subagent_scorecard_latest.md): 子 agent 协作覆盖 scorecard
- [benchmarks/release_harness_scorecard_latest.md](benchmarks/release_harness_scorecard_latest.md): release harness checklist / scorecard
- [benchmarks/agent_golden_eval_latest.json](benchmarks/agent_golden_eval_latest.json): golden eval 原始结果

## 文档维护建议

- 面向外部读者的信息优先放在 `README.md`
- 面向开发实现的细节放在 `docs/` 子目录
- benchmark、golden eval、replay 等运行产物只放在 `docs/benchmarks/`
- 每次大功能上线后，至少同步更新这 4 份文档：
  - `README.md`
  - `docs/README.md`
  - `docs/reference/api-reference.md`
  - `docs/product/product-requirements.md`
- 如果改动的是基础设施层（部署、配置、startup checks、trace、metrics、CI），额外同步：
  - `docs/architecture/infrastructure-foundations.md`
  - `docs/reference/configuration-reference.md`
  - `docs/testing/testing-guide.md`
