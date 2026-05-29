from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware

from quantpilot_market_data.backtest import build_ma_crossover_backtest, build_strategy_backtest
from quantpilot_market_data.cache import MarketDataCache, ttl_from_env
from quantpilot_market_data.database import (
    DatabaseError,
    add_securities_to_universe,
    add_security_to_universe,
    create_ingestion_job,
    finish_ingestion_job,
    get_local_kline,
    get_universe_fetch_targets,
    list_ingestion_jobs,
    list_market_data_coverage,
    list_research_universe_members_page,
    list_research_universe_summaries,
    list_research_universes,
    normalize_fetch_symbol,
    upsert_kline_response,
    upsert_realtime_quote_snapshot,
)
from quantpilot_market_data.fundamentals import build_fundamental_indicators
from quantpilot_market_data.indicators import build_technical_indicators
from quantpilot_market_data.models import (
    Adjustment,
    AnnouncementResponse,
    AShareUniverseBatchImportRequest,
    AShareUniverseBatchImportResponse,
    BacktestResponse,
    BatchQuoteRequest,
    BatchQuoteResponse,
    DataProviderInfo,
    DataRegistryResponse,
    DividendEventsResponse,
    ETFUniverseBatchImportRequest,
    ETFUniverseBatchImportResponse,
    FinancialReportsResponse,
    FundamentalIndicatorsResponse,
    HistoryBatchIngestionRequest,
    HistoryIngestionRequest,
    HistoryIngestionResponse,
    HistoryIngestionSymbolResult,
    IngestionJobsResponse,
    KlinePeriod,
    KlineResponse,
    LocalKlineResponse,
    MarketDataCoverageResponse,
    RealtimeQuote,
    RealtimeSnapshotIngestionRequest,
    ResearchUniverseMemberCreateRequest,
    ResearchUniverseMemberCreateResponse,
    ResearchUniverseMembersPageResponse,
    ResearchUniverseResponse,
    ResearchUniverseSummaryResponse,
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
from quantpilot_market_data.providers.akshare import AkShareClient, AkShareError
from quantpilot_market_data.providers.baostock import BaoStockClient, BaoStockError
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
        limitations=[
            "实时行情使用短 TTL 缓存，盘中价格可能存在数秒延迟。",
            "可在收盘后通过 /api/v1/ingestion/eastmoney/realtime-snapshot 写入当日日线快照。",
        ],
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
            "当前环境到 push2his 历史域名直连和代理均被断开，保留为优先源但需要降级。"
        ),
        endpoints=["/api/v1/quotes/history/{symbol}"],
        cache_ttl_seconds=KLINE_CACHE_TTL_SECONDS,
        limitations=[
            "实时行情、分红和公告接口可用；历史 K 线 push2his 当前在本机不可达。",
            "历史入库默认严格东方财富，不会静默回落到腾讯，避免成交额和换手率缺失被误判。",
        ],
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
        name="QuantPilot 策略回测",
        category="backtest",
        status="available",
        description=(
            "基于历史 K 线运行单标的趋势、突破、均值回归和波动率策略，"
            "输出净值、回撤、交易明细、胜率、夏普和相对标的收益。"
        ),
        endpoints=[
            "/api/v1/backtests/ma-crossover/{symbol}",
            "/api/v1/backtests/strategies/{strategy_id}/{symbol}",
        ],
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
            "/api/v1/research/a-share/import-batch",
            "/api/v1/research/etf/import-batch",
            "/api/v1/research/data-coverage",
            "/api/v1/research/bars/{symbol}",
            "/api/v1/ingestion/jobs",
        ],
        cache_ttl_seconds=None,
    ),
    DataProviderInfo(
        id="eastmoney-history-ingestion",
        name="东方财富历史行情入库",
        category="ingestion",
        status="degraded",
        description=(
            "按股票池或指定标的拉取东方财富历史 K 线，并幂等写入 TimescaleDB；"
            "当前历史域名不可达。"
        ),
        endpoints=["/api/v1/ingestion/eastmoney/history"],
        cache_ttl_seconds=None,
        limitations=[
            "默认写入前复权日线；分钟线和多复权口径会按 adjustment 单独落库。",
            "支持 request_delay_seconds、max_retries 和 allow_fallback；allow_fallback 默认关闭。",
        ],
    ),
    DataProviderInfo(
        id="eastmoney-realtime-snapshot-ingestion",
        name="东方财富实时行情快照入库",
        category="ingestion",
        status="available",
        description="把东方财富实时行情快照写入 TimescaleDB 当日日线，用于补最新交易日。",
        endpoints=["/api/v1/ingestion/eastmoney/realtime-snapshot"],
        cache_ttl_seconds=None,
        limitations=[
            "适合收盘后补最新交易日；盘中执行会写入盘中快照。",
            "实时行情不稳定提供全部 ETF 换手率时，换手率字段会保留为空。",
        ],
    ),
    DataProviderInfo(
        id="tencent-a-share-kline",
        name="腾讯 A 股 K 线兜底",
        category="fallback-provider",
        status="available",
        description="腾讯公开 K 线端点当前探针可通，适合在东方财富历史 K 线失败时兜底量价样本。",
        endpoints=[
            "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get",
            "/api/v1/provider-candidates/probe?provider_id=tencent-a-share-kline",
        ],
        cache_ttl_seconds=KLINE_CACHE_TTL_SECONDS,
        limitations=[
            "非官方稳定 API，字段可能变化。",
            "当前只提供 OHLCV 和可推导涨跌幅，成交额、换手率通常为空。",
        ],
    ),
    DataProviderInfo(
        id="ths-public-kline",
        name="同花顺公开 K 线端点",
        category="candidate-provider",
        status="available",
        description=(
            "同花顺网页历史线数据端点当前探针可通，"
            "可作为 A 股历史 K 线候选源继续解析验证。"
        ),
        endpoints=[
            "https://d.10jqka.com.cn/v6/line/hs_{symbol}/01/all.js",
            "/api/v1/provider-candidates/probe?provider_id=ths-public-kline",
        ],
        cache_ttl_seconds=KLINE_CACHE_TTL_SECONDS,
        limitations=[
            "网页公开端点不是正式 SLA，返回为压缩 JavaScript，需要单独解析和字段校验。",
            "接入入库前需要确认复权口径、成交额、换手率和停牌样本。",
        ],
    ),
    DataProviderInfo(
        id="baostock-a-share-history",
        name="Baostock A 股历史行情",
        category="enrichment-provider",
        status="available",
        description="独立 A 股历史数据服务，已接入用于补日线成交额、换手率、涨跌幅和复权字段。",
        endpoints=[
            "/api/v1/ingestion/baostock/history",
            "/api/v1/ingestion/baostock/history/batch",
            "Python SDK: baostock.query_history_k_data_plus",
        ],
        cache_ttl_seconds=None,
        limitations=[
            "适合 A 股日/周/月历史补数，不用于实时行情主链路。",
            "当前已沉淀成交额、换手率、停牌/ST、涨跌停和 PE/PB/PS/PCF 等估值字段。",
            "Baostock volume 为股数，入库时折算成手，避免破坏现有 K 线量能展示口径。",
        ],
    ),
    DataProviderInfo(
        id="akshare-provider",
        name="AKShare 聚合数据源",
        category="enrichment-provider",
        status="degraded",
        description=(
            "Python 聚合数据源；当前用于补 A 股历史 K 线的成交额、振幅、"
            "涨跌额和换手率，作为东方财富历史端点不可达时的字段增强层。"
        ),
        endpoints=[
            "/api/v1/ingestion/akshare/history",
            "Python SDK: akshare.stock_zh_a_hist",
        ],
        cache_ttl_seconds=None,
        limitations=[
            "需要安装可选依赖：cd services/market-data && uv sync --extra akshare。",
            "部分 AKShare 接口本质仍依赖东方财富或网页公开端点，需要低频补数和字段质量检查。",
        ],
    ),
    DataProviderInfo(
        id="yahoo-finance-chart",
        name="Yahoo Finance Chart API / yfinance",
        category="fallback-provider",
        status="available",
        description=(
            "Yahoo Finance Chart API 当前探针可通，适合海外股票、ETF 和指数历史行情；"
            "后续可用 yfinance 封装。"
        ),
        endpoints=[
            "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
            "/api/v1/provider-candidates/probe?provider_id=yahoo-finance-chart",
        ],
        cache_ttl_seconds=KLINE_CACHE_TTL_SECONDS,
        limitations=[
            "非官方接口，可能限流或调整返回结构。",
            "主要用于海外市场，不作为 A 股历史行情主源。",
        ],
    ),
    DataProviderInfo(
        id="ths-ifind-quantapi",
        name="同花顺 iFinD / QuantAPI",
        category="licensed-provider",
        status="planned",
        description=(
            "同花顺正式数据接口，覆盖历史行情、基本面和指标数据，"
            "通常需要 iFinD 终端或授权账号。"
        ),
        endpoints=["同花顺 iFinD QuantAPI"],
        cache_ttl_seconds=None,
        limitations=[
            "需要商业授权、终端环境或账号登录，当前本地未配置凭证。",
            "适合正式生产数据源评估，不应和网页公开端点混为一类。",
        ],
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
            "/api/v1/research/etf/import-batch",
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
            "用于评估腾讯、新浪、同花顺公开端点、Stooq、Yahoo Finance、Alpha Vantage、"
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
    async def fetch_segment(end: str) -> KlineResponse:
        last_error: EastMoneyError | None = None
        for attempt in range(1, request.max_retries + 1):
            try:
                return await client.get_kline(
                    symbol_or_secid,
                    period=request.period,
                    adjustment=request.adjustment,
                    limit=request.limit,
                    end=end,
                    allow_fallback=request.allow_fallback,
                )
            except EastMoneyError as error:
                last_error = error
                if attempt >= request.max_retries:
                    break
                await asyncio.sleep(request.request_delay_seconds * attempt)
        assert last_error is not None
        raise last_error

    kline = await fetch_segment(request.end)
    await asyncio.sleep(request.request_delay_seconds)
    cutoff = _lookback_cutoff_date(request.lookback_years)

    for _ in range(6):
        first_bar = kline.bars[0] if kline.bars else None
        first_date = _parse_bar_date(first_bar.date) if first_bar else None
        if first_date is None or first_date <= cutoff:
            break

        earlier_end = (first_date - timedelta(days=1)).strftime("%Y%m%d")
        earlier = await fetch_segment(earlier_end)
        await asyncio.sleep(request.request_delay_seconds)
        if not earlier.bars:
            break

        previous_count = len(kline.bars)
        kline = _merge_kline_responses(kline, earlier)
        if len(kline.bars) <= previous_count:
            break

    return kline


async def fetch_akshare_kline_for_ingestion(
    client: AkShareClient,
    symbol_or_secid: str,
    request: HistoryIngestionRequest,
) -> KlineResponse:
    start_date = _lookback_cutoff_date(request.lookback_years).strftime("%Y%m%d")
    return await client.get_kline_range(
        symbol_or_secid,
        period=request.period,
        adjustment=request.adjustment,
        start_date=start_date,
        end_date=request.end,
        limit=request.limit,
    )


async def fetch_baostock_kline_for_ingestion(
    client: BaoStockClient,
    symbol_or_secid: str,
    request: HistoryIngestionRequest,
) -> KlineResponse:
    start_date = _lookback_cutoff_date(request.lookback_years).strftime("%Y-%m-%d")
    return await client.get_kline_range(
        symbol_or_secid,
        period=request.period,
        adjustment=request.adjustment,
        start_date=start_date,
        end_date=request.end,
        limit=request.limit,
    )


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


def strategy_backtest_parameters(request: Request) -> dict[str, str]:
    reserved = {
        "period",
        "adjustment",
        "limit",
        "end",
        "initial_cash",
        "fee_bps",
    }
    return {
        key: value
        for key, value in request.query_params.items()
        if key not in reserved and value not in {"", "undefined", "null"}
    }


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
    akshare_client = AkShareClient()
    baostock_client = BaoStockClient()
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

    @app.get(
        "/api/v1/research/universes/summary",
        response_model=ResearchUniverseSummaryResponse,
    )
    async def get_research_universe_summary() -> ResearchUniverseSummaryResponse:
        try:
            return ResearchUniverseSummaryResponse(
                universes=await list_research_universe_summaries()
            )
        except DatabaseError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post(
        "/api/v1/research/a-share/import-batch",
        response_model=AShareUniverseBatchImportResponse,
    )
    async def import_a_share_universe_batch(
        request: AShareUniverseBatchImportRequest,
    ) -> AShareUniverseBatchImportResponse:
        try:
            total_available, securities = await client.list_a_share_symbols(
                page=request.page,
                page_size=request.page_size,
            )
            stock_securities = [
                security for security in securities if security.asset_type == "stock"
            ]
            members = await add_securities_to_universe(
                universe_id=request.universe_id,
                securities=stock_securities,
                role=request.role,
            )
            total_pages = (total_available + request.page_size - 1) // request.page_size
            next_page = request.page + 1 if request.page < total_pages else None
            return AShareUniverseBatchImportResponse(
                universe_id=request.universe_id,
                page=request.page,
                page_size=request.page_size,
                total_available=total_available,
                total_pages=total_pages,
                next_page=next_page,
                imported_count=len(members),
                members=members,
            )
        except DatabaseError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

    @app.post(
        "/api/v1/research/etf/import-batch",
        response_model=ETFUniverseBatchImportResponse,
    )
    async def import_etf_universe_batch(
        request: ETFUniverseBatchImportRequest,
    ) -> ETFUniverseBatchImportResponse:
        try:
            total_available, securities = await client.list_etf_symbols(
                page=request.page,
                page_size=request.page_size,
            )
            members = await add_securities_to_universe(
                universe_id=request.universe_id,
                securities=securities,
                role=request.role,
                added_source="etf-batch-import",
            )
            total_pages = (total_available + request.page_size - 1) // request.page_size
            next_page = request.page + 1 if request.page < total_pages else None
            return ETFUniverseBatchImportResponse(
                universe_id=request.universe_id,
                page=request.page,
                page_size=request.page_size,
                total_available=total_available,
                total_pages=total_pages,
                next_page=next_page,
                imported_count=len(members),
                members=members,
            )
        except DatabaseError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
        except EastMoneyError as error:
            raise HTTPException(status_code=502, detail=str(error)) from error

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

    @app.get("/api/v1/ingestion/jobs", response_model=IngestionJobsResponse)
    async def get_market_data_ingestion_jobs(
        universe_id: str | None = None,
        limit: int = Query(default=20, ge=1, le=100),
    ) -> IngestionJobsResponse:
        try:
            return IngestionJobsResponse(
                jobs=await list_ingestion_jobs(universe_id=universe_id, limit=limit)
            )
        except DatabaseError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.get(
        "/api/v1/research/universes/{universe_id}/members",
        response_model=ResearchUniverseMembersPageResponse,
    )
    async def get_research_universe_members(
        universe_id: str,
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=10, ge=1, le=100),
        keyword: str | None = Query(default=None, max_length=80),
    ) -> ResearchUniverseMembersPageResponse:
        try:
            members, total, current_page, total_pages = await list_research_universe_members_page(
                universe_id=universe_id,
                page=page,
                page_size=page_size,
                keyword=keyword,
            )
            return ResearchUniverseMembersPageResponse(
                universe_id=universe_id,
                page=current_page,
                page_size=page_size,
                total=total,
                total_pages=total_pages,
                keyword=keyword.strip() if keyword else None,
                members=members,
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
                provider="eastmoney",
                timeframe=request.period,
                adjustment=request.adjustment,
                total_symbols=len(targets),
                metadata={
                    "symbols": targets,
                    "limit": request.limit,
                    "lookback_years": request.lookback_years,
                    "end": request.end,
                    "allow_fallback": request.allow_fallback,
                    "request_delay_seconds": request.request_delay_seconds,
                    "max_retries": request.max_retries,
                },
            )

            symbol_results: list[HistoryIngestionSymbolResult] = []
            for target_index, target in enumerate(targets):
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
                            source=kline.source,
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
                if target_index < len(targets) - 1 and request.request_delay_seconds:
                    await asyncio.sleep(request.request_delay_seconds)

            completed_symbols = len(
                [item for item in symbol_results if item.status in {"success", "skipped"}]
            )
            failed_symbols = len([item for item in symbol_results if item.status == "failed"])
            response = HistoryIngestionResponse(
                job_id=job_id,
                provider="eastmoney",
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

    @app.post("/api/v1/ingestion/akshare/history", response_model=HistoryIngestionResponse)
    async def ingest_akshare_history(
        request: HistoryIngestionRequest,
    ) -> HistoryIngestionResponse:
        started_at = datetime.now(UTC)
        job_id = f"ingest-akshare-{started_at.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
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
                provider="akshare",
                timeframe=request.period,
                adjustment=request.adjustment,
                total_symbols=len(targets),
                metadata={
                    "symbols": targets,
                    "limit": request.limit,
                    "lookback_years": request.lookback_years,
                    "end": request.end,
                    "request_delay_seconds": request.request_delay_seconds,
                    "max_retries": request.max_retries,
                    "source_strategy": "akshare-field-enrichment",
                    "field_contract": [
                        "amount",
                        "amplitude",
                        "change_percent",
                        "change_amount",
                        "turnover",
                    ],
                },
            )

            symbol_results: list[HistoryIngestionSymbolResult] = []
            for target_index, target in enumerate(targets):
                try:
                    kline = await fetch_akshare_kline_for_ingestion(
                        akshare_client,
                        target["query"],
                        request,
                    )
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
                            source=kline.source,
                            status="success" if rows_upserted else "skipped",
                            bars_received=len(kline.bars),
                            rows_upserted=rows_upserted,
                            first_date=first_date,
                            last_date=last_date,
                        )
                    )
                except (ValueError, AkShareError, DatabaseError) as error:
                    symbol_results.append(
                        HistoryIngestionSymbolResult(
                            symbol=target["symbol"],
                            status="failed",
                            error=str(error),
                        )
                    )
                if target_index < len(targets) - 1 and request.request_delay_seconds:
                    await asyncio.sleep(request.request_delay_seconds)

            completed_symbols = len(
                [item for item in symbol_results if item.status in {"success", "skipped"}]
            )
            failed_symbols = len([item for item in symbol_results if item.status == "failed"])
            response = HistoryIngestionResponse(
                job_id=job_id,
                provider="akshare",
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

    @app.post("/api/v1/ingestion/baostock/history", response_model=HistoryIngestionResponse)
    async def ingest_baostock_history(
        request: HistoryIngestionRequest,
    ) -> HistoryIngestionResponse:
        started_at = datetime.now(UTC)
        job_id = f"ingest-baostock-{started_at.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
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
                provider="baostock",
                timeframe=request.period,
                adjustment=request.adjustment,
                total_symbols=len(targets),
                metadata={
                    "symbols": targets,
                    "limit": request.limit,
                    "lookback_years": request.lookback_years,
                    "end": request.end,
                    "request_delay_seconds": request.request_delay_seconds,
                    "max_retries": request.max_retries,
                    "source_strategy": "baostock-field-enrichment",
                    "field_contract": [
                        "previous_close",
                        "amount",
                        "amplitude",
                        "change_percent",
                        "change_amount",
                        "turnover",
                        "trade_status",
                        "is_st",
                        "limit_up",
                        "limit_down",
                        "pe_ttm",
                        "pb_mrq",
                        "ps_ttm",
                        "pcf_ncf_ttm",
                    ],
                },
            )

            symbol_results: list[HistoryIngestionSymbolResult] = []
            for target_index, target in enumerate(targets):
                try:
                    kline = await fetch_baostock_kline_for_ingestion(
                        baostock_client,
                        target["query"],
                        request,
                    )
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
                            source=kline.source,
                            status="success" if rows_upserted else "skipped",
                            bars_received=len(kline.bars),
                            rows_upserted=rows_upserted,
                            first_date=first_date,
                            last_date=last_date,
                        )
                    )
                except (ValueError, BaoStockError, DatabaseError) as error:
                    symbol_results.append(
                        HistoryIngestionSymbolResult(
                            symbol=target["symbol"],
                            status="failed",
                            error=str(error),
                        )
                    )
                if target_index < len(targets) - 1 and request.request_delay_seconds:
                    await asyncio.sleep(request.request_delay_seconds)

            completed_symbols = len(
                [item for item in symbol_results if item.status in {"success", "skipped"}]
            )
            failed_symbols = len([item for item in symbol_results if item.status == "failed"])
            response = HistoryIngestionResponse(
                job_id=job_id,
                provider="baostock",
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

    @app.post(
        "/api/v1/ingestion/baostock/history/batch",
        response_model=HistoryIngestionResponse,
    )
    async def ingest_baostock_history_batch(
        request: HistoryBatchIngestionRequest,
    ) -> HistoryIngestionResponse:
        started_at = datetime.now(UTC)
        job_id = f"ingest-baostock-batch-{started_at.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
        try:
            all_targets = [
                {"symbol": symbol, "query": normalize_fetch_symbol(symbol)}
                for symbol in (request.symbols or [])
            ]
            if not all_targets and request.universe_id:
                all_targets = await get_universe_fetch_targets(request.universe_id)
            if not all_targets:
                raise HTTPException(status_code=400, detail="未指定 symbols，且股票池没有成员。")

            effective_offset = request.offset if request.offset < len(all_targets) else 0
            targets = all_targets[effective_offset : effective_offset + request.batch_size]
            next_offset = effective_offset + len(targets)
            if next_offset >= len(all_targets):
                next_offset = 0

            await create_ingestion_job(
                job_id=job_id,
                universe_id=request.universe_id,
                provider="baostock",
                timeframe=request.period,
                adjustment=request.adjustment,
                total_symbols=len(targets),
                metadata={
                    "symbols": targets,
                    "limit": request.limit,
                    "lookback_years": request.lookback_years,
                    "end": request.end,
                    "request_delay_seconds": request.request_delay_seconds,
                    "max_retries": request.max_retries,
                    "source_strategy": "baostock-low-frequency-batch-enrichment",
                    "batch_offset": effective_offset,
                    "batch_size": request.batch_size,
                    "next_offset": next_offset,
                    "universe_total_symbols": len(all_targets),
                    "field_contract": [
                        "previous_close",
                        "amount",
                        "amplitude",
                        "change_percent",
                        "change_amount",
                        "turnover",
                        "trade_status",
                        "is_st",
                        "limit_up",
                        "limit_down",
                        "pe_ttm",
                        "pb_mrq",
                        "ps_ttm",
                        "pcf_ncf_ttm",
                    ],
                },
            )

            symbol_results: list[HistoryIngestionSymbolResult] = []
            for target_index, target in enumerate(targets):
                try:
                    kline = await fetch_baostock_kline_for_ingestion(
                        baostock_client,
                        target["query"],
                        request,
                    )
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
                            source=kline.source,
                            status="success" if rows_upserted else "skipped",
                            bars_received=len(kline.bars),
                            rows_upserted=rows_upserted,
                            first_date=first_date,
                            last_date=last_date,
                        )
                    )
                except (ValueError, BaoStockError, DatabaseError) as error:
                    symbol_results.append(
                        HistoryIngestionSymbolResult(
                            symbol=target["symbol"],
                            status="failed",
                            error=str(error),
                        )
                    )
                if target_index < len(targets) - 1 and request.request_delay_seconds:
                    await asyncio.sleep(request.request_delay_seconds)

            completed_symbols = len(
                [item for item in symbol_results if item.status in {"success", "skipped"}]
            )
            failed_symbols = len([item for item in symbol_results if item.status == "failed"])
            response = HistoryIngestionResponse(
                job_id=job_id,
                provider="baostock",
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
                batch_offset=effective_offset,
                batch_size=request.batch_size,
                next_offset=next_offset,
                universe_total_symbols=len(all_targets),
                started_at=started_at,
                completed_at=datetime.now(UTC),
            )
            await finish_ingestion_job(response)
            return response
        except DatabaseError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    @app.post(
        "/api/v1/ingestion/eastmoney/realtime-snapshot",
        response_model=HistoryIngestionResponse,
    )
    async def ingest_eastmoney_realtime_snapshot(
        request: RealtimeSnapshotIngestionRequest,
    ) -> HistoryIngestionResponse:
        started_at = datetime.now(UTC)
        job_id = (
            f"ingest-eastmoney-snapshot-{started_at.strftime('%Y%m%d%H%M%S')}-"
            f"{uuid4().hex[:8]}"
        )
        try:
            all_targets = [
                {"symbol": symbol, "query": normalize_fetch_symbol(symbol)}
                for symbol in (request.symbols or [])
            ]
            if not all_targets and request.universe_id:
                all_targets = await get_universe_fetch_targets(request.universe_id)
            if not all_targets:
                raise HTTPException(status_code=400, detail="未指定 symbols，且股票池没有成员。")

            effective_offset = request.offset if request.offset < len(all_targets) else 0
            targets = all_targets[effective_offset : effective_offset + request.batch_size]
            next_offset = effective_offset + len(targets)
            if next_offset >= len(all_targets):
                next_offset = 0

            await create_ingestion_job(
                job_id=job_id,
                universe_id=request.universe_id,
                provider="eastmoney-realtime",
                timeframe="daily",
                adjustment=request.adjustment,
                total_symbols=len(targets),
                metadata={
                    "symbols": targets,
                    "trade_date": request.trade_date,
                    "batch_offset": effective_offset,
                    "batch_size": request.batch_size,
                    "next_offset": next_offset,
                    "universe_total_symbols": len(all_targets),
                    "source_strategy": "eastmoney-realtime-snapshot-daily-bar",
                    "field_contract": [
                        "open",
                        "high",
                        "low",
                        "close",
                        "previous_close",
                        "volume",
                        "amount",
                        "amplitude",
                        "change_percent",
                        "change_amount",
                        "turnover",
                    ],
                },
            )

            symbol_results: list[HistoryIngestionSymbolResult] = []
            try:
                quotes = await client.get_realtime_quotes([target["query"] for target in targets])
            except EastMoneyError as error:
                quotes = []
                symbol_results.extend(
                    HistoryIngestionSymbolResult(
                        symbol=target["symbol"],
                        status="failed",
                        error=str(error),
                    )
                    for target in targets
                )
            quotes_by_code = {quote.symbol: quote for quote in quotes}
            if quotes:
                for target in targets:
                    symbol = str(target["symbol"])
                    code = symbol.split(".", 1)[0]
                    quote = quotes_by_code.get(code)
                    if quote is None:
                        symbol_results.append(
                            HistoryIngestionSymbolResult(
                                symbol=symbol,
                                status="failed",
                                error="东方财富实时行情未返回该标的。",
                            )
                        )
                        continue
                    try:
                        (
                            canonical,
                            rows_upserted,
                            first_date,
                            last_date,
                        ) = await upsert_realtime_quote_snapshot(
                            quote,
                            universe_id=request.universe_id,
                            trade_date=request.trade_date,
                            adjustment=request.adjustment,
                        )
                        symbol_results.append(
                            HistoryIngestionSymbolResult(
                                symbol=canonical,
                                name=quote.name,
                                secid=quote.secid,
                                source=quote.source,
                                status="success" if rows_upserted else "skipped",
                                bars_received=1,
                                rows_upserted=rows_upserted,
                                first_date=first_date,
                                last_date=last_date,
                            )
                        )
                    except (ValueError, DatabaseError) as error:
                        symbol_results.append(
                            HistoryIngestionSymbolResult(
                                symbol=symbol,
                                status="failed",
                                error=str(error),
                            )
                        )
            if request.request_delay_seconds:
                await asyncio.sleep(request.request_delay_seconds)

            completed_symbols = len(
                [item for item in symbol_results if item.status in {"success", "skipped"}]
            )
            failed_symbols = len([item for item in symbol_results if item.status == "failed"])
            response = HistoryIngestionResponse(
                job_id=job_id,
                provider="eastmoney-realtime",
                status=(
                    "failed"
                    if completed_symbols == 0
                    else "partial"
                    if failed_symbols
                    else "completed"
                ),
                universe_id=request.universe_id,
                period="daily",
                adjustment=request.adjustment,
                lookback_years=1,
                total_symbols=len(targets),
                completed_symbols=completed_symbols,
                failed_symbols=failed_symbols,
                rows_received=sum(item.bars_received for item in symbol_results),
                rows_upserted=sum(item.rows_upserted for item in symbol_results),
                symbols=symbol_results,
                batch_offset=effective_offset,
                batch_size=request.batch_size,
                next_offset=next_offset,
                universe_total_symbols=len(all_targets),
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

    @app.get(
        "/api/v1/backtests/strategies/{strategy_id}/{symbol}",
        response_model=BacktestResponse,
    )
    async def get_strategy_backtest(
        request: Request,
        strategy_id: str,
        symbol: str,
        period: KlinePeriod = "daily",
        adjustment: Adjustment = "qfq",
        limit: int = 1000,
        end: str = "20500101",
        initial_cash: Decimal = Decimal("1"),
        fee_bps: Decimal = Decimal("5"),
    ) -> BacktestResponse:
        normalized_limit = max(80, min(limit, 1500))
        parameters = strategy_backtest_parameters(request)
        cache_key = cache.build_key(
            "backtest-strategy",
            {
                "strategy_id": strategy_id,
                "symbol": symbol,
                "parameters": parameters,
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
            response = build_strategy_backtest(
                kline,
                strategy_id=strategy_id,
                parameters=parameters,
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
