# RoutePilot V1 历史数据离线导入 Runbook

工具入口：`python -m scripts.migration_v1`

该工具不是产品运行时、兼容层或流量切换器。它只提供 `inventory`、`backfill` 和 `verify`，把管理员明确选择保留的历史记录导入为只读 `ImportedTripArchive@1`。

## 安全边界

- 源数据必须是停止变化的快照或处于明确的短暂停写窗口；工具不捕获在线增量。
- 源凭据只读，目标使用限时 migration role。
- owner/tenant 映射必须由管理员显式提供；禁止根据 session ID、邮箱相似度或访问者猜测。
- 导入内容丢弃 reasoning、tool/raw result、diagnostics、内部错误/stack、HTML、cookie、token、password 和 API key。
- 历史 share token/session ID 不进入 Artifact，也不会变成 V1 分享能力。
- 报告可能含 source ID，只能写到权限为 `0700/0600` 的受限运维目录。
- 工具不会删除或修改源数据，不会调用 `create_all`，也不会更改部署流量。

## 前置条件

1. V1 PostgreSQL 已执行 Alembic head，存在 Trip/Member/Artifact/ArtifactVersion 表。
2. 已生成并人工审核 owner mapping。
3. 已确定源快照、法律保留期和目标恢复点。
4. 已在非生产环境用相同输入完成 dry-run 与 verify。

owner mapping 示例：

```json
{
  "schema": "routepilot.v1.owner-mapping@1",
  "mappings": {
    "session:source-session-001": {
      "tenant_id": "tenant-beijing",
      "owner_id": "user-42",
      "locale": "zh-CN",
      "timezone": "Asia/Shanghai"
    }
  }
}
```

无法确认 owner 的记录必须显式映射到隔离 tenant 和待审核 synthetic owner；不存在隐式 fallback。

## 1. Inventory

```bash
umask 077
.venv/bin/python -m scripts.migration_v1 inventory \
  --sessions-file /readonly/source/sessions.json \
  --share-links-file /readonly/source/share-links.json \
  --owner-mapping /secure/routepilot/owner-mapping.json \
  --file-data-root /readonly/source \
  --output /secure/routepilot/inventory.json
```

SQL 源可通过只读 `ROUTEPILOT_LEGACY_DATABASE_URL` 提供。inventory 记录 count、checksum、owner 映射校验和与文件决策，不读取 checkpoint 内部对象。

人工确认：

- `owner_unresolved_count == 0`；
- `blocking_issues == []`；
- source count 与 checksum 符合冻结快照；
- 每个文件的 retain/archive/drop 决策已审批。

## 2. Dry-run 与 Backfill

```bash
export ROUTEPILOT_V1_DATABASE_URL='postgresql+psycopg://...'
.venv/bin/python -m scripts.migration_v1 backfill \
  --sessions-file /readonly/source/sessions.json \
  --share-links-file /readonly/source/share-links.json \
  --inventory /secure/routepilot/inventory.json \
  --owner-mapping /secure/routepilot/owner-mapping.json \
  --archive-manifest /secure/routepilot/archive-manifest.json \
  --state /secure/routepilot/backfill-state.json \
  --batch-size 100 \
  --output /secure/routepilot/backfill-dry-run.json
```

无 `--apply` 时不写目标、state 或 manifest。审核 `dry_run_ready`、selected/pending count 和批次数后，使用完全相同参数增加 `--apply`。

每批 Trip、owner membership、Artifact 与 ArtifactVersion 在一个事务中提交。目标 ID 从 source key 确定性生成；重跑只验证相同内容，遇到同 ID 不同内容立即停止，绝不覆盖 V1 数据。

`backfill-state.json` 保存请求 hash、最后提交 cursor 和计数。中断后以完全相同参数重跑；不得手工移动 cursor 或修改请求 hash。

## 3. Verify

```bash
.venv/bin/python -m scripts.migration_v1 verify \
  --sessions-file /readonly/source/sessions.json \
  --share-links-file /readonly/source/share-links.json \
  --inventory /secure/routepilot/inventory.json \
  --owner-mapping /secure/routepilot/owner-mapping.json \
  --archive-manifest /secure/routepilot/archive-manifest.json \
  --output /secure/routepilot/reconciliation.json
```

verify 检查 source/manifest/target counts、canonical hashes、owner membership、tenant 一致性、Trip current Artifact 引用、孤儿与跨租户引用。只有 `passed=true` 且 `blocking_issue_count=0` 才算导入完成。

## 失败处理

- source fingerprint 或 owner mapping 变化：废弃本轮 state，重新 inventory。
- 目标冲突：停止并人工核查，不覆盖或删除目标记录。
- 事务中断：以相同参数重跑，从已提交 cursor 恢复。
- reconciliation 失败：目标导入批次保持只读隔离，修复投影/映射后重新生成 inventory 并导入新的确定性批次。
- 源数据始终保留到法律保留和审计批准完成；删除源数据不属于本工具权限。
