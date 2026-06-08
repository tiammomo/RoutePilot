---
name: travel-poi-retrieval
description: Use this skill to retrieve Beijing POIs from local travel-data/processed datasets through the Travel API.
---

# Travel POI Retrieval

从本地北京 POI 数据集中召回文化、餐饮和娱乐点位。不得凭空编造 POI；输出 POI 必须来自 `/api/v1/travel/pois`、`/api/v1/travel/options` 或路线规划响应。

关键字段：
- `poi_id`
- `name`
- `area`
- `category`
- `poi_type`
- `rating`
- `avg_cost`
- `suggested_duration_min`
- `open_time` / `close_time`

距离和转移时间只能标注为本地估算。
