# Harness Engineering 下一阶段规划（2026-03-27）

## 1. 背景

截至 2026-03-27，上一轮 Harness Engineering 基线重构与总演进规划已经完成收口：

- `Contract / Application / Agent Runtime / Frontend Feature / Replay & Eval / Governance` 六条主线已全部落到代码、测试与 CI 门禁
- 前端主工作区与测试目录已经收口为按 feature 组织的结构，当前测试树稳定落在 `frontend/tests/features/`
- `docstring_audit`、`complexity_budget`、`decision_record_audit` 已全部接入本地 `python scripts/dev.py infra-check` 与 GitHub Actions

本文件从这一基线继续往下推进，作为新的活动规划入口。

## 2. 当前目标

下一阶段的重点不再是“把系统从巨石拆开”，而是让多 agent 结果真正进入稳定交付闭环：

1. 让 `artifact -> HTML / share / export` 成为稳定的一等交付路径
2. 让 `Supervisor -> Subagents -> Skills` 从“能力骨架”升级为“可治理、可评测、可扩展”的运行体系
3. 让评测、发布、运营文档和质量门禁能持续约束后续新增复杂度

## 3. 三条主线

### 3.1 Delivery Harness

目标：

- 把旅游结果从“结构化 artifact”进一步推进成“可直接交付给用户的 HTML 成品”

建议动作：

- [已完成 2026-03-27] 建立统一的 `artifact delivery descriptor`，当前 `frontend/src/components/travel-plan-toolkit/shared/artifact.ts` 已统一收口 HTML 标题、摘要、卡片区块、分享文本、导出文件名与 overview 指标
- [已完成 2026-03-27] 把导出图片、分享短链、详情页 HTML 三条链路统一到同一份 descriptor，当前 `useTravelPlanToolkitActions.ts` 已让 share/export 直接消费统一 descriptor，share link 也已开始持久化 `html_content`
- [已完成 2026-03-27] 为 HTML 结果建立 golden snapshot，当前 `frontend/tests/features/trip-plan/travelPlanDeliverySnapshot.test.ts` 已基于 `tests/golden/frontend_chat_runtime_golden_fixture.json` 回放并固化 `frontend/tests/features/trip-plan/__snapshots__/travelPlanDeliverySnapshot.test.ts.snap`

### 3.2 Skills Market Harness

目标：

- 把 skills 从“代码里的工具封装”升级成“可注册、可版本化、可审计”的能力市场

建议动作：

- [已完成 2026-03-27] 为 skills 建立统一 metadata schema，当前 `agent/travel_agent/contracts/skills.py` 与 `agent/travel_agent/skills/registry.py` 已显式收口 `name / owner / input / output / evidence / freshness / fallback / docs / eval`
- [已完成 2026-03-27] 为 subagent 补齐 skill selection policy，当前 `agent/travel_agent/subagents/base.py`、`agent/travel_agent/subagents/registry.py` 与 `agent/travel_agent/runtime/agent_runtime.py` 已显式暴露 `selection_policy()`、`selection_plan()` 和 `subagent_skill_policies`
- [已完成 2026-03-27] 建立 skill onboarding checklist，当前已新增 [docs/governance/skills-market-onboarding.md](/D:/moyuan/moyuan-travel-agent/docs/governance/skills-market-onboarding.md) 与 [docs/reference/skills-market-catalog.md](/D:/moyuan/moyuan-travel-agent/docs/reference/skills-market-catalog.md)

### 3.3 Runtime & Eval Harness

目标：

- 让多 agent 运行时继续摆脱 legacy graph 兼容层，并为 Agent 结果建立更清晰的质量面板

建议动作：

- 继续把 `AgentRuntime` 从旧 `run_travel_agent_streaming_with_memory` 兼容入口中解耦
- [已完成 2026-03-27] 为 `research / planning / budget / verification` 增加按子 agent 维度的 replay scorecard，当前 `scripts/agent_subagent_scorecard.py` 已固化 `docs/benchmarks/agent_subagent_scorecard_latest.{json,md}`
- [已完成 2026-03-28] 把 HTML 成品、artifact 完整度和 skill 质量纳入 release checklist，当前 `scripts/release_harness_scorecard.py` 已统一读取 `benchmark / golden eval / subagent scorecard / delivery snapshot / skills market` 并生成 `docs/benchmarks/release_harness_scorecard_latest.{json,md}`

## 4. 分阶段执行

### Phase A：Artifact Delivery 收口

- [已完成 2026-03-27] 统一 `trip-plan` 的 HTML / share / export descriptor
- [已完成 2026-03-27] 为最终交付页建立 snapshot fixture 与回放测试
- [已完成 2026-03-27] 让前端和导出链路都只消费 artifact delivery contract

### Phase B：Skills Market 治理

- [已完成 2026-03-27] 建立 skills metadata registry 与 onboarding 模板
- [已完成 2026-03-27] 补齐技能版本、责任人、证据要求和失败回退字段
- [已完成 2026-03-28] 让新 skill 接入必须经过 `schema + tests + docs + eval` 四件套，当前 `scripts/skills_market_audit.py --strict` 已把 `docs_path / test_fixture / eval_fixture / onboarding_doc` 与输入输出 contract 一并纳入治理门禁

### Phase C：Runtime Decoupling

- [已完成 2026-03-28] 收口 supervisor 编排状态，当前 `agent/travel_agent/contracts/supervisor_orchestration.py` 已统一定义 `SupervisorRunRequest / SupervisorPlanPreviewRequest / SupervisorRuntimeContext`，`AgentRuntime` 与 `runtime/legacy_bridge.py` 通过显式 contract 传递 streaming / preview 编排请求
- 逐步削薄 legacy graph 兼容入口
- [已完成 2026-03-28] 为 subagent 运行记录统一生成 execution receipt，当前 `agent/travel_agent/contracts/execution_receipt.py` 与 `agent/travel_agent/runtime/agent_runtime.py` 已把阶段、工具、artifact patch 收口进 `done` 事件，`web/moyuan_web/services/chat/stream_diagnostics.py` 也会把它持久化到 assistant diagnostics
- [已完成 2026-03-28] 抽出 `AgentRuntime -> legacy graph` 的显式 bridge，当前 `agent/travel_agent/runtime/legacy_bridge.py` 已统一承接 streaming / preview / diagnostics 三类兼容调用，`AgentRuntime` 不再直接 import 旧 `graph.builder` 入口函数
- [已完成 2026-03-28] 把 legacy graph 归一化 runtime 事件收口成显式 contract，当前 `agent/travel_agent/contracts/supervisor_events.py` 已统一定义 `stage / reasoning / chunk / tool_start / tool_end / done` 六类 payload，`agent/travel_agent/graph/builder.py` 不再继续手搓大段事件字典
- [已完成 2026-03-28] 把 legacy graph 的兼容执行入口整体迁到独立 shim，当前 `agent/travel_agent/graph/legacy_runtime.py` 已承接 `run / stream / stream_with_memory / plan preview / diagnostics`，`agent/travel_agent/graph/builder.py` 进一步退化为图组装与编译模块
- [已完成 2026-03-28] 让 legacy runtime shim 直接消费 supervisor request/context contract，当前 `agent/travel_agent/graph/legacy_runtime.py` 已新增 `stream_supervisor_run()` 与 `generate_supervisor_plan_preview()`，`agent/travel_agent/runtime/legacy_bridge.py` 不再手工重组 streaming / preview 所需的一长串 kwargs
- [已完成 2026-03-28] 把 legacy plan preview 结果收口成显式 contract，当前 `agent/travel_agent/contracts/supervisor_orchestration.py` 已新增 `SupervisorPlanPreview`，`agent/travel_agent/graph/legacy_runtime.py` 与 `agent/travel_agent/runtime/legacy_bridge.py` 会先返回 typed preview payload，`agent/travel_agent/runtime/agent_runtime.py` 再统一转成 enriched preview dict
- [已完成 2026-03-28] 把 legacy tool health diagnostics 收口成显式 contract，当前 `agent/travel_agent/contracts/supervisor_orchestration.py` 已新增 `SupervisorToolHealthDiagnostics / SupervisorToolHealthEntry`，`agent/travel_agent/graph/legacy_runtime.py` 与 `agent/travel_agent/runtime/legacy_bridge.py` 会先返回 typed diagnostics payload，`agent/travel_agent/runtime/agent_runtime.py` 再统一合并 skills/subagents 元数据

### Phase D：Eval / Release 闭环

- [已完成 2026-03-27] 对 subagent 协作质量建立 replay scorecard 基线，当前已覆盖 `research / planning / budget / verification`
- [已完成 2026-03-28] 对 HTML 成品、artifact 完整度、skill 质量建立 release harness scorecard
- [已完成 2026-03-28] 将 benchmark / delivery / skills checklist 接入 CI / release checklist，当前 `ci.yml`、`python scripts/dev.py infra-check` 与 `export_release_manifest.py` 已统一纳入 release harness scorecard
- [已完成 2026-03-28] 收口本地开发入口并清理 Windows 专用脚本，当前根目录 dev.ps1 与 scripts/bootstrap.ps1 已移除，统一改为 scripts/dev.py / scripts/bootstrap.py，并同步更新 README、开发流程、测试指南与架构文档
- [已完成 2026-03-28] 统一脚本 bootstrap 加载方式并把新入口接入 `pytest + ruff + mypy`，当前 `scripts/dev.py`、`scripts/bootstrap.py` 以及 benchmark / replay / runtime / snapshot 脚本都已兼容“直接执行 / 包内导入 / spec 加载单测”三种运行路径
- [已完成 2026-03-28] 在治理文档中固化“新增 agent 能力前先补 contract / eval / docs”的流程，当前 onboarding 文档、skills catalog、README、测试指南和 `python scripts/dev.py infra-check` 已统一引用 skills market audit

## 5. 退出标准

满足以下条件后，这一轮规划可视为完成：

- 最终旅游结果可以稳定导出为 HTML 成品，并有 snapshot / replay 基线
- skills registry 拥有稳定 metadata 与 onboarding 规范
- 多 agent runtime 的关键协作结果可被 `scorecard + benchmark` 稳定评估
- 新增复杂度继续被 `docstring / complexity / decision-record / benchmark` 四类门禁约束

## 6. 当前第一优先级

建议从下面三项开始：

1. [已完成 2026-03-27] 建立 `artifact delivery descriptor`，统一 HTML / share / export 三条交付链
2. [已完成 2026-03-27] 建立 skills metadata schema 与 onboarding 模板
3. [已完成 2026-03-27] 为 subagent 结果建立 scorecard 基线，先覆盖 `research / planning / budget / verification`

下一步建议从下面三项开始：

1. 继续把 `AgentRuntime` 从 legacy graph 兼容入口中解耦
2. [已完成 2026-03-28] 让新 skill 接入必须经过 `schema + tests + docs + eval` 四件套，并补齐相应治理门禁
3. 继续削薄 runtime 和 legacy graph 之间的兼容层，让 `AgentRuntime` 真正脱离旧 `run_travel_agent_streaming_with_memory` 入口
### Update 2026-03-28

- [已完成 2026-03-28] 稳定前端默认验证入口，当前 `frontend/vitest.config.ts` 已把 `vitest` worker 上限固定为 `2`，`frontend/package.json` 的 `npm run build` 已切到 `next build --webpack`，`scripts/dev.py` 也会在 Windows 上自动解析 `npm.cmd`，让默认 `npm run test:run / npm run build / python scripts/dev.py test` 都能直接复用。
- [已完成 2026-03-28] 技能市场治理门禁已落地，当前 `agent/travel_agent/contracts/skills.py` 新增 `market_metadata.test_fixture`，默认 skill registry 已补齐 `schema / tests / docs / eval` 四件套指针，`scripts/skills_market_audit.py`、`ci.yml` 与 `python scripts/dev.py infra-check` 会统一拦截缺失治理信息的新 skill。
- [已完成 2026-03-28] 稳定 runtime doctor 的治理链韧性，当前 `scripts/runtime_doctor.py` 在遇到被占用的 runtime 文件时会把 `runtime_files` 标记为 `degraded` 并保留错误类型，不再让 `python scripts/dev.py infra-check` 因单个锁定文件直接异常退出。
- [已完成 2026-03-28] Runtime decoupling 已新增 bridge seam，当前 `AgentRuntime` 通过 `runtime/legacy_bridge.py` 注入旧 graph 兼容调用，测试也已改为围绕 bridge 做依赖注入，后续继续替换 legacy graph 时不再需要大面积改动 runtime 主编排。
- [已完成 2026-03-28] supervisor 编排状态已从散落 kwargs 收口成显式 contract，当前 `AgentRuntime` 会先构造 `SupervisorRunRequest / SupervisorPlanPreviewRequest` 与 `SupervisorRuntimeContext`，再交给 `runtime/legacy_bridge.py` 做兼容分发，后续替换 legacy graph 时可以优先替换 request/context 消费方，而不是继续扩散签名。
- [已完成 2026-03-28] legacy graph 的 normalized runtime events 已从 `graph/builder.py` 内联字典收口成 `agent/travel_agent/contracts/supervisor_events.py`，当前 bridge 继续替换时可以先稳定事件 contract，再逐步替换底层 graph 执行源。
- [已完成 2026-03-28] legacy graph 的执行 shim 已从 `graph/builder.py` 拆到 `graph/legacy_runtime.py`，当前 `AgentRuntime -> legacy bridge -> legacy_runtime` 的兼容链已显式成层，后续继续替换 legacy graph 时可以优先替换最内层执行实现，而不是继续挤占 builder。
- [已完成 2026-03-28] legacy runtime shim 现在也直接消费 `SupervisorRunRequest / SupervisorPlanPreviewRequest / SupervisorRuntimeContext`，当前 `runtime/legacy_bridge.py` 只负责桥接显式 contract，不再继续重组 legacy streaming / preview 参数链；对应 seam 已补齐 [tests/test_legacy_runtime_contract_unit.py](/D:/moyuan/moyuan-travel-agent/tests/test_legacy_runtime_contract_unit.py)。
- [已完成 2026-03-28] legacy preview payload 现在也通过显式 `SupervisorPlanPreview` contract 返回，当前 `runtime/legacy_bridge.py` 与 `graph/legacy_runtime.py` 已不再把 preview 结果继续裸露成 loose dict；对应 enriched preview 兼容链已补齐到 [tests/test_agent_runtime_phase1_unit.py](/D:/moyuan/moyuan-travel-agent/tests/test_agent_runtime_phase1_unit.py) 和 [tests/test_legacy_runtime_contract_unit.py](/D:/moyuan/moyuan-travel-agent/tests/test_legacy_runtime_contract_unit.py)。
- [已完成 2026-03-28] legacy tool health diagnostics 现在也通过显式 `SupervisorToolHealthDiagnostics` contract 返回，当前 `runtime/legacy_bridge.py` 与 `graph/legacy_runtime.py` 已不再把 diagnostics 结果继续裸露成 loose dict；对应兼容链已补齐到 [tests/test_agent_runtime_config_unit.py](/D:/moyuan/moyuan-travel-agent/tests/test_agent_runtime_config_unit.py)、[tests/test_skill_registry_unit.py](/D:/moyuan/moyuan-travel-agent/tests/test_skill_registry_unit.py) 和 [tests/test_legacy_runtime_contract_unit.py](/D:/moyuan/moyuan-travel-agent/tests/test_legacy_runtime_contract_unit.py)。
