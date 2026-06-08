---
name: travel-visualization-html
description: Use this skill to build Beijing itinerary dashboards from Travel API responses and data_file/final/itinerary-data.json.
---

# Travel Visualization HTML

生成的 `app/page.tsx` 必须是可用路线看板，不是营销页或纯文本说明。

必备组件：
- 三方案对比
- 时间轴
- POI 决策卡
- 预算、总时长、步行/转移估算
- UGC 证据
- 风险提示
- 动态重规划入口

最终数据优先写入 `data_file/final/itinerary-data.json`，并显示静态数据边界：不接入实时排队、实时地图或实时营业变更。
