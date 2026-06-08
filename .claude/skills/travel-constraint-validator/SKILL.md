---
name: travel-constraint-validator
description: Use this skill to validate Beijing route proposals against POI count, category coverage, budget, duration, opening-hours, UGC evidence, and response-time requirements.
---

# Travel Constraint Validator

验证每条路线：
- 至少 3 个 POI
- 混合路线至少 1 个餐饮 + 2 个文化/娱乐
- 预算不超限，或明确显示超预算风险
- 总时长不超限，或明确显示超时风险
- 营业时间未知或冲突必须提示
- 餐饮 POI 展示 UGC 排队/性价比证据
- 生成耗时目标小于 10 秒

验证结果写入 `.travelpilot/validation.json` 或页面风险区。
