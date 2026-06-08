# 北京旅游 Agent

北京旅游 Agent 是一个面向北京本地游玩的智能路线规划工作台。系统基于本地 POI、餐厅、文化地点、UGC 评论特征和高德通勤补全数据，生成可解释、可调整的旅游路线。

项目已经清理掉历史量化平台包袱，不再包含股票策略平台、金融数据服务、时序数据库量化 SQL 或旧评测平台。

## 核心能力

- 自然语言解析：把用户的区域、时长、预算、餐饮和偏好约束转成结构化规划条件。
- 数据库路线命中：优先从 PostgreSQL 的 `travel_precomputed_routes` 查询预生成路线，命中后直接返回前端渲染。
- 本地数据检索：将 `travel-data/processed` 中的北京 POI、餐厅、文化地点、UGC 特征和预生成路线导入数据库。
- 通勤补全：使用 `travel_commute_edges` 表中的景点-景点、景点-餐厅、餐厅-餐厅通勤边。
- 路线规划：大模型只负责语义理解，后端根据结构化条件查询数据库路线库；未命中时使用本地数据规则兜底。
- 动态重规划：支持继续追加、删除、替换或保留地点。
- 数据平台：`/data-platform` 查看旅游能力、数据源和接口健康状态。

## 数据位置

- 原始/处理后的 POI 数据：`travel-data/processed`
- 预生成路线库文件：`travel-data/processed/beijing_route_corpus.json`
- Wiki 知识库：`travel-data/wiki`
- 通勤补全 SQL：`sqls/008-travel-commute-data.sql`
- 旅游知识库 SQL：`sqls/009-travel-knowledge-base.sql`
- 预生成路线库 SQL：`sqls/010-travel-route-corpus.sql`
- 通勤采集 CSV 导出：`tmp/exports/travel_commute_edges_completed_9000.csv`
- 主要数据库表：`travel_pois`、`travel_poi_features`、`travel_reviews`、`travel_areas`、`travel_commute_edges`、`travel_precomputed_routes`

## 快速启动

推荐使用 Docker PostgreSQL 保存旅游数据和预生成路线：

```bash
npm install
cp .env.example .env
npm run db:up
npm run travel:db:seed
npm run travel:db:doctor
npm run dev
```

默认访问：

```text
http://localhost:3000
```

如果你已经在本机用旧数据库名保存了采集结果，可以继续在 `.env` 中保留原来的 `DATABASE_URL`，不需要为了改名重新采集。

## Docker 数据库导入

`docker-compose.yml` 会启动一个 PostgreSQL 16 容器，默认配置来自 `.env`：

```env
DATABASE_URL="postgresql://travelpilot:<replace-with-local-password>@127.0.0.1:5432/travelpilot?schema=public"
POSTGRES_DB="travelpilot"
POSTGRES_USER="travelpilot"
POSTGRES_PASSWORD="<replace-with-local-password>"
POSTGRES_PORT=5432
```

完整导入流程：

```bash
# 1. 启动 PostgreSQL 容器
npm run db:up

# 2. 建旅游数据表，包括 POI、UGC、通勤边、语义日志、预生成路线库
npm run travel:db:init

# 3. 从 travel-data/processed 生成预计算路线库 JSON
npm run travel:routes:build

# 4. 将 POI、UGC、评论、区域和预生成路线导入 PostgreSQL
npm run travel:db:import

# 5. 检查表和数据量
npm run travel:db:doctor
```

也可以直接使用合并命令：

```bash
npm run travel:db:seed
```

导入完成后，关键数据会保存在 Docker PostgreSQL 的这些表中：

| 表 | 内容 |
| --- | --- |
| `travel_pois` | 北京 POI、餐厅、文化地点、基础评分、营业时间和标签 |
| `travel_poi_features` | UGC 聚合特征，例如排队风险、性价比、亲子友好度 |
| `travel_reviews` | 本地评论/证据文本 |
| `travel_areas` | 区域汇总 |
| `travel_commute_edges` | 景点和餐饮点之间的通勤边 |
| `travel_precomputed_routes` | 预生成旅行路线，运行时优先命中后直接返回前端 |

可以用下面的命令确认路线库已经入库：

```bash
docker compose exec postgres psql -U travelpilot -d travelpilot \
  -c "SELECT COUNT(*) FROM travel_precomputed_routes;"
```

当前路线链路是：

```text
用户自然语言
  -> MiniMax-M2.7 解析结构化 intent
  -> 后端将 intent 转成受控 SQL 查询
  -> 优先命中 travel_precomputed_routes
  -> 直接返回 planning_response.proposals 给前端渲染
```

大模型不直接生成 SQL 字符串，也不负责实时生成完整路线；SQL 查询由后端模板和参数控制。

## 常用命令

```bash
npm run dev
npm run build
npm run lint
npm run type-check

npm run db:up
npm run db:down
npm run db:init
npm run db:doctor
npm run db:psql

npm run travel:db:init
npm run travel:routes:build
npm run travel:db:seed
npm run travel:db:import
npm run travel:db:doctor
npm run travel:wiki:build
npm run travel:amap:backfill

npm run check:travel
npm run check:travel-commute
npm run check:travel-query-plan
```

## 旅游 API

- `GET /api/v1/travel/health`
- `GET /api/v1/travel/options`
- `GET /api/v1/travel/pois`
- `POST /api/v1/travel/parse-and-plan`
- `POST /api/v1/travel/plan`
- `POST /api/v1/travel/replan`
- `POST /api/v1/travel/query-plan`
- `GET /api/v1/travel/evidence/{poi_id}`

## 项目结构

| 路径 | 说明 |
| --- | --- |
| `src/app/` | Next.js 页面和 API |
| `src/app/api/v1/travel/` | 旅游规划 API |
| `src/lib/travel/` | 语义解析、SQL 查询、路线规划、Wiki 检索和重排 |
| `scripts/travel/` | 旅游数据库初始化、导入、诊断、Wiki 构建和高德通勤补全 |
| `scripts/checks/` | 旅游链路检查脚本 |
| `sqls/` | 旅游数据库 SQL |
| `travel-data/` | 本地旅游数据和 Wiki |
| `data/projects/` | 本地生成的任务工作空间，默认不提交 |
| `tmp/` | 本地导出、采集和检查产物，默认不提交 |

## 注意事项

- 通勤时间、排队风险和性价比是本地静态或历史数据估算，不代表实时导航、实时排队或实时营业状态。
- 真实 key 请放在 `.env` 或 `.env.local`，不要提交到 Git。
- 高德 API 调用建议控制频率，默认脚本支持通过参数调整延迟。
