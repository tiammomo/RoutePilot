# QuantPilot 市场数据服务

这个子模块用于给量化分析 Agent 提供基础行情、财务和事件数据能力。当前以东方财富为主数据源，已接入实时行情、证券解析、财务摘要和公告事件；历史 K 线接口已预留，但外部源偶发断连，后续会继续接入 AKShare/Tushare 作为降级源。

## 环境要求

- Python 3.14
- uv

首次初始化：

```bash
cd backend/market_data
uv sync
```

启动服务：

```bash
uv run quantpilot-market-api
```

默认地址：

```text
http://127.0.0.1:8000
```

可选环境变量：

```bash
# 服务监听地址
export QUANTPILOT_MARKET_HOST=127.0.0.1
export QUANTPILOT_MARKET_PORT=8000

# 东方财富主备域名，按顺序失败重试
export EASTMONEY_BASE_URLS=https://push2.eastmoney.com,https://push2delay.eastmoney.com
```

## 接口

### 健康检查

```bash
curl http://127.0.0.1:8000/health
```

### 数据源注册表

```bash
curl http://127.0.0.1:8000/api/v1/registry
```

### 证券代码/名称解析

```bash
curl -G 'http://127.0.0.1:8000/api/v1/symbols/resolve' \
  --data-urlencode 'query=茅台' \
  --data-urlencode 'count=5'
```

### 单只股票实时行情

```bash
curl 'http://127.0.0.1:8000/api/v1/quotes/realtime/600519'
curl 'http://127.0.0.1:8000/api/v1/quotes/realtime/000001'
curl 'http://127.0.0.1:8000/api/v1/quotes/realtime/1.600519'
```

### 批量股票实时行情

```bash
curl -X POST 'http://127.0.0.1:8000/api/v1/quotes/realtime' \
  -H 'Content-Type: application/json' \
  -d '{"symbols":["600519","000001","300750"]}'
```

### 历史 K 线

```bash
curl 'http://127.0.0.1:8000/api/v1/quotes/history/600519?period=daily&adjustment=qfq&limit=120'
```

说明：当前东方财富历史 K 线外部源偶发断连，注册表会将能力标记为 `degraded`。调用失败时应展示真实错误，并降级到实时行情、财务摘要和公告事件。

### 财务摘要

```bash
curl 'http://127.0.0.1:8000/api/v1/fundamentals/financials/600519?limit=8'
```

### 公告事件

```bash
curl 'http://127.0.0.1:8000/api/v1/events/announcements/600519?limit=20'
```

## 代码结构

- `quantpilot_market_data/providers/eastmoney.py`：东方财富数据源客户端。
- `quantpilot_market_data/models.py`：行情数据模型。
- `quantpilot_market_data/api.py`：FastAPI HTTP 服务。
- `quantpilot_market_data/cli.py`：启动入口。

## 说明

东方财富接口不是正式稳定的商业 SDK，这里先按常见的 `push2.eastmoney.com/api/qt/ulist.np/get` 行情接口封装，并内置 `push2delay.eastmoney.com` 作为备用域名。生产环境需要增加缓存、限流、降级数据源和接口变更监控。
