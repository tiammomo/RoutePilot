---
name: travel-ugc-evidence
description: Use this skill to explain Beijing POI recommendations with local UGC feature aggregates such as queue risk, value for money, family friendliness, and environment quality.
---

# Travel UGC Evidence

使用 `/api/v1/travel/evidence/{poi_id}` 查询 POI 的评论特征证据。UGC 只能作为历史评论语义信号，不得包装成实时排队或实时服务状态。

核心信号：
- `queue_risk`
- `value_for_money`
- `family_friendliness`
- `environment_quality`

如果证据缺失，必须显示“本地数据暂无该 POI 的评论证据”。
