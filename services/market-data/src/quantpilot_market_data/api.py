from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from quantpilot_market_data.backtest import build_ma_crossover_backtest
from quantpilot_market_data.cache import MarketDataCache, ttl_from_env
from quantpilot_market_data.database import (
    DatabaseError,
    add_security_to_universe,
    create_ingestion_job,
    finish_ingestion_job,
    get_local_kline,
    get_universe_fetch_targets,
    list_market_data_coverage,
    list_research_universes,
    normalize_fetch_symbol,
    upsert_kline_response,
)
from quantpilot_market_data.fundamentals import build_fundamental_indicators
from quantpilot_market_data.indicators import build_technical_indicators
from quantpilot_market_data.models import (
    Adjustment,
    AnnouncementResponse,
    BacktestResponse,
    BatchQuoteRequest,
    BatchQuoteResponse,
    DataProviderInfo,
    DataRegistryResponse,
    DividendEventsResponse,
    FinancialReportsResponse,
    FundamentalIndicatorsResponse,
    HistoryIngestionRequest,
    HistoryIngestionResponse,
    HistoryIngestionSymbolResult,
    KlinePeriod,
    KlineResponse,
    LocalKlineResponse,
    MarketDataCoverageResponse,
    RealtimeQuote,
    ResearchUniverseMemberCreateRequest,
    ResearchUniverseMemberCreateResponse,
    ResearchUniverseResponse,
    SymbolResolveResponse,
    SymbolResolveResult,
    TechnicalIndicatorsResponse,
)
from quantpilot_market_data.provider_candidates import (
    CANDIDATE_PROVIDERS,
    CandidateProviderProbeResponse,
    CandidateProviderRegistry,
    get_candidate_provider,
    probe_candidate_provider,
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
        name="东方财富历史 K 线 / 指数 / ETF",
        category="market-data",
        status="degraded",
        description=(
            "A 股个股、常见指数和 ETF 的日线、周线、月线和常用分钟线历史行情；"
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
        description=(
            "基于个股、指数或 ETF 历史 K 线计算 MA5/MA10/MA20、"
            "区间收益、最大回撤和年化波动率。"
        ),
        endpoints=["/api/v1/indicators/technical/{symbol}"],
        cache_ttl_seconds=KLINE_CACHE_TTL_SECONDS,
    ),
    DataProviderInfo(
        id="quantpilot-ma-crossover-backtest",
        name="QuantPilot 均线突破回测",
        category="backtest",
        status="available",
        description=(
            "基于历史 K 线运行单标的均线突破策略，输出净值、回撤、交易明细、胜率、"
            "夏普和相对标的收益。"
        ),
        endpoints=["/api/v1/backtests/ma-crossover/{symbol}"],
        cache_ttl_seconds=KLINE_CACHE_TTL_SECONDS,
        limitations=["当前为单标的、全仓/空仓、日线级回测，暂不包含滑点、停牌和分红再投资建模。"],
    ),
    DataProviderInfo(
        id="quantpilot-research-universe",
        name="QuantPilot 策略研究股票池",
        category="research-config",
        status="available",
        description="读取本地 PostgreSQL/TimescaleDB 中的策略研究股票池、成员证券和行情覆盖状态。",
        endpoints=[
            "/api/v1/research/universes",
            "/api/v1/research/data-coverage",
            "/api/v1/research/bars/{symbol}",
        ],
        cache_ttl_seconds=None,
    ),
    DataProviderInfo(
        id="eastmoney-history-ingestion",
        name="东方财富历史行情入库",
        category="ingestion",
        status="available",
        description="按股票池或指定标的拉取东方财富历史 K 线，并幂等写入 TimescaleDB。",
        endpoints=["/api/v1/ingestion/eastmoney/history"],
        cache_ttl_seconds=None,
        limitations=["默认写入前复权日线；分钟线和多复权口径会按 adjustment 单独落库。"],
    ),
    DataProviderInfo(
        id="eastmoney-index-etf-market",
        name="东方财富指数与 ETF 行情",
        category="index-etf",
        status="available",
        description=(
            "常见指数和 ETF 的实时行情、历史 K 线与技术指标，"
            "支持沪深300、创业板指、中证500、科创50、510300 等。"
        ),
        endpoints=[
            "/api/v1/symbols/resolve",
            "/api/v1/quotes/realtime/{symbol}",
            "/api/v1/quotes/history/{symbol}",
            "/api/v1/indicators/technical/{symbol}",
        ],
        cache_ttl_seconds=KLINE_CACHE_TTL_SECONDS,
        limitations=["指数/ETF 默认不提供个股财务摘要和公告事件。"],
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
        id="eastmoney-dividend-events",
        name="东方财富分红送配事件",
        category="event",
        status="available",
        description="上市公司分红送配、股权登记日和除权除息日事件。",
        endpoints=["/api/v1/events/dividends/{symbol}"],
        cache_ttl_seconds=FINANCIAL_CACHE_TTL_SECONDS,
        limitations=["分红送配来自东方财富数据中心公开接口，图表默认用除权除息日对齐 K 线。"],
    ),
    DataProviderInfo(
        id="tushare-akshare-openbb",
        name="免费/免费层候选信源测试池",
        category="planned-provider",
        status="available",
        description=(
            "用于评估腾讯、新浪、Stooq、Yahoo Finance、Alpha Vantage、"
            "Finnhub、Twelve Data 等候选信源。"
        ),
        endpoints=["/api/v1/provider-candidates", "/api/v1/provider-candidates/probe"],
        limitations=["候选源不会直接替换主链路，必须先通过探针和数据质量评估。"],
    ),
]


def _parse_bar_date(value: str):
    text = value.split(" ", 1)[0]
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _lookback_cutoff_date(years: int):
    today = datetime.now(UTC).date()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


def _merge_kline_responses(current: KlineResponse, earlier: KlineResponse) -> KlineResponse:
    bars_by_date = {bar.date: bar for bar in current.bars}
    bars_by_date.update({bar.date: bar for bar in earlier.bars})
    bars = sorted(bars_by_date.values(), key=lambda bar: bar.date)
    return current.model_copy(update={"bars": bars, "source": current.source or earlier.source})


async def fetch_kline_for_ingestion(
    client: EastMoneyClient,
    symbol_or_secid: str,
    request: HistoryIngestionRequest,
) -> KlineResponse:
    kline = await client.get_kline(
        symbol_or_secid,
        period=request.period,
        adjustment=request.adjustment,
        limit=request.limit,
        end=request.end,
    )
    cutoff = _lookback_cutoff_date(request.lookback_years)

    for _ in range(6):
        first_bar = kline.bars[0] if kline.bars else None
        first_date = _parse_bar_date(first_bar.date) if first_bar else None
        if first_date is None or first_date <= cutoff:
            break

        earlier_end = (first_date - timedelta(days=1)).strftime("%Y%m%d")
        earlier = await client.get_kline(
            symbol_or_secid,
            period=request.period,
            adjustment=request.adjustment,
            limit=request.limit,
            end=earlier_end,
        )
        if not earlier.bars:
            break

        previous_count = len(kline.bars)
        kline = _merge_kline_responses(kline, earlier)
        if len(kline.bars) <= previous_count:
            break

    return kline


async def resolve_research_security(
    client: EastMoneyClient,
    query: str,
) -> tuple[SymbolResolveResult, list[SymbolResolveResult]]:
    candidates = await client.resolve_symbol(query, count=8)
    preferred = next(
        (
            item
            for item in candidates
            if item.asset_type == "stock"
            and item.market in {"SH", "SZ", "BJ"}
            and item.symbol.isdigit()
            and len(item.symbol) == 6
        ),
        None,
    )
    if preferred is None:
        preferred = next((item for item in candidates if item.asset_type == "stock"), None)
    if preferred is None and candidates:
        preferred = candidates[0]
    if preferred is not None:
        return preferred, candidates

    quote = await client.get_realtime_quote(query)
    resolved = SymbolResolveResult(
        query=query,
        symbol=quote.symbol,
        name=quote.name,
        asset_type=quote.asset_type,
        market=quote.market,
        secid=quote.secid,
        source=quote.source,
        raw={},
    )
    return resolved, [resolved]


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

    @app.get("/api/v1/research/universes", response_model=ResearchUniverseResponse)
    async def get_research_universes() -> ResearchUniverseResponse:
        try:
            return ResearchUniverseResponse(universes=await list_research_universes())
        except DatabaseError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get("/api/v1/research/data-coverage", response_model=MarketDataCoverageResponse)
    async def get_research_data_coverage(
        universe_id: str | None = "a-share-sample-research-pool",
    ) -> MarketDataCoverageResponse:
        try:
            return MarketDataCoverageResponse(
                universe_id=universe_id,
                items=await list_market_data_coverage(universe_id),
            )
        except DatabaseError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get("/api/v1/research/bars/{symbol}", response_model=LocalKlineResponse)
    async def get_research_local_bars(
        symbol: str,
        timeframe: KlinePeriod = "daily",
        adjustment: Adjustment = "qfq",
        provider: str | None = None,
        limit: int = 240,
    ) -> LocalKlineResponse:
        try:
            return await get_local_kline(
                symbol=symbol.strip().upper(),
                timeframe=timeframe,
                adjustment=adjustment,
                provider=provider.strip() if provider and provider.strip() else None,
                limit=limit,
            )
        except DatabaseError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post(
        "/api/v1/research/universes/{universe_id}/members",
        response_model=ResearchUniverseMemberCreateResponse,
    )
    async def add_research_universe_member(
        universe_id: str,
        request: ResearchUniverseMemberCreateRequest,
    ) -> ResearchUniverseMemberCreateResponse:
        try:
            security, candidates = await resolve_research_security(client, request.query.strip())
            member = await add_security_to_universe(
                universe_id=universe_id,
                security=security,
                role=request.role,
                weight=request.weight,
            )
            return ResearchUniverseMemberCreateResponse(
                universe_id=universe_id,
                member=member,
                candidates=candidates,
            )
        except ValueError as error:
            raise HTTPException(status_code=400, detail=str(error)) from error
        except DatabaseError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.post("/api/v1/ingestion/eastmoney/history", response_model=HistoryIngestionResponse)
    async def ingest_eastmoney_history(
        request: HistoryIngestionRequest,
    ) -> HistoryIngestionResponse:
        started_at = datetime.now(UTC)
        job_id = f"ingest-{started_at.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
        try:
            targets = [
                {"symbol": symbol, "query": normalize_fetch_symbol(symbol)}
                for symbol in (request.symbols or [])
            ]
            if not targets and request.universe_id:
                targets = await get_universe_fetch_targets(request.universe_id)
            if not targets:
                raise HTTPException(status_code=400, detail="未指定 symbols，且股票池没有成员。")

            await create_ingestion_job(
                job_id=job_id,
                universe_id=request.universe_id,
                timeframe=request.period,
                adjustment=request.adjustment,
                total_symbols=len(targets),
                metadata={
                    "symbols": targets,
                    "limit": request.limit,
                    "lookback_years": request.lookback_years,
                    "end": request.end,
                },
            )

            symbol_results: list[HistoryIngestionSymbolResult] = []
            for target in targets:
                try:
                    kline = await fetch_kline_for_ingestion(client, target["query"], request)
                    symbol, rows_upserted, first_date, last_date = await upsert_kline_response(
                        kline,
                        universe_id=request.universe_id,
                        lookback_years=request.lookback_years,
                    )
                    symbol_results.append(
                        HistoryIngestionSymbolResult(
                            symbol=symbol,
                            name=kline.name,
                            secid=kline.secid,
                            status="success" if rows_upserted else "skipped",
                            bars_received=len(kline.bars),
                            rows_upserted=rows_upserted,
                            first_date=first_date,
                            last_date=last_date,
                        )
                    )
                except (ValueError, EastMoneyError, DatabaseError) as error:
                    symbol_results.append(
                        HistoryIngestionSymbolResult(
                            symbol=target["symbol"],
                            status="failed",
                            error=str(error),
                        )
                    )

            completed_symbols = len(
                [item for item in symbol_results if item.status in {"success", "skipped"}]
            )
            failed_symbols = len([item for item in symbol_results if item.status == "failed"])
            response = HistoryIngestionResponse(
                job_id=job_id,
                status=(
                    "failed"
                    if completed_symbols == 0
                    else "partial"
                    if failed_symbols
                    else "completed"
                ),
                universe_id=request.universe_id,
                period=request.period,
                adjustment=request.adjustment,
                lookback_years=request.lookback_years,
                total_symbols=len(targets),
                completed_symbols=completed_symbols,
                failed_symbols=failed_symbols,
                rows_received=sum(item.bars_received for item in symbol_results),
                rows_upserted=sum(item.rows_upserted for item in symbol_results),
                symbols=symbol_results,
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
            await finish_ingestion_job(response)
            return response
        except DatabaseError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get("/api/v1/provider-candidates", response_model=CandidateProviderRegistry)
    async def get_provider_candidates() -> CandidateProviderRegistry:
        return CandidateProviderRegistry(providers=CANDIDATE_PROVIDERS)

    @app.get("/api/v1/provider-candidates/probe", response_model=CandidateProviderProbeResponse)
    async def probe_provider_candidates(
        provider_id: str | None = None,
    ) -> CandidateProviderProbeResponse:
        providers = CANDIDATE_PROVIDERS
        if provider_id:
            provider = get_candidate_provider(provider_id)
            if provider is None:
                raise HTTPException(status_code=404, detail=f"候选信源不存在：{provider_id}")
            providers = [provider]

        results = [await probe_candidate_provider(provider) for provider in providers]
        return CandidateProviderProbeResponse(results=results)

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

    @app.get("/api/v1/backtests/ma-crossover/{symbol}", response_model=BacktestResponse)
    async def get_ma_crossover_backtest(
        symbol: str,
        fast_window: int = 20,
        slow_window: int = 60,
        period: KlinePeriod = "daily",
        adjustment: Adjustment = "qfq",
        limit: int = 250,
        end: str = "20500101",
        initial_cash: Decimal = Decimal("1"),
        fee_bps: Decimal = Decimal("5"),
    ) -> BacktestResponse:
        normalized_fast = max(2, min(fast_window, 120))
        normalized_slow = max(3, min(slow_window, 250))
        normalized_limit = max(normalized_slow + 5, min(limit, 1000))
        cache_key = cache.build_key(
            "backtest-ma-crossover",
            {
                "symbol": symbol,
                "fast_window": normalized_fast,
                "slow_window": normalized_slow,
                "period": period,
                "adjustment": adjustment,
                "limit": normalized_limit,
                "end": end,
                "initial_cash": str(initial_cash),
                "fee_bps": str(fee_bps),
            },
        )
        try:
            cached = cache.read(cache_key)
            if cached is not None:
                return BacktestResponse.model_validate(cached.payload).model_copy(
                    update={"fetch": cached.to_fetch_metadata("hit")}
                )

            kline = await client.get_kline(
                symbol,
                period=period,
                adjustment=adjustment,
                limit=normalized_limit,
                end=end,
            )
            response = build_ma_crossover_backtest(
                kline,
                fast_window=normalized_fast,
                slow_window=normalized_slow,
                initial_cash=initial_cash,
                fee_bps=fee_bps,
            )
            return cache_response(
                cache,
                cache_key,
                KLINE_CACHE_TTL_SECONDS,
                response,
                BacktestResponse,
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

    @app.get("/api/v1/events/dividends/{symbol}", response_model=DividendEventsResponse)
    async def get_dividend_events(symbol: str, limit: int = 20) -> DividendEventsResponse:
        normalized_limit = max(1, min(limit, 100))
        cache_key = cache.build_key(
            "dividend-events",
            {"symbol": symbol, "limit": normalized_limit},
        )
        try:
            cached = cache.read(cache_key)
            if cached is not None:
                return DividendEventsResponse.model_validate(cached.payload)

            response = DividendEventsResponse(
                symbol=symbol,
                events=await client.get_dividend_events(symbol, limit=normalized_limit),
                fetched_at=datetime.now(UTC),
            )
            cache.write(
                cache_key,
                ttl_seconds=FINANCIAL_CACHE_TTL_SECONDS,
                payload=response.model_dump(mode="json"),
            )
            return response
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
