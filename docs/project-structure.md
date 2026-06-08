# 项目结构

北京旅游 Agent 是一个 Next.js + PostgreSQL 的本地旅游规划应用。

| 路径 | 说明 |
| --- | --- |
| `src/app/` | App Router 页面与 API |
| `src/app/api/v1/travel/` | 旅游规划、重规划、POI、证据和健康检查 API |
| `src/lib/travel/` | 语义意图、SQL 查询、路线规划、Wiki 检索和 LLM 重排 |
| `scripts/travel/` | 旅游数据导入、诊断、Wiki 构建和高德通勤补全 |
| `scripts/checks/` | 旅游链路 smoke/回归检查 |
| `sqls/` | 旅游数据库 schema |
| `travel-data/` | 本地旅游数据、原始数据和 Wiki |
| `data/projects/` | 用户创建的本地任务工作空间 |
| `tmp/` | 导出文件、采集进度和临时报告 |

## 已清理内容

旧量化平台、股票/ETF/策略平台、金融数据 FastAPI 服务、时序数据库量化 SQL、旧 eval/ops/skills 控制台均已从项目结构中移除。
