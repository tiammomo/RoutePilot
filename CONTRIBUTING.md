# Contributing to RoutePilot V1

RoutePilot 只接受 V1 产品主线变更。不要恢复旧 Web、旧 API、旧 Agent、旧事件协议或运行时兼容开关。历史数据保留只能通过 `scripts/migration_v1/` 的离线流程。

## 开始之前

1. 阅读 [AGENTS.md](AGENTS.md) 和[已实现架构 RFC](docs/governance/rfcs/RFC-0003-routepilot-full-rebuild-v1.md)；
2. 按[本地开发指南](docs/development/local-development.md)安装依赖并启动状态服务；
3. 确认工作区现有修改的所有权，不覆盖无关用户变更；
4. 为功能选择明确代码域和最小测试范围。

## 变更原则

- PostgreSQL 是真相源，Redis 只投递；
- Run、A2A Task、Artifact version 生命周期独立；
- 所有 tenant 查询包含服务端 predicate 并保持 RLS；
- 浏览器只接收 public event 白名单和结构化 Artifact；
- Provider key、OIDC、数据库和模型凭据始终 server-only；
- schema 只通过 Alembic 修改；
- 网络 mutation 使用幂等和必要的 CAS/version；
- 不用兼容层掩盖契约或数据迁移问题。

## 开发流程

1. 先写清输入、输出、权限、失败和恢复边界；
2. 实现最小完整垂直切片；
3. 增加正常、拒绝、冲突、恢复和安全边界测试；
4. 同步用户、开发或运维文档；
5. 运行分领域门禁和 `git diff --check`；
6. 提交一个可独立构建和回退的原子 commit。

扩展指南：

- [Artifact 与事件契约扩展](docs/development/artifact-contracts.md)
- [Agent 与 A2A 扩展](docs/development/agent-extension.md)
- [Provider Gateway 扩展](docs/development/provider-extension.md)
- [API 与事件开发指南](docs/development/api-guide.md)

## 测试

```bash
python scripts/v1_quality_gate.py
git diff --check
```

文档变更至少运行：

```bash
python scripts/v1_quality_gate.py --only docs
```

不要删除、跳过或放宽测试来适配实现。需要真实 PostgreSQL/Redis 的场景使用 integration marker，并保持 CI stateful job 可重复运行。

## Commit 与安全

- 使用简洁的 Conventional Commit 风格，例如 `feat(web): ...`、`docs(ops): ...`；
- 不提交 `.env`、token、API key、数据库 dump、真实旅行数据或渲染后的含 secret 配置；
- 不在测试 fixture 中放看起来真实的凭据；
- 发现漏洞按 [.github/SECURITY.md](.github/SECURITY.md) 私密报告，不先公开 Issue；
- 用户可见行为变化更新 [CHANGELOG.md](CHANGELOG.md)。

Pull Request 应说明结果、风险、验证命令、数据库/契约影响，以及失败时如何恢复。
