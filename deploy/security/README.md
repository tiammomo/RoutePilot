# Security Ops Assets

这里存放仓库的安全扫描与 secret-scan 配置，避免安全资产继续散落在根目录。

当前已收口：

- [`gitleaks.toml`](./gitleaks.toml)
  - CI 与本地 `gitleaks` 扫描共用的 allowlist / example-token 例外规则
- [`postgres-v1-init.sh`](./postgres-v1-init.sh)
  - 仅在空 V1 数据卷创建 migration/API/worker/outbox 分权角色与扩展
- [`postgres-v1-grants.sql`](./postgres-v1-grants.sql)
  - 每次 migration 后强制 V1 RLS，并应用最小 runtime grants
当前 CI 使用方式：

```bash
docker run --rm \
  -v "$PWD:/repo" \
  zricethezav/gitleaks:v8.27.2 \
  dir /repo --config /repo/deploy/security/gitleaks.toml --no-banner --redact
```

维护约定：

1. 只在确有必要时增加 allowlist。
2. 每条 allowlist 都应尽量限定到明确路径或明确 placeholder token。
3. 运行时角色不得复用 admin/migration credential；outbox BYPASSRLS 角色只能获得
   `v1_outbox_events` 权限。
4. 示例 env 保持空 secret；CI 只能使用明确的 synthetic placeholder。
5. 如果扫描或平台策略变化，同步更新
   `docs/operations/v1-platform.md` 与相关架构文档。
