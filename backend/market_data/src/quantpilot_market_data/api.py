from __future__ import annotations

from datetime import UTC, datetime

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from quantpilot_market_data.cache import MarketDataCache, ttl_from_env
from quantpilot_market_data.fundamentals import build_fundamental_indicators
from quantpilot_market_data.indicators import build_technical_indicators
from quantpilot_market_data.models import (
    Adjustment,
    AnnouncementResponse,
    BatchQuoteRequest,
    BatchQuoteResponse,
    DataProviderInfo,
    DataRegistryResponse,
    FinancialReportsResponse,
    FundamentalIndicatorsResponse,
    KlinePeriod,
    KlineResponse,
    RealtimeQuote,
    SymbolResolveResponse,
    TechnicalIndicatorsResponse,
)
from quantpilot_market_data.providers.eastmoney import EastMoneyClient, EastMoneyError

QUOTE_CACHE_TTL_SECONDS = ttl_from_env("QUANTPILOT_QUOTE_CACHE_TTL_SECONDS", 5)
SYMBOL_CACHE_TTL_SECONDS = ttl_from_env("QUANTPILOT_SYMBOL_CACHE_TTL_SECONDS", 86400)
KLINE_CACHE_TTL_SECONDS = ttl_from_env("QUANTPILOT_KLINE_CACHE_TTL_SECONDS", 1800)
FINANCIAL_CACHE_TTL_SECONDS = ttl_from_env("QUANTPILOT_FINANCIAL_CACHE_TTL_SECONDS", 21600)
ANNOUNCEMENT_CACHE_TTL_SECONDS = ttl_from_env("QUANTPILOT_ANNOUNCEMENT_CACHE_TTL_SECONDS", 600)

DATA_PROVIDERS = [
    DataProviderInfo(
        id="eastmoney-realtime",
        name="东方财富实时行情",
        category="market-data",
        status="available",
        description="A 股实时价格、成交额、市值等快照数据。",
        endpoints=["/api/v1/quotes/realtime/{symbol}", "/api/v1/quotes/realtime"],
        cache_ttl_seconds=QUOTE_CACHE_TTL_SECONDS,
        limitations=["实时行情使用短 TTL 缓存，盘中价格可能存在数秒延迟。"],
    ),
    DataProviderInfo(
        id="eastmoney-symbol-resolver",
        name="东方财富证券搜索",
        category="symbol",
        status="available",
        description="按股票代码、简称或中文名称解析证券标识和 secid。",
        endpoints=["/api/v1/symbols/resolve"],
        cache_ttl_seconds=SYMBOL_CACHE_TTL_SECONDS,
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
        cache_ttl_seconds=KLINE_CACHE_TTL_SECONDS,
        limitations=["日线及以上周期可缓存较久，分钟线后续会单独细化 TTL。"],
    ),
    DataProviderInfo(
        id="quantpilot-technical-indicators",
        name="QuantPilot 技术指标",
        category="indicator",
        status="available",
        description="基于历史 K 线计算 MA5/MA10/MA20、区间收益、最大回撤和年化波动率。",
        endpoints=["/api/v1/indicators/technical/{symbol}"],
        cache_ttl_seconds=KLINE_CACHE_TTL_SECONDS,
    ),
    DataProviderInfo(
        id="eastmoney-financial-summary",
        name="东方财富财务摘要",
        category="fundamental",
        status="available",
        description="上市公司主要财务指标、营收、归母净利润、ROE、毛利率等。",
        endpoints=["/api/v1/fundamentals/financials/{symbol}"],
        cache_ttl_seconds=FINANCIAL_CACHE_TTL_SECONDS,
    ),
    DataProviderInfo(
        id="quantpilot-fundamental-indicators",
        name="QuantPilot 财务衍生指标",
        category="fundamental",
        status="available",
        description="基于财务摘要计算净利率、平均 ROE、平均毛利率和最近报告期核心指标。",
        endpoints=["/api/v1/indicators/fundamental/{symbol}"],
        cache_ttl_seconds=FINANCIAL_CACHE_TTL_SECONDS,
    ),
    DataProviderInfo(
        id="eastmoney-announcements",
        name="东方财富公告事件",
        category="event",
        status="available",
        description="上市公司公告标题、公告日期、栏目和详情链接。",
        endpoints=["/api/v1/events/announcements/{symbol}"],
        cache_ttl_seconds=ANNOUNCEMENT_CACHE_TTL_SECONDS,
        limitations=["公告列表按东方财富公开接口返回，公告全文解析后续单独增强。"],
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
    cache = MarketDataCache()

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/v1/registry", response_model=DataRegistryResponse)
    async def get_data_registry() -> DataRegistryResponse:
        return DataRegistryResponse(providers=DATA_PROVIDERS)

    @app.get("/api/v1/symbols/resolve", response_model=SymbolResolveResponse)
    async def resolve_symbol(query: str, count: int = 5) -> SymbolResolveResponse:
        normalized_count = max(1, min(count, 20))
        cache_key = cache.build_key("symbols-resolve", {"query": query, "count": normalized_count})
        try:
            cached = cache.read(cache_key)
            if cached is not None:
                return SymbolResolveResponse.model_validate(cached.payload).model_copy(
                    update={"fetch": cached.to_fetch_metadata("hit")}
                )

            results = await client.resolve_symbol(query, count=normalized_count)
            response = SymbolResolveResponse(results=results, fetched_at=datetime.now(UTC))
            return cache_response(
                cache,
                cache_key,
                SYMBOL_CACHE_TTL_SECONDS,
                response,
                SymbolResolveResponse,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.get("/api/v1/quotes/realtime/{symbol}", response_model=RealtimeQuote)
    async def get_realtime_quote(symbol: str) -> RealtimeQuote:
        cache_key = cache.build_key("quote-realtime", {"symbol": symbol})
        try:
            cached = cache.read(cache_key)
            if cached is not None:
                return RealtimeQuote.model_validate(cached.payload).model_copy(
                    update={"fetch": cached.to_fetch_metadata("hit")}
                )

            quote = await client.get_realtime_quote(symbol)
            return cache_response(
                cache,
                cache_key,
                QUOTE_CACHE_TTL_SECONDS,
                quote,
                RealtimeQuote,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.post("/api/v1/quotes/realtime", response_model=BatchQuoteResponse)
    async def get_realtime_quotes(request: BatchQuoteRequest) -> BatchQuoteResponse:
        normalized_symbols = [symbol.strip() for symbol in request.symbols]
        cache_key = cache.build_key("quote-realtime-batch", {"symbols": normalized_symbols})
        try:
            cached = cache.read(cache_key)
            if cached is not None:
                return BatchQuoteResponse.model_validate(cached.payload).model_copy(
                    update={"fetch": cached.to_fetch_metadata("hit")}
                )

            quotes = await client.get_realtime_quotes(normalized_symbols)
            response = BatchQuoteResponse(quotes=quotes)
            return cache_response(
                cache,
                cache_key,
                QUOTE_CACHE_TTL_SECONDS,
                response,
                BatchQuoteResponse,
            )
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
        normalized_limit = max(1, min(limit, 1000))
        cache_key = cache.build_key(
            "quote-history",
            {
                "symbol": symbol,
                "period": period,
                "adjustment": adjustment,
                "limit": normalized_limit,
                "end": end,
            },
        )
        try:
            cached = cache.read(cache_key)
            if cached is not None:
                return KlineResponse.model_validate(cached.payload).model_copy(
                    update={"fetch": cached.to_fetch_metadata("hit")}
                )

            response = await client.get_kline(
                symbol,
                period=period,
                adjustment=adjustment,
                limit=normalized_limit,
                end=end,
            )
            return cache_response(
                cache,
                cache_key,
                KLINE_CACHE_TTL_SECONDS,
                response,
                KlineResponse,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.get("/api/v1/indicators/technical/{symbol}", response_model=TechnicalIndicatorsResponse)
    async def get_technical_indicators(
        symbol: str,
        period: KlinePeriod = "daily",
        adjustment: Adjustment = "qfq",
        limit: int = 120,
        end: str = "20500101",
    ) -> TechnicalIndicatorsResponse:
        normalized_limit = max(1, min(limit, 1000))
        cache_key = cache.build_key(
            "technical-indicators",
            {
                "symbol": symbol,
                "period": period,
                "adjustment": adjustment,
                "limit": normalized_limit,
                "end": end,
            },
        )
        try:
            cached = cache.read(cache_key)
            if cached is not None:
                return TechnicalIndicatorsResponse.model_validate(cached.payload).model_copy(
                    update={"fetch": cached.to_fetch_metadata("hit")}
                )

            kline = await client.get_kline(
                symbol,
                period=period,
                adjustment=adjustment,
                limit=normalized_limit,
                end=end,
            )
            response = build_technical_indicators(kline)
            return cache_response(
                cache,
                cache_key,
                KLINE_CACHE_TTL_SECONDS,
                response,
                TechnicalIndicatorsResponse,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.get("/api/v1/fundamentals/financials/{symbol}", response_model=FinancialReportsResponse)
    async def get_financial_reports(symbol: str, limit: int = 8) -> FinancialReportsResponse:
        normalized_limit = max(1, min(limit, 40))
        cache_key = cache.build_key(
            "fundamental-financials",
            {"symbol": symbol, "limit": normalized_limit},
        )
        try:
            cached = cache.read(cache_key)
            if cached is not None:
                return FinancialReportsResponse.model_validate(cached.payload).model_copy(
                    update={"fetch": cached.to_fetch_metadata("hit")}
                )

            reports = await client.get_financial_reports(symbol, limit=normalized_limit)
            response = FinancialReportsResponse(
                symbol=symbol,
                reports=reports,
                fetched_at=datetime.now(UTC),
            )
            return cache_response(
                cache,
                cache_key,
                FINANCIAL_CACHE_TTL_SECONDS,
                response,
                FinancialReportsResponse,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.get(
        "/api/v1/indicators/fundamental/{symbol}",
        response_model=FundamentalIndicatorsResponse,
    )
    async def get_fundamental_indicators(
        symbol: str,
        limit: int = 8,
    ) -> FundamentalIndicatorsResponse:
        normalized_limit = max(1, min(limit, 40))
        cache_key = cache.build_key(
            "fundamental-indicators",
            {"symbol": symbol, "limit": normalized_limit},
        )
        try:
            cached = cache.read(cache_key)
            if cached is not None:
                return FundamentalIndicatorsResponse.model_validate(cached.payload).model_copy(
                    update={"fetch": cached.to_fetch_metadata("hit")}
                )

            reports = await client.get_financial_reports(symbol, limit=normalized_limit)
            response = build_fundamental_indicators(symbol, reports)
            return cache_response(
                cache,
                cache_key,
                FINANCIAL_CACHE_TTL_SECONDS,
                response,
                FundamentalIndicatorsResponse,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.get("/api/v1/events/announcements/{symbol}", response_model=AnnouncementResponse)
    async def get_announcements(symbol: str, limit: int = 20) -> AnnouncementResponse:
        normalized_limit = max(1, min(limit, 100))
        cache_key = cache.build_key(
            "announcement-events",
            {"symbol": symbol, "limit": normalized_limit},
        )
        try:
            cached = cache.read(cache_key)
            if cached is not None:
                return AnnouncementResponse.model_validate(cached.payload).model_copy(
                    update={"fetch": cached.to_fetch_metadata("hit")}
                )

            announcements = await client.get_announcements(symbol, limit=normalized_limit)
            response = AnnouncementResponse(
                symbol=symbol,
                announcements=announcements,
                fetched_at=datetime.now(UTC),
            )
            return cache_response(
                cache,
                cache_key,
                ANNOUNCEMENT_CACHE_TTL_SECONDS,
                response,
                AnnouncementResponse,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    return app


def cache_response[T](
    cache: MarketDataCache,
    cache_key: str,
    ttl_seconds: int,
    response: T,
    model_type: type[T],
) -> T:
    if not hasattr(response, "model_dump") or not hasattr(response, "model_copy"):
        return response

    if not cache.enabled:
        return response.model_copy(  # type: ignore[union-attr, no-any-return]
            update={"fetch": cache.disabled_metadata(cache_key, ttl_seconds)}
        )

    response_with_metadata = response.model_copy(  # type: ignore[union-attr]
        update={"fetch": cache.miss_metadata(cache_key, ttl_seconds)}
    )
    cached = cache.write(
        cache_key,
        ttl_seconds=ttl_seconds,
        payload=response_with_metadata.model_dump(mode="json"),  # type: ignore[union-attr]
    )
    if cached is None:
        return response_with_metadata  # type: ignore[return-value]

    return model_type.model_validate(  # type: ignore[attr-defined, no-any-return]
        response_with_metadata.model_dump(mode="json")  # type: ignore[union-attr]
    ).model_copy(update={"fetch": cached.to_fetch_metadata("miss")})


app = create_app()
