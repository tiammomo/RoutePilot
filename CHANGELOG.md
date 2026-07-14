# Changelog

本文记录用户、开发者和运维人员可观察的 RoutePilot V1 变化。Git commit 仍是完整实现历史。

## Unreleased

### Added

- 用户完整问答、转行程、重规划、分享和归档指南。
- API、Agent/A2A、Artifact/public event 和 Provider 扩展指南。
- RAG 摄取、故障排查、可观测性以及 PostgreSQL 备份恢复 Runbook。
- 文档覆盖、仓库内链接和 Compose env 一致性自动门禁。
- PostgreSQL/Redis dependency readiness，以及 bearer token 保护的低基数 Prometheus HTTP 指标。
- RAG 文档清单、CAS/幂等保护的发布/隔离/下线生命周期与命令审计。
- 原子、私有、带 checksum/manifest 和 archive 结构校验的 Compose 备份工具。

### Changed

- Run lease/reclaim、Provider timeout/allowlist 和 Worker 日志级别可以通过 V1 env 文件覆盖。
- 疑似 prompt injection 的摄取文档默认隔离，管理员复核发布前不参与检索。
- 平台文档明确区分已实现的依赖 readiness/基础指标与仍待平台补充的 Worker 指标、集中 telemetry 和 HA 能力。

## 1.0.0 - 2026-07-12

### Added

- Artifact-first 旅行问答与正式规划工作台。
- FastAPI V1 控制平面、PostgreSQL/RLS、Redis Streams 和 transactional outbox。
- A2A 1.0 Answering、Research、Planner、Validation 和 Semantic Verifier。
- PostgreSQL FTS + 可选 pgvector RAG，以及 AMap Provider Gateway。
- OIDC BFF、结构化 public event、版本化 Artifact 和安全只读分享。

### Removed

- 旧前端、旧业务 API、旧 Agent 运行时及隐式历史数据读取。
