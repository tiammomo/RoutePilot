# ADR-0001 Governance Record Flow

## Status

Status: accepted

## Context

`moyuan-travel-agent` 已经进入持续的 harness engineering 演进期。重构不再只是单文件调整，而是会同时影响：

- Agent Runtime
- Web API contract
- Frontend feature workspace
- CI / quality gate / release governance

如果这些变更只留在 PR 描述或零散文档中，后续团队会很难回答：

- 某条规则到底是长期决策还是一次试验
- 哪些改动应该先提案再实施
- 哪些工程门禁是“临时做法”，哪些是已经正式采纳的规则

## Decision

统一采用三类治理记录：

- `ADR`
  记录已经采纳的长期架构决策
- `RFC`
  记录尚未最终拍板、但需要评审的中大型提案
- `Design Review`
  记录一次具体实现切片的目标、风险、验证和 follow-ups

并引入统一规则：

- 长期架构规则进入 `main` 时，尽量补对应 `ADR`
- 中大型跨层改动，先写 `RFC` 或 `Design Review`
- 所有记录文件使用固定命名前缀和基础章节
- 用 `scripts/decision_record_audit.py --strict` 做结构审计，防止流程再次漂移成口头约定

## Consequences

正面影响：

- 大改动有稳定落点，不再只靠 PR 描述承接上下文
- 架构决策、提案和单次实现评审之间的边界会更清楚
- 后续 teaching / architecture 文档可以引用这些记录，而不是重复解释背景

代价与约束：

- 团队需要在大改动前多写一层结构化说明
- 需要维护模板与审计脚本，避免流程本身失效

后续跟进：

- 后续如出现跨层大改动，优先新增 `RFC` 或 `Design Review`
- 如某条 RFC 最终落地，需要补对应 `ADR`
