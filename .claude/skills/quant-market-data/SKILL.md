---
name: quant-market-data
description: Use this skill when the task needs to fetch stock prices or A-share market data before analysis or visualization.
---

# QuantPilot 行情取数能力

使用 QuantPilot 本地 Python 市场数据后端获取东方财富 A 股实时行情。这个 skill 只负责取数，不负责设计页面。

## 何时必须使用

当任务涉及以下任意内容时，必须使用这个能力：

- 股票实时价格。
- A 股行情数据。
- 个股、组合、指数等市场数据查询。
- 指数或 ETF 查询优先配合 `quant-index-etf-market`，避免误走个股财务/公告链路。
- 需要先获取数据再做可视化、HTML 看板或分析的任务。

本 skill 只负责“取数和数据理解”。可视化页面生成必须交给 `quant-visualization-html` skill。

## 本地后端

服务地址：

```text
http://127.0.0.1:8000
```

健康检查：

```bash
curl http://127.0.0.1:8000/health
```

单只股票实时行情：

```bash
curl 'http://127.0.0.1:8000/api/v1/quotes/realtime/600519'
curl 'http://127.0.0.1:8000/api/v1/quotes/realtime/000300'
curl 'http://127.0.0.1:8000/api/v1/quotes/realtime/510300'
```

候选免费/免费层信源：

```bash
curl 'http://127.0.0.1:8000/api/v1/provider-candidates'
curl 'http://127.0.0.1:8000/api/v1/provider-candidates/probe?provider_id=stooq-daily'
curl 'http://127.0.0.1:8000/api/v1/provider-candidates/probe?provider_id=yahoo-finance-chart'
```

这些候选源只用于能力评估和后端 provider 规划，不直接替换东方财富主链路。海外股票、ETF、指数等任务后续优先通过 QuantPilot 后端封装 Stooq/Yahoo/yfinance，不要在生成项目中临时安装或直接调用外网接口。

批量实时行情：

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/quotes/realtime' \
  -H 'Content-Type: application/json' \
  -d '{"symbols":["600519","000001","300750"]}'
```

## 返回字段

典型返回：

```json
{
  "symbol": "600519",
  "secid": "1.600519",
  "name": "贵州茅台",
  "market": "SH",
  "asset_type": "stock",
  "source": "eastmoney",
  "price": "1290.2",
  "open": "1310.95",
  "high": "1311.91",
  "low": "1290.12",
  "previous_close": "1311.0",
  "change_percent": "-1.59",
  "volume": 49157,
  "amount": "6372389482.0",
  "market_cap": "1615679031393",
  "float_market_cap": "1615679031393",
  "quote_time": "2026-05-22T08:11:47Z",
  "fetched_at": "2026-05-22T17:37:53.137699Z",
  "fetch": {
    "cache_status": "miss",
    "cache_ttl_seconds": 5
  }
}
```

## 工作流程

1. 从用户问题中识别股票代码、股票名称或默认标的。
2. 如果用户没有指定股票，默认使用 `600519`、`000001`、`300750`。
3. 使用 `curl` 或页面 API 调用本地行情后端获取数据。
4. 如果接口失败，先展示真实错误，不要编造数据。
5. 明确记录返回数据中的 `symbol`、`name`、`asset_type`、`price`、`change_percent`、`amount`、`market_cap`、`quote_time`、`fetched_at` 和 `fetch.cache_status`。
6. 如果后续需要页面或看板，必须把已获取的数据作为输入交给 `quant-visualization-html` skill。
7. 如果用户请求海外股票或 ETF，先查询 `/api/v1/provider-candidates` 说明当前可测试的免费源；如果后端主接口尚未支持该市场，要把能力边界写进数据质量，不要编造行情。

## 禁止事项

- 不要硬编码行情数据来假装已取数。
- 不要绕过 QuantPilot 市场数据后端直接在生成项目里抓东方财富。
- 不要在生成项目中 `pip install yfinance` 或用 Bash 临时写爬虫；海外数据源必须先进入 QuantPilot 后端 provider。
- 不要在取数 skill 中设计页面结构；页面结构交给可视化 skill。

## 后端启动

如果服务未启动，在 QuantPilot 根目录执行：

```bash
cd backend/market_data
uv sync
uv run quantpilot-market-api
```

不要在生成的 Next.js 项目中重新实现行情抓取逻辑；统一调用 QuantPilot 市场数据后端。
