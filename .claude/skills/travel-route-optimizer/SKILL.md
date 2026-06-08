---
name: travel-route-optimizer
description: Use this skill to generate or adjust Beijing travel routes with time, budget, walking, category coverage, and POI ordering constraints.
---

# Travel Route Optimizer

通过 Travel API 生成路线：
- 首轮自然语言：`POST /api/v1/travel/parse-and-plan`
- 结构化请求：`POST /api/v1/travel/plan`
- 追问调整：`POST /api/v1/travel/replan`

路线输出至少展示三套方案：均衡体验、预算优先、效率优先。混合路线至少 1 个餐饮 POI + 2 个文化/娱乐 POI；文化路线至少 3 个文化/娱乐 POI。
