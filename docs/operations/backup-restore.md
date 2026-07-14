# PostgreSQL 备份与恢复 Runbook

PostgreSQL 是 Trip、Run、Artifact、A2A Task、RAG 和 outbox 的真相源。Redis 只负责投递，不是业务备份来源。本手册提供单节点 Compose 的逻辑备份与隔离恢复演练基线；生产必须使用托管备份、WAL/PITR、加密和跨故障域副本。

## 恢复目标

正式环境上线前必须定义并审批：

- RPO：最多允许丢失多少已提交事务；
- RTO：从事件开始到恢复服务的最长时间；
- 备份频率、保留期、加密和访问角色；
- PITR/WAL 归档与恢复点选择；
- 恢复演练频率和成功标准。

没有经过恢复演练的备份不能视为可靠。

## 单节点逻辑备份

推荐使用仓库工具创建权限受限、原子落盘并经过 `pg_restore --list` 结构检查的 custom-format dump：

```bash
umask 077
mkdir -p /secure/routepilot/backups
chmod 700 /secure/routepilot/backups
python scripts/v1_backup.py \
  --env-file deploy/compose/.env.v1.local \
  create --output-dir /secure/routepilot/backups
```

工具通过 Compose 容器执行 `pg_dump`，不会把数据库密码放入命令行。每次成功会生成权限为 `600` 的三个绑定文件：

- `routepilot-<UTC>.dump`；
- `.dump.sha256`；
- `.dump.manifest.json`，包含大小、checksum、Git commit、Alembic revision、PostgreSQL image ID 和 Compose project。

创建后或从离线存储取回时重新验证：

```bash
python scripts/v1_backup.py \
  --env-file deploy/compose/.env.v1.local \
  verify /secure/routepilot/backups/routepilot-<UTC>.dump
```

验证会拒绝宽松文件权限、checksum/manifest 不一致和不可读取的 archive。它不是恢复演练：备份文件可能包含私人旅行和知识库内容，仍必须加密、限制读取并定期执行下面的隔离恢复。

## 一致性要求

`pg_dump` 提供事务一致的逻辑快照，但不提供连续时间恢复。需要近零 RPO 时使用 WAL/PITR。不要单独备份 Redis 并把它当成业务状态；数据库恢复后，应启动空的受控 Redis 投递层，由未发布 outbox 和数据库租约恢复工作。

## 隔离恢复演练

恢复演练必须使用独立 Compose project、独立端口、独立 volume 和新生成的测试 secret，绝不能覆盖当前运行栈。

1. 从 `deploy/compose/v1.env.example` 创建权限为 `600` 的 restore env；
2. 为所有必填 secret 生成新值；
3. 将 `ROUTEPILOT_POSTGRES_PORT` 改为未占用端口，例如 `45434`；
4. 只启动隔离 PostgreSQL：

   ```bash
   docker compose --project-name routepilot-v1-restore \
     --env-file /secure/routepilot/restore.env \
     --file deploy/compose/v1.yaml up --build --detach postgres
   ```

5. 等待隔离容器 healthy；
6. 将 dump 恢复到隔离数据库：

   ```bash
   backup=/secure/routepilot/backups/routepilot-<UTC>.dump
   docker compose --project-name routepilot-v1-restore \
     --env-file /secure/routepilot/restore.env \
     --file deploy/compose/v1.yaml exec --no-TTY postgres \
     pg_restore --username routepilot_admin --dbname routepilot \
     --clean --if-exists --no-owner --no-acl < "$backup"
   ```

7. 运行 Alembic head 和 reviewed grants：

   ```bash
   docker compose --project-name routepilot-v1-restore \
     --env-file /secure/routepilot/restore.env \
     --file deploy/compose/v1.yaml run --rm migration
   ```

8. 使用只读核对查询检查表数量、Alembic revision、Trip 当前 Artifact 引用、孤儿、tenant/RLS 和 A2A/Run 状态；
9. 记录恢复耗时、checksum、结果和偏差；
10. 审核完成后才删除隔离 restore project。确认 project name 无误后执行：

   ```bash
   docker compose --project-name routepilot-v1-restore \
     --env-file /secure/routepilot/restore.env \
     --file deploy/compose/v1.yaml down --volumes
   ```

最后一步只允许删除明确命名的演练项目。执行前再次确认没有指向当前生产/开发 project。

## 恢复后验证

- Alembic revision 为当前 head；
- 四个数据库角色存在且 grants/RLS 已复核；
- Trip、Run、Artifact version、A2A Task、RAG 和 outbox 数量符合备份清单；
- current Artifact 引用存在，没有跨 tenant/孤儿引用；
- 未发布 outbox 可以重新投递；
- Redis 使用新的空投递状态；
- API、Worker、A2A、RAG 和分享集成测试通过；
- 旧 secret 没有被复制到恢复环境。

## 生产要求

生产至少需要：

- 托管 PostgreSQL 多可用区或同等故障域隔离；
- 自动快照与连续 WAL/PITR；
- 备份加密、不可变保留和独立账号；
- 定期恢复到隔离账户/区域；
- schema/version-aware 验证；
- 恢复期间的写入冻结、流量切换和回退方案；
- 审计记录与双人审批。

当前 Compose 不实现这些生产控制，不能因为本地 `pg_dump` 成功而宣称达到生产灾备标准。
