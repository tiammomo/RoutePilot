---
title: "西城3927号LiveHouse"
type: "poi"
source_ids: ["beijing_planner_entities"]
entity_ids: ["fixture_entertainment_西城区_26_livehouse"]
area: "西城区"
updated_at: "2026-06-05T06:52:36.200Z"
confidence: "low"
tags: ["西城区", "entertainment", "livehouse", "walk:low", "queue:low", "family:low", "area:西城区", "category:entertainment", "district:西城区", "leisure", "need:short_stop", "poi_type:entertainment"]
---

# 西城3927号LiveHouse

> Obsidian Wiki 页面。来源：`travel-data/raw/sources/beijing_planner_entities.json`，UGC 聚合：`beijing_poi_feature_aggregates.json`，评论：`beijing_review_records.json`。

## 导航
- 所属区域：[[区域 - 西城区]]
- 类型：entertainment / livehouse
- 相关主题：[[主题 - 室内优先]]、[[主题 - 少排队]]

## POI 摘要
| 字段 | 值 |
| --- | --- |
| 区域 | 西城区 |
| 地址 | 北京市西城区西城区商圈共享示例 27 号 |
| 预算 | 214 元 |
| 建议停留 | 90 分钟 |
| 营业时间 | 17:00 - 23:30 |
| 评分 | 4.4 |
| 步行强度 | low |
| 排队风险 | low |
| 亲子友好 | low |
| 老人友好 | unknown |

## UGC 聚合信号
| feature | value | confidence | reviews |
| --- | --- | --- | --- |
| queue_risk | low | high | 4 |
| value_for_money | unavailable | low | 0 |
| family_friendliness | low | low | 1 |
| environment_quality | low | low | 2 |

## 评论证据
- [fixture_review_c0831fdfe42e] 带娃会有点累，更偏年轻一点的路线，在西城区这一带临时找吃的，桌子排得比较密，工作日下午过去几乎不用等，性价比比预期高。（评分 3.9，fixture_reviews）
- [fixture_review_1d298061ef85] 演出前后来这里很顺，看完周边点位顺路进来，高峰时稍显拥挤，工作日下午过去几乎不用等，分量挺足。（评分 3.9，fixture_reviews）
- [fixture_review_e933ef1b0743] 工作日下午过去几乎不用等，台阶多，性价比比预期高，演出前后来这里很顺。（评分 4，fixture_reviews）
- [fixture_review_0ad5116252bf] 不太适合带孩子，在西城区这一带临时找吃的，高峰时稍显拥挤，夜里氛围感更强，出餐快。（评分 4.1，fixture_reviews）

## 通勤可达性
- 暂无 travel_commute_edges 覆盖，路线规划会回退坐标估算。

## 可用于路线规划的判断
- 如果用户要求少走路，优先检查 `walk_intensity` 与通勤覆盖。
- 如果用户要求不排队，优先检查 `queue_risk` 和评论证据。
- 如果用户是老人/亲子/情侣，结合本页 tags 与区域页进行候选筛选。
