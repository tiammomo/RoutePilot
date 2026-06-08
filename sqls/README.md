# 北京旅游 Agent SQL

`sqls/` 只保存旅游 Agent 需要的 PostgreSQL schema，所有 SQL 都应保持可重复执行。

| 文件 | 说明 |
| --- | --- |
| `008-travel-commute-data.sql` | 通勤边表，保存景点-景点、景点-餐厅、餐厅-餐厅的步行/驾车/公交结果 |
| `009-travel-knowledge-base.sql` | 旅游 Wiki 文档、分块与检索所需表 |
| `010-travel-route-corpus.sql` | 预生成路线库表，运行时优先按用户语义条件命中路线并直接返回前端 |

初始化：

```bash
npm run travel:db:init
```

旅游数据导入到 Docker PostgreSQL：

```bash
npm run db:up
npm run travel:routes:build
npm run travel:db:import
npm run travel:db:doctor
```

一条命令完成建表、生成路线库、导入数据：

```bash
npm run travel:db:seed
```

导入后可检查路线库：

```bash
docker compose exec postgres psql -U travelpilot -d travelpilot \
  -c "SELECT COUNT(*) FROM travel_precomputed_routes;"
```
