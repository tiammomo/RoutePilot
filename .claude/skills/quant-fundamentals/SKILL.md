---
name: quant-fundamentals
description: Use this skill for financial statements, derived fundamental indicators, announcements, and event context. It is the long-term aggregate replacement for quant-fundamental-financials, quant-fundamental-indicators, and quant-announcement-events.
---

# QuantPilot 基本面与事件能力

本 skill 负责上市公司基本面数据和事件上下文，长期承接以下兼容能力：

- `quant-fundamental-financials`
- `quant-fundamental-indicators`
- `quant-announcement-events`

## 能力边界

输入：

- `run_plan.symbols`
- 用户关注的报告期、财务指标或公告事件
- 后端数据接口返回的财务、指标和公告数据

输出：

- `financials`
- `fundamentalIndicators`
- `announcements`
- `valuation`
- `evidence/sources.json`
- `evidence/data_quality.json`

## 标准流程

1. 使用 `quant-symbol-resolver` 确认标的。
2. 调用：
   - `/api/v1/fundamentals/financials/{symbol}`
   - `/api/v1/indicators/fundamental/{symbol}`
   - `/api/v1/events/announcements/{symbol}`
3. 如果用户询问估值、贵不贵、调仓、持有/减仓依据，运行估值情景脚本生成 `valuation`。
4. 使用 `quant-data-quality` 记录来源、报告期、缺失字段和限制。
5. 将结果写入 `data_file/final/dashboard-data.json` 的标准字段。
6. 交给 `quant-visualization-html` 生成基本面或综合看板。

## Python 脚本原则

财务口径和估值情景优先用确定性脚本，不让模型口算倍数或上行空间。脚本只输出结构化 JSON，不直接生成页面。

可用脚本：

- `scripts/valuation_scenarios.py`：读取 `data_file/final/dashboard-data.json`，基于最新价、EPS、PE、市值、净利润等可用字段生成防守/中性/进攻三档估值情景。

推荐调用：

```bash
python3 .claude/skills/quant-fundamentals/scripts/valuation_scenarios.py data_file/final/dashboard-data.json -o data_file/final/valuation.json
```

然后把结果合并回：

- `dashboard-data.json.valuation`

如果 EPS、PE 或最新价缺失，脚本必须保留 warning；页面展示 warning，不要编造估值结果。

## 禁止事项

- 不要把缺失财务字段编造成真实值。
- 不要把公告标题推断成确定性利好或利空。
- 不要省略报告期、来源和缺失字段说明。
- 不要把估值情景当成收益承诺或直接交易指令。
