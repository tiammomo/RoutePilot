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
- `correlation`
- `liquidity`
- `trendTemplate`
- 可视化所需的序列数据

## 标准流程

1. 确认 K 线样本长度、周期和复权方式。
2. 计算或读取 MA、区间收益、最大回撤、年化波动率、成交量均值等指标。
3. 多标的任务需要统一时间窗口和缺失值处理规则。
4. 如果是多标的、组合、对比或风控问题，必须计算相关性矩阵和流动性摘要。
5. 如果用户询问走势、调仓、持有/减仓或趋势确认，运行趋势模板脚本生成 `trendTemplate`。
6. 将指标写入 `data_file/final/dashboard-data.json`。
7. 使用 `quant-data-quality` 记录样本长度、缺失字段和计算限制。

## Python 脚本原则

指标计算优先使用后端接口或确定性脚本，不依赖模型口算。脚本应输出 JSON，不直接生成页面。

可用脚本：

- `scripts/correlation.py`：读取 `data_file/final/dashboard-data.json`，基于多标的收盘价对齐日期，输出 `pearson_log_return` 相关性矩阵和 Top pairs。
- `scripts/liquidity.py`：读取 `data_file/final/dashboard-data.json`，输出 20 日平均成交额、成交量、换手代理、Amihud 非流动性和流动性等级。
- `scripts/trend_template.py`：读取 `data_file/final/dashboard-data.json`，输出 MA20/MA60、20 日收益、120 日回撤、量能比和确认/减仓/观察触发条件。

推荐调用：

```bash
python3 .claude/skills/quant-indicators/scripts/correlation.py data_file/final/dashboard-data.json -o data_file/final/correlation.json
python3 .claude/skills/quant-indicators/scripts/liquidity.py data_file/final/dashboard-data.json -o data_file/final/liquidity.json
python3 .claude/skills/quant-indicators/scripts/trend_template.py data_file/final/dashboard-data.json -o data_file/final/trend-template.json
```

然后把结果合并回：

- `dashboard-data.json.correlation`
- `dashboard-data.json.liquidity`
- `dashboard-data.json.trendTemplate`

单标的任务也可以运行 `liquidity.py`；相关性脚本在不足两个标的时会返回 warning。

## 禁止事项

- 不要在样本不足时给出确定性趋势判断。
- 不要混用不同周期或不同复权口径的数据。
- 不要省略指标窗口、样本长度和计算限制。
