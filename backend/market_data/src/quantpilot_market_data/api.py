from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from quantpilot_market_data.models import (
    Adjustment,
    AnnouncementResponse,
    BatchQuoteRequest,
    BatchQuoteResponse,
    DataProviderInfo,
    DataRegistryResponse,
    FinancialReportsResponse,
    KlinePeriod,
    KlineResponse,
    RealtimeQuote,
    SymbolResolveResponse,
)
from quantpilot_market_data.providers.eastmoney import EastMoneyClient, EastMoneyError

DATA_PROVIDERS = [
    DataProviderInfo(
        id="eastmoney-realtime",
        name="东方财富实时行情",
        category="market-data",
        status="available",
        description="A 股实时价格、成交额、市值等快照数据。",
        endpoints=["/api/v1/quotes/realtime/{symbol}", "/api/v1/quotes/realtime"],
    ),
    DataProviderInfo(
        id="eastmoney-symbol-resolver",
        name="东方财富证券搜索",
        category="symbol",
        status="available",
        description="按股票代码、简称或中文名称解析证券标识和 secid。",
        endpoints=["/api/v1/symbols/resolve"],
    ),
    DataProviderInfo(
        id="eastmoney-kline",
        name="东方财富历史 K 线",
        category="market-data",
        status="degraded",
        description=(
            "A 股日线、周线、月线和常用分钟线历史行情；"
            "外部源偶发断连，后续会接入 AKShare/Tushare 降级源。"
        ),
        endpoints=["/api/v1/quotes/history/{symbol}"],
    ),
    DataProviderInfo(
        id="eastmoney-financial-summary",
        name="东方财富财务摘要",
        category="fundamental",
        status="available",
        description="上市公司主要财务指标、营收、归母净利润、ROE、毛利率等。",
        endpoints=["/api/v1/fundamentals/financials/{symbol}"],
    ),
    DataProviderInfo(
        id="eastmoney-announcements",
        name="东方财富公告事件",
        category="event",
        status="available",
        description="上市公司公告标题、公告日期、栏目和详情链接。",
        endpoints=["/api/v1/events/announcements/{symbol}"],
    ),
    DataProviderInfo(
        id="tushare-akshare-openbb",
        name="Tushare / AKShare / OpenBB 扩展源",
        category="planned-provider",
        status="planned",
        description="用于后续增强交易日历、指数、行业、宏观、海外资产等覆盖。",
        endpoints=[],
    ),
]


def create_app() -> FastAPI:
    app = FastAPI(
        title="QuantPilot Market Data API",
        description="QuantPilot 量化分析 Agent 的市场数据后端",
        version="0.1.0",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1):\d+$",
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    client = EastMoneyClient()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/registry", response_model=DataRegistryResponse)
    async def get_data_registry() -> DataRegistryResponse:
        return DataRegistryResponse(providers=DATA_PROVIDERS)

    @app.get("/api/v1/symbols/resolve", response_model=SymbolResolveResponse)
    async def resolve_symbol(query: str, count: int = 5) -> SymbolResolveResponse:
        try:
            results = await client.resolve_symbol(query, count=max(1, min(count, 20)))
            return SymbolResolveResponse(results=results, fetched_at=datetime.now(UTC))
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.get("/api/v1/quotes/realtime/{symbol}", response_model=RealtimeQuote)
    async def get_realtime_quote(symbol: str) -> RealtimeQuote:
        try:
            return await client.get_realtime_quote(symbol)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.post("/api/v1/quotes/realtime", response_model=BatchQuoteResponse)
    async def get_realtime_quotes(request: BatchQuoteRequest) -> BatchQuoteResponse:
        try:
            quotes = await client.get_realtime_quotes(request.symbols)
            return BatchQuoteResponse(quotes=quotes)
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.get("/api/v1/quotes/history/{symbol}", response_model=KlineResponse)
    async def get_history_quote(
        symbol: str,
        period: KlinePeriod = "daily",
        adjustment: Adjustment = "qfq",
        limit: int = 120,
        end: str = "20500101",
    ) -> KlineResponse:
        try:
            return await client.get_kline(
                symbol,
                period=period,
                adjustment=adjustment,
                limit=max(1, min(limit, 1000)),
                end=end,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.get("/api/v1/fundamentals/financials/{symbol}", response_model=FinancialReportsResponse)
    async def get_financial_reports(symbol: str, limit: int = 8) -> FinancialReportsResponse:
        try:
            reports = await client.get_financial_reports(symbol, limit=max(1, min(limit, 40)))
            return FinancialReportsResponse(
                symbol=symbol,
                reports=reports,
                fetched_at=datetime.now(UTC),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.get("/api/v1/events/announcements/{symbol}", response_model=AnnouncementResponse)
    async def get_announcements(symbol: str, limit: int = 20) -> AnnouncementResponse:
        try:
            announcements = await client.get_announcements(symbol, limit=max(1, min(limit, 100)))
            return AnnouncementResponse(
                symbol=symbol,
                announcements=announcements,
                fetched_at=datetime.now(UTC),
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    return app


app = create_app()
