# 基础设施配置

QuantPilot 本地开发默认使用 PostgreSQL + TimescaleDB。PostgreSQL 承载工作空间、项目、评测、配置和运行记录；TimescaleDB 承载股票 K 线、因子、策略信号和组合净值等时序数据。

## 本地启动

```bash
npm run db:up
npm run db:init
npm run db:sync-workspaces
npm run db:migrate-platform-state
npm run dev
```

默认连接信息：

```env
DATABASE_URL="postgresql://quantpilot:quantpilot_dev_password@127.0.0.1:5432/quantpilot?schema=public"
TIMESCALEDB_IMAGE="timescale/timescaledb:2.27.1-pg18"
POSTGRES_DB="quantpilot"
POSTGRES_USER="quantpilot"
POSTGRES_PASSWORD="quantpilot_dev_password"
POSTGRES_PORT=5432
```

## 组件分工

| 组件 | 用途 |
| --- | --- |
| PostgreSQL | 主业务库，承载 Prisma 管理的应用表 |
| TimescaleDB | 股票时序数据、因子、信号、组合快照 |
| Redis | 后续用于缓存、任务队列和短期状态 |
| 对象存储 | 后续用于原始行情文件、回测产物和大报告 |
| ClickHouse | 后续用于超大量 tick、盘口快照和研究分析面板 |

## 回填本地工作空间索引

如果 PostgreSQL 中的首页项目列表为空，但 `data/projects/project-*` 目录仍在，可以回填项目索引：

```bash
npm run db:sync-workspaces
```

该命令只会为 PostgreSQL 中缺失的 workspace 创建项目记录，不会修改工作空间源码。

平台级状态迁移：

```bash
npm run db:migrate-platform-state
```

当前会迁移 `data/global-settings.json`、`data/strategy-scans/jobs/*.json`、`data/strategy-scans/runs/*.json`、评测报告索引、评测队列、评测修复单和评测定时配置到 PostgreSQL。workspace 源码、证据文件、验证报告原件、评测日志和图表数据仍保留在文件系统，后续按“索引进库、文件留原地”的方式继续收敛。

## 时序表

根目录 `sqls/` 记录组件默认需要的基础 SQL。Docker 首次创建数据库时会自动执行 `sqls/*.sql`，已有数据库可重复运行：

```bash
npm run db:init
```

`db:init` 会先执行 `sqls/*.sql`，再运行 `prisma db push` 同步 Prisma 管理的应用表。

当前 `sqls/001-quant-timeseries.sql` 会创建：

- `quant.stock_bars`
- `quant.stock_bars` 内的高价值 K 线字段包括 `amount`、`amplitude`、`change_percent`、`change_amount` 和 `turnover`，字段来源与补数策略见 `docs/market-data-source-knowledge.md`。
- `quant.stock_factors`
- `quant.strategy_signals`
- `quant.portfolio_snapshots`

这些表使用 TimescaleDB hypertable，以时间字段 `ts` 做分区。Prisma 继续管理主业务表，量化时序数据可通过 SQL、后端服务或后续专门的数据访问层写入。

## 推荐组件路线

当前不建议一次性引入过多组件。优先级如下：

| 组件 | 建议阶段 | 作用 |
| --- | --- | --- |
| Redis | 下一阶段 | 任务队列、短期缓存、分布式锁和进度状态 |
| 对象存储 | 产物规模上来后 | 截图、回测报告、原始行情文件和大 JSON |
| ClickHouse | 数据规模明显放大后 | 超大量 tick、盘口快照和交互式研究分析 |

短期继续以 PostgreSQL + TimescaleDB 作为核心数据底座即可。Redis 是最值得优先补的组件，因为它能把评测队列、策略扫描队列和生成任务队列从进程内状态中解耦出来。
