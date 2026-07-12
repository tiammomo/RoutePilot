# RoutePilot V1 文档

本文档集只描述当前 V1 产品主线。仓库中的历史数据如果需要保留，必须经离线迁移工具导入；它们不构成旧应用、旧 API 或旧 Agent 的运行时兼容面。

## 架构与决策

- [RFC-0003：RoutePilot V1 已实现架构](governance/rfcs/RFC-0003-routepilot-full-rebuild-v1.md)
  系统边界、领域模型、Agent/A2A、RAG、Provider、安全与关键不变量。
- [契约说明](../schemas/README.md)
  Artifact 与 public event 的 JSON Schema 入口。

## 运行与交付

- [V1 平台手册](operations/v1-platform.md)
  本地 Compose、预发 OIDC、数据库角色、租约恢复、健康检查与质量门禁。
- [V1 数据迁移 Runbook](operations/v1-migration-runbook.md)
  显式离线 inventory、ImportedTripArchive backfill、reconciliation 与源数据保留边界。
- [安全策略](../.github/SECURITY.md)
  漏洞私密报告方式与仓库安全基线。

## 代码内说明

- [A2A 运行边界](../agent/travel_agent/a2a/README.md)
- [RAG 检索边界](../agent/travel_agent/rag/README.md)
- [Provider Gateway](../agent/travel_agent/providers/README.md)

文档与实现发生冲突时，以版本化契约、Alembic migration 和通过质量门禁的代码为准，并在同一变更中修正文档。
