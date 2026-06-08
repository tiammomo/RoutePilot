# 本地产物边界

以下内容通常是本地生成或本地私有配置，不应提交：

- `.env`
- `.env.local`
- `.next/`
- `node_modules/`
- `data/projects/`
- `tmp/`
- `public/uploads/`
- `public/generated/`

以下内容属于项目数据资产，可以提交或按需版本管理：

- `travel-data/processed/`
- `travel-data/wiki/`
- `sqls/008-travel-commute-data.sql`
- `sqls/009-travel-knowledge-base.sql`
- `scripts/travel/`
- `scripts/checks/check-travel-*.js`

通勤采集导出默认在 `tmp/exports/` 下，例如：

```text
tmp/exports/travel_commute_edges_completed_9000.csv
```
