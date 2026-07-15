# RoutePilot V1 文档

本文档集只描述当前 V1 产品主线。仓库中的历史数据如果需要保留，必须经离线迁移工具导入；它们不构成旧应用、旧 API 或旧 Agent 的运行时兼容面。

## 用户

- [用户指南](product/user-guide.md)
  从直接问答、转成行程、重规划、证据、分享到归档恢复的完整体验路径。

## 架构与决策

- [RFC-0003：RoutePilot V1 已实现架构](governance/rfcs/RFC-0003-routepilot-full-rebuild-v1.md)
  系统边界、领域模型、Agent/A2A、RAG、Provider、安全与关键不变量。
- [契约说明](../schemas/README.md)
  Artifact 与 public event 的 JSON Schema 入口。

## 开发与扩展

- [本地开发指南](development/local-development.md)
  工具链、Compose、本机开发循环、分领域门禁和数据库变更。
- [API 与事件开发指南](development/api-guide.md)
  身份、幂等、CAS、SSE 恢复、错误结构和浏览器 BFF 边界。
- [Agent 与 A2A 扩展指南](development/agent-extension.md)
  Agent 角色判断、注册、执行器、恢复取消以及远程编排安全边界。
- [Artifact 与事件契约扩展](development/artifact-contracts.md)
  Python、JSON Schema、TypeScript、public projection 和测试同步流程。
- [Provider Gateway 扩展指南](development/provider-extension.md)
  新增实时事实端口、网络安全、缓存、freshness 和交付门禁。

## 运行与交付

- [V1 平台手册](operations/v1-platform.md)
  本地 Compose、预发 OIDC、数据库角色、租约恢复、健康检查与质量门禁。
- [RAG 知识摄取与检索 Runbook](operations/rag-ingestion.md)
  权限、许可、摄取、检索验证、更新和当前生命周期限制。
- [知识库建设与维护手册](operations/knowledge-base-maintenance.md)
  内置知识包、来源分层、批量发布、固定查询验收、版本切换和回滚。
- [故障排查手册](operations/troubleshooting.md)
  Compose、数据库、OIDC、Worker、Provider、RAG 与安全事件处理。
- [可观测性与告警基线](operations/observability.md)
  当前已有信号、真实限制、生产指标、告警和安全日志规则。
- [备份与恢复 Runbook](operations/backup-restore.md)
  PostgreSQL 逻辑备份、隔离恢复演练和生产 PITR 要求。
- [V1 数据迁移 Runbook](operations/v1-migration-runbook.md)
  显式离线 inventory、ImportedTripArchive backfill、reconciliation 与源数据保留边界。
- [安全策略](../.github/SECURITY.md)
  漏洞私密报告方式与仓库安全基线。
- [贡献指南](../CONTRIBUTING.md)与[变更记录](../CHANGELOG.md)
  提交边界、门禁、文档同步和面向用户的版本变化。

## 代码内说明

- [V1 API 控制平面](../backend/moyuan_web/v1/README.md)
- [A2A 运行边界](../agent/travel_agent/a2a/README.md)
- [Runtime V2 编排](../agent/travel_agent/runtime_v2/README.md)
- [RAG 检索边界](../agent/travel_agent/rag/README.md)
- [Provider Gateway](../agent/travel_agent/providers/README.md)
- [Web/BFF](../apps/web/README.md)

文档与实现发生冲突时，以版本化契约、Alembic migration 和通过质量门禁的代码为准，并在同一变更中修正文档。
