---
name: quant-announcement-events
description: Use this skill to fetch A-share announcement/event data for explaining stock moves, corporate actions, earnings notices, and risk events.
---

# QuantPilot 公告事件能力

获取上市公司公告列表，用于事件驱动分析和行情归因。

## API

```bash
curl 'http://127.0.0.1:8000/api/v1/events/announcements/600519?limit=20'
```

返回重点字段：

- `title`
- `notice_date`
- `display_time`
- `columns`
- `url`
- `pdf_url`
- `source`

## 工作流程

1. 必要时先用 `quant-symbol-resolver`。
2. 获取最近公告，筛选业绩、分红、回购、减持、诉讼、并购、停复牌等事件。
3. 分析公告和价格/成交额变化之间的可能关系。
4. 如果需要更深入内容，再基于 `url` 或 `pdf_url` 读取公告详情。
5. 可视化时用事件时间线、事件标签和影响摘要。

## 禁止事项

- 不要只凭标题下结论，要说明不确定性。
- 不要把公告事件和价格因果关系说死。
