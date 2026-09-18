# RoutePilot 文档中心

[项目首页](../README.md) · [English overview](../README.en.md)

按你要完成的任务选择入口。当前文档描述 V1 产品主线；全球多语言体验与独立 AgentOps 的交付状态见首页[迭代方向](../README.md#迭代方向)。详细指南目前以中文为主。

## 从这里开始

| 你要做什么 | 先读 | 然后读 |
| --- | --- | --- |
| 了解和体验旅行助手 | [项目首页与快速开始](../README.md#快速开始) | [用户指南](product/user-guide.md) |
| 修改 Web、API 或 Agent | [本地开发](development/local-development.md) | [贡献指南](../CONTRIBUTING.md) |
| 部署一套完整服务 | [平台手册](operations/v1-platform.md) | [故障排查](operations/troubleshooting.md) |
| 给系统增加旅行知识 | [知识库维护](operations/knowledge-base-maintenance.md) | [RAG 摄取与检索](operations/rag-ingestion.md) |
| 接入外部实时数据 | [Provider 扩展](development/provider-extension.md) | [Provider 能力与配置](../agent/travel_agent/providers/README.md) |
| 理解架构与演进边界 | [架构 RFC](governance/rfcs/RFC-0003-routepilot-full-rebuild-v1.md) | [独立 AgentOps 方向](../README.md#独立-agentops) |

## 使用产品

- [用户指南](product/user-guide.md)：直接问答、转成行程、重规划、来源与风险、历史版本、分享和归档恢复。
- [变更记录](../CHANGELOG.md)：已记录的用户、开发者和运维行为变化。

新建数据库不会自动发布内置知识；首次体验前需按知识库手册完成发布。数据覆盖、可选第三方配置和降级行为集中说明在首页[数据接入](../README.md#数据与第三方服务)。

## 理解和扩展系统

| 指南 | 解决的问题 |
| --- | --- |
| [架构 RFC](governance/rfcs/RFC-0003-routepilot-full-rebuild-v1.md) | 产品领域、系统边界、Agent/A2A、RAG、Provider 与关键不变量 |
| [本地开发](development/local-development.md) | 工具链、完整栈启动、开发循环、测试与数据库变更 |
| [API 与事件](development/api-guide.md) | 身份、幂等、CAS、SSE 恢复、错误结构与 BFF 边界 |
| [Agent 与 A2A 扩展](development/agent-extension.md) | 角色、注册、执行器、恢复取消与远程编排 |
| [Artifact 与事件契约](development/artifact-contracts.md) | Python、JSON Schema、TypeScript 与公开投影的同步流程 |
| [Provider Gateway 扩展](development/provider-extension.md) | 外部事实接口、网络边界、缓存、时效与验收 |
| [贡献指南](../CONTRIBUTING.md) | 变更范围、提交要求、检查与文档同步 |

## 部署和维护

| 指南 | 解决的问题 |
| --- | --- |
| [平台手册](operations/v1-platform.md) | Compose、OIDC、数据库角色、租约恢复与健康检查 |
| [RAG 摄取与检索](operations/rag-ingestion.md) | 权限、许可、摄取、检索验证和知识生命周期 |
| [知识库建设与维护](operations/knowledge-base-maintenance.md) | 内置包部署、来源审核、固定查询验收、版本切换与回滚 |
| [故障排查](operations/troubleshooting.md) | 启动、数据库、登录、Worker、Provider 与检索异常 |
| [可观测性与告警](operations/observability.md) | 当前信号、能力限制、指标、告警与安全日志 |
| [备份与恢复](operations/backup-restore.md) | PostgreSQL 备份、隔离恢复演练与生产 PITR 要求 |
| [离线数据迁移](operations/v1-migration-runbook.md) | 历史数据盘点、只读归档导入、校验与源数据保留 |
| [安全策略](../.github/SECURITY.md) | 漏洞私密报告与安全基线 |

## 按代码模块查阅

| 模块 README | 说明 |
| --- | --- |
| [Web / BFF](../apps/web/README.md) | 前端开发、服务端配置与浏览器登录 |
| [V1 API 控制平面](../backend/moyuan_web/v1/README.md) | 路由、存储、Worker 与分享职责 |
| [A2A](../agent/travel_agent/a2a/README.md) | 协议、持久任务、幂等、取消与恢复 |
| [Runtime V2](../agent/travel_agent/runtime_v2/README.md) | 问答与规划阶段编排 |
| [RAG](../agent/travel_agent/rag/README.md) | 租户检索、知识生命周期与降级 |
| [Provider Gateway](../agent/travel_agent/providers/README.md) | 已实现外部能力、配置与缓存边界 |
| [契约 Schema](../schemas/README.md) | JSON Schema 生成与版本规则 |

## 保持文档准确

新增功能时，在同一变更中更新对应指南、入口链接和[变更记录](../CHANGELOG.md)。首页中文与英文版本须同步维护；计划、开发分支能力与当前分支实现须明确区分。运行：

```bash
.venv/bin/python scripts/v1_quality_gate.py --only docs
git diff --check
```

文档门禁检查必需文档、索引覆盖、仓库内链接和 Compose env 一致性。执行命令前的依赖安装见[本地开发](development/local-development.md)。
