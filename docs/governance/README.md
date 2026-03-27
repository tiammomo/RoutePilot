# Governance Records

这套记录用来收口会长期影响 `moyuan-travel-agent` 的架构、流程和跨层决策。

它不是重复 `README` 或功能文档，而是专门回答三类问题：

- 这个决策为什么值得留下长期记录
- 这次变更是方案探索、正式决定，还是一次具体设计评审
- 后续同类改动应该去哪里补材料，而不是重新发明流程

## 什么时候用哪一种记录

### ADR

放在 [adr/](/D:/moyuan/moyuan-travel-agent/docs/governance/adr)。

适合记录：

- 已经决定采用的长期架构选择
- 会影响多个模块或多个阶段演进的工程规则
- 需要在未来被复用、被追溯、被 supersede 的决策

典型例子：

- 为什么要采用 artifact-first
- 为什么 CI 要对热点复杂文件做 line-budget 门禁
- 为什么 memory conflict resolution 要从 legacy graph 中拆出

### RFC

放在 [rfcs/](/D:/moyuan/moyuan-travel-agent/docs/governance/rfcs)。

适合记录：

- 还没最终拍板、但需要团队评审的方案
- 可能存在多条替代路径的中大型重构
- 会影响产品、架构、运维或前后端协作方式的提案

典型例子：

- 是否引入新的 provider / policy engine
- 是否把某条 feature 工作流切到新的 artifact contract
- 是否大规模替换 runtime orchestration 模式

### Design Review

放在 [design-reviews/](/D:/moyuan/moyuan-travel-agent/docs/governance/design-reviews)。

适合记录：

- 一次具体迭代或 PR 的设计边界
- 风险、回归矩阵、验证和 follow-ups
- 已经有大方向，但需要在实现前把本次切片讲清楚

典型例子：

- 这次只拆 `planning pipeline`，不动 `execution`
- 这次把 compare tab 改为 artifact history 优先，但不改 share payload

## 统一规则

1. 大改动先写 `RFC` 或 `Design Review`，定型后补 `ADR`。
2. 进入 `main` 的长期工程规则，尽量有对应 `ADR`。
3. 每条记录都要写 `Status:`，并带上必填章节。
4. 记录文件名按固定前缀：
   - `ADR-xxxx-*.md`
   - `RFC-xxxx-*.md`
   - `DR-xxxx-*.md`
5. `python scripts/decision_record_audit.py --strict` 会检查这些记录的基础结构，当前已接入本地 `dev.ps1 infra-check` 和 CI。

## 当前入口

- [adr/ADR-0000-template.md](/D:/moyuan/moyuan-travel-agent/docs/governance/adr/ADR-0000-template.md)
- [adr/ADR-0001-governance-record-flow.md](/D:/moyuan/moyuan-travel-agent/docs/governance/adr/ADR-0001-governance-record-flow.md)
- [rfcs/RFC-0000-template.md](/D:/moyuan/moyuan-travel-agent/docs/governance/rfcs/RFC-0000-template.md)
- [design-reviews/DR-0000-template.md](/D:/moyuan/moyuan-travel-agent/docs/governance/design-reviews/DR-0000-template.md)
