---
name: travel-run-planner
description: Use this skill at the beginning of every 北京旅游 Agent task to create or update .travelpilot/run_plan.json before fetching POI/UGC data or generating itinerary dashboards.
---

# Travel Run Planner

把用户自然语言目标转换为北京路线规划计划。计划必须记录城市、区域、路线模式、时间、预算、POI 数量、步行偏好、少排队/亲子/性价比等约束。

默认产物：
- `.travelpilot/run_plan.json`
- `.travelpilot/events.jsonl`

必须优先使用本地 Travel API：
- `GET /api/v1/travel/options`
- `POST /api/v1/travel/parse-and-plan`
- `POST /api/v1/travel/plan`
- `POST /api/v1/travel/replan`

如果区域、时间或预算缺失但仍可合理默认，可以继续规划并标注假设；只有完全无法判断游玩目标时才澄清。
