---
name: quant-indicators
description: Use this skill for deterministic technical, return, volatility, drawdown, volume, and risk metric computation. It is the long-term aggregate replacement for quant-technical-indicators.
---

# QuantPilot 指标计算能力

本 skill 负责把已获取的行情/K 线数据转换为稳定可复用的指标结果，长期承接：

- `quant-technical-indicators`

## 能力边界

输入：

- `kline.bars`
- `assets[]`
- 用户指定的时间范围、指标窗口或风险口径

输出：

- `technicalIndicators`
- `computedMetrics`
- `riskMetrics`
- 可视化所需的序列数据

## 标准流程

1. 确认 K 线样本长度、周期和复权方式。
2. 计算或读取 MA、区间收益、最大回撤、年化波动率、成交量均值等指标。
3. 多标的任务需要统一时间窗口和缺失值处理规则。
4. 将指标写入 `data_file/final/dashboard-data.json`。
5. 使用 `quant-data-quality` 记录样本长度、缺失字段和计算限制。

## Python 脚本原则

指标计算优先使用后端接口或确定性脚本，不依赖模型口算。脚本应输出 JSON，不直接生成页面。

## 禁止事项

- 不要在样本不足时给出确定性趋势判断。
- 不要混用不同周期或不同复权口径的数据。
- 不要省略指标窗口、样本长度和计算限制。
