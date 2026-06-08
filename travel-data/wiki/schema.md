---
title: "schema"
type: "system"
source_ids: []
entity_ids: []
updated_at: "2026-06-05T06:52:36.200Z"
confidence: "high"
---

# schema

## Page Types
- `poi`：单个 POI 页面，必须包含预算、停留、开放时间、UGC 信号和通勤可达性。
- `area`：区域/商圈画像页面，必须链接区域内代表 POI。
- `topic`：偏好主题页面，例如少排队、老人友好、亲子友好、室内优先。
- `system`：purpose、schema、log、index。

## Frontmatter
每个页面必须包含：
- `title`
- `type`
- `source_ids`
- `entity_ids`
- `updated_at`
- `confidence`

## Link Rule
页面之间使用 Obsidian 兼容的 `[[wikilink]]`。POI 必须链接区域页；区域和主题页必须链接代表 POI。
