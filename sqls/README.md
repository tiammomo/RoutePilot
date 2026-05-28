# QuantPilot SQL Bootstrap

`sqls/` 保存 QuantPilot 组件第一次使用时需要的基础数据库对象。所有 SQL 都应保持可重复执行，方便 Docker 首次建库、已有本地库补齐和后续部署检查。

## 执行顺序

| 文件 | 组件 | 说明 |
| --- | --- | --- |
| `001-quant-timeseries.sql` | TimescaleDB / quant schema | 创建 TimescaleDB 扩展、`quant` schema、股票 K 线、因子、策略信号和组合快照 hypertable |
| `002-quant-research-platform.sql` | 策略研究 / 入库 / 回测 | 补齐证券主数据、股票池、入库任务、同步水位、回测任务和示例 A 股研究池 |

主业务表由 Prisma 维护，不在这里手写：

| 组件 | 表 |
| --- | --- |
| 项目与对话 | `projects`、`messages`、`sessions`、`tool_usages`、`user_requests` |
| 环境与集成 | `env_vars`、`service_tokens`、`project_service_connections`、`commits` |
| 平台配置 | `platform_settings` |
| 策略平台 | `strategy_scan_runs`、`strategy_scan_jobs` |
| 评测平台 | `eval_runs`、`eval_queue_items`、`eval_repair_tickets`、`eval_schedules` |

## 本地初始化

首次使用推荐：

```bash
npm run db:up
npm run db:init
npm run db:doctor
```

`npm run db:init` 会按顺序执行 `sqls/*.sql`，然后运行 `prisma db push` 同步 Prisma 管理的应用表。已有数据库也可以重复执行该命令。

## 规则

- SQL 必须使用 `IF NOT EXISTS` 或等价方式，避免重复执行失败。
- 时序、大批量行情和策略信号表放在 `quant` schema。
- `stock_bars` 的唯一口径包含 `symbol + timeframe + adjustment + ts`，避免前复权、后复权和不复权数据互相覆盖。
- 平台主业务表继续先改 `prisma/schema.prisma`，再通过 Prisma 生成数据库结构。
- 后续若引入 Redis、对象存储或 ClickHouse，只把 PostgreSQL/TimescaleDB 相关 SQL 放在这里。
