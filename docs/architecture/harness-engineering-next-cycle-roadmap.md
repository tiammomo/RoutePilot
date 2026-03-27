# Harness Engineering 下一阶段规划（2026-03-27）

## 1. 背景

截至 2026-03-27，上一轮 Harness Engineering 基线重构与总演进规划已经完成收口：

- `Contract / Application / Agent Runtime / Frontend Feature / Replay & Eval / Governance` 六条主线已全部落到代码、测试与 CI 门禁
- 前端主工作区与测试目录已经收口为按 feature 组织的结构，当前测试树稳定落在 `frontend/tests/features/`
- `docstring_audit`、`complexity_budget`、`decision_record_audit` 已全部接入本地 `dev.ps1 infra-check` 与 GitHub Actions

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

- 建立统一的 `artifact delivery descriptor`，收口 HTML 标题、摘要、卡片顺序、证据区块和分享元信息
- 把导出图片、分享短链、详情页 HTML 三条链路统一到同一份 descriptor，而不是各自拼装
- 为 HTML 结果建立 golden snapshot，避免模板改动引起结构或字段回退

### 3.2 Skills Market Harness

目标：

- 把 skills 从“代码里的工具封装”升级成“可注册、可版本化、可审计”的能力市场

建议动作：

- 为 skills 建立统一 metadata schema，明确 `name / owner / input / output / evidence / freshness / fallback`
- 为 subagent 补齐 skill selection policy，减少 prompt 内联的隐式能力选择
- 建立 skill onboarding checklist，要求新技能同时补齐 prompt、测试、eval 样本和文档

### 3.3 Runtime & Eval Harness

目标：

- 让多 agent 运行时继续摆脱 legacy graph 兼容层，并为 Agent 结果建立更清晰的质量面板

建议动作：

- 继续把 `AgentRuntime` 从旧 `run_travel_agent_streaming_with_memory` 兼容入口中解耦
- 为 `research / planning / budget / verification` 增加按子 agent 维度的 replay scorecard
- 把 HTML 交付结果纳入 benchmark，对 `artifact completeness / evidence presence / verification status / export stability` 建立阈值

## 4. 分阶段执行

### Phase A：Artifact Delivery 收口

- 统一 `trip-plan` 的 HTML / share / export descriptor
- 为最终交付页建立 snapshot fixture 与回放测试
- 让前端和导出链路都只消费 artifact delivery contract

### Phase B：Skills Market 治理

- 建立 skills metadata registry 与 onboarding 模板
- 补齐技能版本、责任人、证据要求和失败回退字段
- 让新 skill 接入必须经过 `schema + tests + docs + eval` 四件套

### Phase C：Runtime Decoupling

- 收口 supervisor 编排状态
- 逐步削薄 legacy graph 兼容入口
- 为 subagent 运行记录统一生成 execution receipt

### Phase D：Eval / Release 闭环

- 对 HTML 成品、artifact 完整度、skill 质量和 subagent 协作质量建立 scorecard
- 将 benchmark 门禁接入 CI / release checklist
- 在治理文档中固化“新增 agent 能力前先补 contract / eval / docs”的流程

## 5. 退出标准

满足以下条件后，这一轮规划可视为完成：

- 最终旅游结果可以稳定导出为 HTML 成品，并有 snapshot / replay 基线
- skills registry 拥有稳定 metadata 与 onboarding 规范
- 多 agent runtime 的关键协作结果可被 `scorecard + benchmark` 稳定评估
- 新增复杂度继续被 `docstring / complexity / decision-record / benchmark` 四类门禁约束

## 6. 当前第一优先级

建议从下面三项开始：

1. 建立 `artifact delivery descriptor`，统一 HTML / share / export 三条交付链
2. 建立 skills metadata schema 与 onboarding 模板
3. 为 subagent 结果建立 scorecard 基线，先覆盖 `research / planning / budget / verification`
