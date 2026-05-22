# QuantPilot 市场数据服务

这个子模块用于给量化分析 Agent 提供基础行情能力。当前先实现东方财富实时股价查询，后续可以继续扩展历史行情、财务数据、盘口、资金流等数据源。

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
http://127.0.0.1:8010
```

可选环境变量：

```bash
# 服务监听地址
export QUANTPILOT_MARKET_HOST=127.0.0.1
export QUANTPILOT_MARKET_PORT=8010

# 东方财富主备域名，按顺序失败重试
export EASTMONEY_BASE_URLS=https://push2.eastmoney.com,https://push2delay.eastmoney.com
```

## 接口

### 健康检查

```bash
curl http://127.0.0.1:8010/health
```

### 单只股票实时行情

```bash
curl 'http://127.0.0.1:8010/api/v1/quotes/realtime/600519'
curl 'http://127.0.0.1:8010/api/v1/quotes/realtime/000001'
curl 'http://127.0.0.1:8010/api/v1/quotes/realtime/1.600519'
```

### 批量股票实时行情

```bash
curl -X POST 'http://127.0.0.1:8010/api/v1/quotes/realtime' \
  -H 'Content-Type: application/json' \
  -d '{"symbols":["600519","000001","300750"]}'
```

## 代码结构

- `quantpilot_market_data/providers/eastmoney.py`：东方财富数据源客户端。
- `quantpilot_market_data/models.py`：行情数据模型。
- `quantpilot_market_data/api.py`：FastAPI HTTP 服务。
- `quantpilot_market_data/cli.py`：启动入口。

## 说明

东方财富接口不是正式稳定的商业 SDK，这里先按常见的 `push2.eastmoney.com/api/qt/ulist.np/get` 行情接口封装，并内置 `push2delay.eastmoney.com` 作为备用域名。生产环境需要增加缓存、限流、降级数据源和接口变更监控。
