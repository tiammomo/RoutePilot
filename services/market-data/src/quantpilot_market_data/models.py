from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator

MarketCode = Literal["SH", "SZ", "BJ", "UNKNOWN"]
AssetType = Literal["stock", "index", "etf", "fund", "mixed", "unknown"]
DataQualityStatus = Literal["ok", "warning", "error"]
CacheStatus = Literal["hit", "miss", "disabled", "bypass"]


class DataQuality(BaseModel):
    """统一数据质量摘要，供 Agent 和前端判断数据是否可直接使用。"""

    status: DataQualityStatus = Field(default="ok", description="数据质量状态")
    missing_fields: list[str] = Field(default_factory=list, description="缺失字段")
    warnings: list[str] = Field(default_factory=list, description="质量警告")


class FetchMetadata(BaseModel):
    """本服务获取数据时的缓存与新鲜度元信息。"""

    cache_status: CacheStatus = Field(default="bypass", description="缓存状态")
    cache_key: str | None = Field(default=None, description="本地缓存键")
    cache_ttl_seconds: int | None = Field(default=None, description="缓存 TTL，单位秒")
    cached_at: datetime | None = Field(default=None, description="写入缓存时间")
    expires_at: datetime | None = Field(default=None, description="缓存过期时间")
    cache_path: str | None = Field(default=None, description="本地缓存文件路径")


def _merge_data_quality(
    current: DataQuality,
    *,
    missing_fields: list[str] | None = None,
    warnings: list[str] | None = None,
    status: DataQualityStatus | None = None,
) -> DataQuality:
    merged_missing = list(dict.fromkeys([*current.missing_fields, *(missing_fields or [])]))
    merged_warnings = list(dict.fromkeys([*current.warnings, *(warnings or [])]))
    inferred_status: DataQualityStatus = "ok"
    if current.status == "error" or status == "error":
        inferred_status = "error"
    elif current.status == "warning" or status == "warning" or merged_missing or merged_warnings:
        inferred_status = "warning"

    return DataQuality(
        status=inferred_status,
        missing_fields=merged_missing,
        warnings=merged_warnings,
    )


def _missing_field_names(values: dict[str, Any]) -> list[str]:
    return [key for key, value in values.items() if value is None or value == ""]


class RealtimeQuote(BaseModel):
    """标准化后的实时行情快照。"""

    symbol: str = Field(description="证券代码，例如 600519")
    secid: str = Field(description="东方财富 secid，例如 1.600519")
    name: str | None = Field(default=None, description="证券名称")
    asset_type: AssetType = Field(default="stock", description="资产类型")
    market: MarketCode = Field(default="UNKNOWN", description="交易市场")
    source: str = Field(default="eastmoney", description="数据源")
    currency: str = Field(default="CNY", description="计价货币")
    timezone: str = Field(default="Asia/Shanghai", description="交易时区")

    price: Decimal | None = Field(default=None, description="最新价")
    open: Decimal | None = Field(default=None, description="开盘价")
    high: Decimal | None = Field(default=None, description="最高价")
    low: Decimal | None = Field(default=None, description="最低价")
    previous_close: Decimal | None = Field(default=None, description="昨收价")
    change_percent: Decimal | None = Field(default=None, description="涨跌幅，单位：%")
    change_amount: Decimal | None = Field(default=None, description="涨跌额")
    amplitude: Decimal | None = Field(default=None, description="振幅，单位：%")
    turnover: Decimal | None = Field(default=None, description="换手率，单位：%")

    volume: int | None = Field(default=None, description="成交量，单位按东方财富原始返回")
    amount: Decimal | None = Field(default=None, description="成交额")
    market_cap: Decimal | None = Field(default=None, description="总市值")
    float_market_cap: Decimal | None = Field(default=None, description="流通市值")

    quote_time: datetime | None = Field(default=None, description="行情时间")
    as_of: datetime | str | None = Field(default=None, description="数据对应时间")
    fetched_at: datetime = Field(description="本服务获取时间")
    fetch: FetchMetadata = Field(default_factory=FetchMetadata, description="获取元信息")
    data_quality: DataQuality = Field(default_factory=DataQuality, description="数据质量摘要")

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if self.as_of is None:
            self.as_of = self.quote_time or self.fetched_at

        missing = _missing_field_names(
            {
                "symbol": self.symbol,
                "secid": self.secid,
                "price": self.price,
                "quote_time": self.quote_time,
                "fetched_at": self.fetched_at,
            }
        )
        self.data_quality = _merge_data_quality(self.data_quality, missing_fields=missing)
        return self


class BatchQuoteRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=100, description="股票代码或东方财富 secid")


class BatchQuoteResponse(BaseModel):
    quotes: list[RealtimeQuote]
    asset_type: AssetType = "mixed"
    source: str = "eastmoney"
    currency: str = "CNY"
    timezone: str = "Asia/Shanghai"
    as_of: datetime | str | None = None
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    fetch: FetchMetadata = Field(default_factory=FetchMetadata)
    data_quality: DataQuality = Field(default_factory=DataQuality)

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if self.as_of is None and self.quotes:
            self.as_of = self.quotes[0].as_of

        missing = [] if self.quotes else ["quotes"]
        warnings = [] if self.quotes else ["批量行情未返回任何证券数据。"]
        self.data_quality = _merge_data_quality(
            self.data_quality,
            missing_fields=missing,
            warnings=warnings,
            status="warning" if missing else None,
        )
        return self


class DataProviderInfo(BaseModel):
    id: str = Field(description="数据源或能力编号")
    name: str = Field(description="中文名称")
    category: str = Field(description="能力分类")
    status: Literal["available", "planned", "degraded"] = Field(description="当前状态")
    description: str = Field(description="能力说明")
    endpoints: list[str] = Field(default_factory=list, description="相关 API 端点")
    cache_ttl_seconds: int | None = Field(default=None, description="默认本地缓存 TTL，单位秒")
    limitations: list[str] = Field(default_factory=list, description="数据限制或注意事项")


class DataRegistryResponse(BaseModel):
    providers: list[DataProviderInfo]


class SymbolResolveResult(BaseModel):
    query: str = Field(description="原始查询")
    symbol: str = Field(description="证券代码")
    name: str | None = Field(default=None, description="证券名称")
    asset_type: AssetType = Field(default="stock", description="资产类型")
    market: MarketCode = Field(default="UNKNOWN", description="市场")
    secid: str = Field(description="东方财富 secid")
    source: str = Field(default="eastmoney", description="数据源")
    raw: dict[str, Any] = Field(default_factory=dict, description="原始字段")


class SymbolResolveResponse(BaseModel):
    results: list[SymbolResolveResult]
    asset_type: AssetType = "mixed"
    source: str = "eastmoney"
    timezone: str = "Asia/Shanghai"
    as_of: datetime | str | None = None
    fetched_at: datetime = Field(description="获取时间")
    fetch: FetchMetadata = Field(default_factory=FetchMetadata, description="获取元信息")
    data_quality: DataQuality = Field(default_factory=DataQuality)

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if self.as_of is None:
            self.as_of = self.fetched_at
        missing = [] if self.results else ["results"]
        warnings = [] if self.results else ["证券解析未返回匹配结果。"]
        self.data_quality = _merge_data_quality(
            self.data_quality,
            missing_fields=missing,
            warnings=warnings,
            status="warning" if missing else None,
        )
        return self


KlinePeriod = Literal[
    "daily",
    "weekly",
    "monthly",
    "minute1",
    "minute5",
    "minute15",
    "minute30",
    "minute60",
]
Adjustment = Literal["none", "qfq", "hfq"]


class KlineBar(BaseModel):
    date: str = Field(description="交易日期或时间")
    open: Decimal | None = None
    close: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    previous_close: Decimal | None = Field(default=None, description="前收盘价")
    volume: int | None = Field(default=None, description="成交量")
    amount: Decimal | None = Field(default=None, description="成交额")
    amplitude: Decimal | None = Field(default=None, description="振幅，单位：%")
    change_percent: Decimal | None = Field(default=None, description="涨跌幅，单位：%")
    change_amount: Decimal | None = Field(default=None, description="涨跌额")
    turnover: Decimal | None = Field(default=None, description="换手率，单位：%")
    trade_status: str | None = Field(default=None, description="交易状态，数据源原始枚举")
    is_st: bool | None = Field(default=None, description="是否 ST")
    limit_up: bool | None = Field(default=None, description="是否涨停")
    limit_down: bool | None = Field(default=None, description="是否跌停")
    metadata: dict[str, Any] = Field(default_factory=dict, description="数据源原始字段与补充信息")


class KlineResponse(BaseModel):
    symbol: str
    name: str | None = None
    secid: str
    asset_type: AssetType = "stock"
    market: MarketCode = "UNKNOWN"
    source: str = "eastmoney"
    currency: str = "CNY"
    timezone: str = "Asia/Shanghai"
    period: KlinePeriod
    adjustment: Adjustment
    bars: list[KlineBar]
    as_of: datetime | str | None = None
    fetched_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict, description="数据源响应元信息")
    fetch: FetchMetadata = Field(default_factory=FetchMetadata)
    data_quality: DataQuality = Field(default_factory=DataQuality)

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if self.as_of is None:
            self.as_of = self.bars[-1].date if self.bars else self.fetched_at

        missing = _missing_field_names(
            {
                "symbol": self.symbol,
                "secid": self.secid,
                "bars": self.bars,
                "fetched_at": self.fetched_at,
            }
        )
        warnings = [] if self.bars else ["历史 K 线未返回样本。"]
        self.data_quality = _merge_data_quality(
            self.data_quality,
            missing_fields=missing,
            warnings=warnings,
            status="warning" if missing else None,
        )
        return self


class ResearchUniverseMember(BaseModel):
    symbol: str = Field(description="规范化证券代码，例如 002156.SZ")
    code: str = Field(description="交易所原始代码，例如 002156")
    name: str | None = Field(default=None, description="证券名称")
    industry: str | None = Field(default=None, description="所属行业")
    region: str | None = Field(default=None, description="地域板块")
    concepts: list[str] = Field(default_factory=list, description="概念板块")
    sector_hint: str | None = Field(default=None, description="种子数据板块提示")
    sector_tags: list[str] = Field(default_factory=list, description="前端展示用板块标签")
    exchange: MarketCode = Field(default="UNKNOWN", description="交易所")
    asset_type: AssetType = Field(default="stock", description="资产类型")
    currency: str = Field(default="CNY", description="计价货币")
    timezone: str = Field(default="Asia/Shanghai", description="交易时区")
    secid: str | None = Field(default=None, description="东方财富 secid")
    provider: str = Field(default="eastmoney", description="主数据来源")
    security_status: str = Field(default="active", description="证券状态")
    role: str = Field(default="member", description="股票池角色")
    weight: Decimal | None = Field(default=None, description="默认权重")
    row_count: int = Field(default=0, description="已入库 K 线条数")
    first_ts: datetime | None = Field(default=None, description="最早入库时间")
    last_ts: datetime | None = Field(default=None, description="最新入库时间")
    data_provider: str | None = Field(default=None, description="当前覆盖数据来源")
    latest_close: Decimal | None = Field(default=None, description="最新收盘价")
    latest_change_pct: Decimal | None = Field(default=None, description="最近一日涨跌幅，单位：%")
    latest_amount: Decimal | None = Field(default=None, description="最近一日成交额")
    latest_turnover: Decimal | None = Field(default=None, description="最近一日换手率，单位：%")
    strength_20d_pct: Decimal | None = Field(
        default=None,
        description="近 20 个交易日涨跌幅，单位：%",
    )
    strength_60d_pct: Decimal | None = Field(
        default=None,
        description="近 60 个交易日涨跌幅，单位：%",
    )
    ma20: Decimal | None = Field(default=None, description="最近 20 日均线")
    ma60: Decimal | None = Field(default=None, description="最近 60 日均线")
    trend_status: Literal["bullish", "bearish", "sideways", "insufficient"] = Field(
        default="insufficient",
        description="基于收盘价、MA20 和 MA60 推导的趋势状态",
    )
    avg_amount_20d: Decimal | None = Field(default=None, description="近 20 日平均成交额")
    avg_volume_20d: Decimal | None = Field(default=None, description="近 20 日平均成交量")
    avg_turnover_20d: Decimal | None = Field(default=None, description="近 20 日平均换手率")
    trade_status: str | None = Field(default=None, description="最近一日交易状态")
    is_st: bool | None = Field(default=None, description="最近一日是否 ST")
    limit_up: bool | None = Field(default=None, description="最近一日是否涨停")
    limit_down: bool | None = Field(default=None, description="最近一日是否跌停")
    pe_ttm: Decimal | None = Field(default=None, description="TTM 市盈率")
    pb_mrq: Decimal | None = Field(default=None, description="市净率 MRQ")
    ps_ttm: Decimal | None = Field(default=None, description="TTM 市销率")
    pcf_ncf_ttm: Decimal | None = Field(default=None, description="TTM 市现率")
    data_status: Literal["ready", "missing", "stale"] = Field(
        default="missing",
        description="本地数据状态",
    )


class ResearchUniverse(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: str = "active"
    source: str = "manual"
    tags: list[str] = Field(default_factory=list)
    default_timeframe: KlinePeriod = "daily"
    default_adjustment: Adjustment = "qfq"
    provider: str = "eastmoney"
    members: list[ResearchUniverseMember] = Field(default_factory=list)
    member_count: int = Field(default=0, description="股票池成员总数")
    stock_count: int = Field(default=0, description="股票成员数量")
    etf_count: int = Field(default=0, description="ETF 成员数量")
    index_count: int = Field(default=0, description="指数成员数量")
    fund_count: int = Field(default=0, description="基金成员数量")
    ready_count: int = Field(default=0, description="已完成行情覆盖的成员数量")
    bar_count: int = Field(default=0, description="已入库 K 线样本总数")
    latest_ts: datetime | None = Field(default=None, description="股票池内最新行情日期")
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ResearchUniverseSummary(BaseModel):
    id: str
    name: str
    description: str | None = None
    status: str = "active"
    source: str = "manual"
    tags: list[str] = Field(default_factory=list)
    default_timeframe: KlinePeriod = "daily"
    default_adjustment: Adjustment = "qfq"
    provider: str = "eastmoney"
    member_count: int = 0
    stock_count: int = 0
    etf_count: int = 0
    index_count: int = 0
    fund_count: int = 0
    ready_count: int = 0
    bar_count: int = 0
    latest_ts: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ResearchUniverseResponse(BaseModel):
    universes: list[ResearchUniverse]
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data_quality: DataQuality = Field(default_factory=DataQuality)

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if not self.universes:
            self.data_quality = _merge_data_quality(
                self.data_quality,
                missing_fields=["universes"],
                warnings=["数据库中尚未配置策略研究股票池。"],
                status="warning",
            )
        return self


class ResearchUniverseSummaryResponse(BaseModel):
    universes: list[ResearchUniverseSummary]
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data_quality: DataQuality = Field(default_factory=DataQuality)

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if not self.universes:
            self.data_quality = _merge_data_quality(
                self.data_quality,
                missing_fields=["universes"],
                warnings=["数据库中尚未配置策略研究股票池。"],
                status="warning",
            )
        return self


class ResearchUniverseMembersPageResponse(BaseModel):
    universe_id: str
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total: int = 0
    total_pages: int = 1
    keyword: str | None = None
    members: list[ResearchUniverseMember] = Field(default_factory=list)
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ResearchUniverseMemberCreateRequest(BaseModel):
    query: str = Field(min_length=1, max_length=80, description="股票代码、简称或中文名称")
    role: str = Field(default="member", max_length=40, description="股票池角色")
    weight: Decimal | None = Field(default=None, ge=0, le=1, description="默认权重")


class ResearchUniverseMemberCreateResponse(BaseModel):
    universe_id: str
    member: ResearchUniverseMember
    candidates: list[SymbolResolveResult] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class AShareUniverseBatchImportRequest(BaseModel):
    universe_id: str = Field(
        default="a-share-sample-research-pool",
        description="目标股票池 ID。",
    )
    page: int = Field(default=1, ge=1, description="东方财富沪深京 A 股列表页码。")
    page_size: int = Field(default=100, ge=1, le=100, description="每批导入证券数量。")
    role: str = Field(default="member", max_length=40, description="股票池成员角色。")


class AShareUniverseBatchImportResponse(BaseModel):
    universe_id: str
    page: int
    page_size: int
    total_available: int
    total_pages: int
    next_page: int | None = None
    imported_count: int
    members: list[ResearchUniverseMember] = Field(default_factory=list)
    source: str = "eastmoney"
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ETFUniverseBatchImportRequest(AShareUniverseBatchImportRequest):
    universe_id: str = Field(
        default="etf-index-pool",
        description="目标 ETF/指数池 ID。",
    )
    page: int = Field(default=1, ge=1, description="东方财富 ETF 列表页码。")
    page_size: int = Field(default=100, ge=1, le=100, description="每批导入 ETF 数量。")


class ETFUniverseBatchImportResponse(AShareUniverseBatchImportResponse):
    pass


class MarketDataCoverageItem(BaseModel):
    symbol: str
    name: str | None = None
    timeframe: KlinePeriod | str = "daily"
    adjustment: Adjustment | str = "qfq"
    provider: str = "eastmoney"
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    row_count: int = 0
    data_status: Literal["ready", "missing", "stale"] = "missing"


class MarketDataCoverageResponse(BaseModel):
    universe_id: str | None = None
    items: list[MarketDataCoverageItem]
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data_quality: DataQuality = Field(default_factory=DataQuality)

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if not self.items:
            self.data_quality = _merge_data_quality(
                self.data_quality,
                missing_fields=["items"],
                warnings=["未查询到任何本地行情覆盖数据。"],
                status="warning",
            )
        return self


class LocalKlineBar(BaseModel):
    ts: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    previous_close: Decimal | None = None
    volume: Decimal
    amount: Decimal | None = None
    amplitude: Decimal | None = None
    change_percent: Decimal | None = None
    change_amount: Decimal | None = None
    turnover: Decimal | None = None
    trade_status: str | None = None
    is_st: bool | None = None
    limit_up: bool | None = None
    limit_down: bool | None = None
    provider: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class LocalKlineSummary(BaseModel):
    row_count: int = 0
    first_ts: datetime | None = None
    last_ts: datetime | None = None
    latest_close: Decimal | None = None
    previous_close: Decimal | None = None
    return_pct: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    total_volume: Decimal | None = None
    total_amount: Decimal | None = None


class LocalKlineResponse(BaseModel):
    symbol: str
    code: str | None = None
    name: str | None = None
    exchange: MarketCode = "UNKNOWN"
    asset_type: AssetType = "stock"
    currency: str = "CNY"
    timezone: str = "Asia/Shanghai"
    secid: str | None = None
    provider: str | None = None
    timeframe: KlinePeriod | str = "daily"
    adjustment: Adjustment | str = "qfq"
    bars: list[LocalKlineBar]
    summary: LocalKlineSummary
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data_quality: DataQuality = Field(default_factory=DataQuality)

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if not self.bars:
            self.data_quality = _merge_data_quality(
                self.data_quality,
                missing_fields=["bars"],
                warnings=["本地数据库未查询到该证券的 K 线。"],
                status="warning",
            )
        return self


class HistoryIngestionRequest(BaseModel):
    universe_id: str | None = Field(
        default="a-share-sample-research-pool",
        description="股票池 ID；为空时仅使用 symbols。",
    )
    symbols: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="股票代码、东方财富 secid 或规范化代码。",
    )
    period: KlinePeriod = Field(default="daily", description="K 线周期")
    adjustment: Adjustment = Field(default="qfq", description="复权方式")
    limit: int = Field(default=1260, ge=1, le=20000, description="每只证券最多拉取条数")
    lookback_years: int = Field(default=5, ge=1, le=30, description="本地保留的最近年份数")
    end: str = Field(default="20500101", description="东方财富 end 参数，默认远期代表取最新")
    allow_fallback: bool = Field(
        default=False,
        description="东方财富不可用时是否允许降级到腾讯 K 线；严格东方财富同步默认关闭。",
    )
    request_delay_seconds: float = Field(
        default=2.0,
        ge=0,
        le=60,
        description="每次东方财富 K 线请求之间的最小等待时间，降低被限流概率。",
    )
    max_retries: int = Field(
        default=3,
        ge=1,
        le=10,
        description="每段 K 线请求失败后的低频重试次数。",
    )


class HistoryBatchIngestionRequest(HistoryIngestionRequest):
    batch_size: int = Field(default=25, ge=1, le=200, description="单批最多处理标的数。")
    offset: int = Field(default=0, ge=0, description="从股票池成员列表的第几个标的开始。")


class RealtimeSnapshotIngestionRequest(BaseModel):
    universe_id: str | None = Field(
        default="a-share-sample-research-pool",
        description="股票池 ID；为空时仅使用 symbols。",
    )
    symbols: list[str] | None = Field(
        default=None,
        min_length=1,
        max_length=100,
        description="股票代码、东方财富 secid 或规范化代码。",
    )
    trade_date: str | None = Field(
        default=None,
        description="写入的交易日，YYYY-MM-DD；为空时使用行情 quote_time 对应的上海日期。",
    )
    adjustment: Adjustment = Field(default="qfq", description="写入复权口径，默认 qfq")
    batch_size: int = Field(default=100, ge=1, le=200, description="单批最多处理标的数。")
    offset: int = Field(default=0, ge=0, description="从股票池成员列表的第几个标的开始。")
    request_delay_seconds: float = Field(
        default=0.2,
        ge=0,
        le=60,
        description="批量实时行情请求后的等待时间，降低被限流概率。",
    )


class DividendEvent(BaseModel):
    symbol: str
    name: str | None = None
    report_date: datetime | None = None
    plan_notice_date: datetime | None = None
    equity_record_date: datetime | None = None
    ex_dividend_date: datetime | None = None
    notice_date: datetime | None = None
    assign_progress: str | None = None
    plan_profile: str | None = None
    pretax_bonus_rmb: Decimal | None = None
    bonus_ratio: Decimal | None = None
    transfer_ratio: Decimal | None = None
    dividend_yield: Decimal | None = None


class DividendEventsResponse(BaseModel):
    symbol: str
    events: list[DividendEvent]
    source: str = "eastmoney"
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    data_quality: DataQuality = Field(default_factory=DataQuality)

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if not self.events:
            self.data_quality = _merge_data_quality(
                self.data_quality,
                missing_fields=["events"],
                warnings=["未查询到该证券的分红送配事件。"],
                status="warning",
            )
        return self


class HistoryIngestionSymbolResult(BaseModel):
    symbol: str
    name: str | None = None
    secid: str | None = None
    source: str | None = None
    status: Literal["success", "failed", "skipped"]
    bars_received: int = 0
    rows_upserted: int = 0
    first_date: str | None = None
    last_date: str | None = None
    error: str | None = None


class HistoryIngestionResponse(BaseModel):
    job_id: str
    status: Literal["completed", "partial", "failed"]
    provider: str = "eastmoney"
    universe_id: str | None = None
    period: KlinePeriod = "daily"
    adjustment: Adjustment = "qfq"
    lookback_years: int = 5
    total_symbols: int
    completed_symbols: int
    failed_symbols: int
    rows_received: int
    rows_upserted: int
    symbols: list[HistoryIngestionSymbolResult]
    batch_offset: int | None = None
    batch_size: int | None = None
    next_offset: int | None = None
    universe_total_symbols: int | None = None
    started_at: datetime
    completed_at: datetime
    data_quality: DataQuality = Field(default_factory=DataQuality)

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if self.failed_symbols:
            self.data_quality = _merge_data_quality(
                self.data_quality,
                warnings=[f"{self.failed_symbols} 个标的入库失败，请查看 symbols[].error。"],
                status="warning" if self.completed_symbols else "error",
            )
        return self


class IngestionJobSummary(BaseModel):
    id: str
    universe_id: str | None = None
    provider: str
    timeframe: str
    adjustment: str
    status: str
    total_symbols: int = 0
    completed_symbols: int = 0
    failed_symbols: int = 0
    rows_received: int = 0
    rows_upserted: int = 0
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class IngestionJobsResponse(BaseModel):
    jobs: list[IngestionJobSummary]
    fetched_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class TechnicalIndicatorPoint(BaseModel):
    date: str = Field(description="交易日期或时间")
    close: Decimal | None = None
    volume: int | None = None
    ma5: Decimal | None = None
    ma10: Decimal | None = None
    ma20: Decimal | None = None
    return_pct: Decimal | None = Field(default=None, description="相对上一根 K 线收益率，单位：%")
    drawdown_pct: Decimal | None = Field(
        default=None,
        description="相对历史最高收盘价回撤，单位：%",
    )


class TechnicalIndicatorSummary(BaseModel):
    latest_close: Decimal | None = None
    period_return_pct: Decimal | None = None
    max_drawdown_pct: Decimal | None = None
    volatility_annualized_pct: Decimal | None = None
    avg_volume20: Decimal | None = None
    ma5: Decimal | None = None
    ma10: Decimal | None = None
    ma20: Decimal | None = None


class TechnicalIndicatorsResponse(BaseModel):
    symbol: str
    name: str | None = None
    secid: str
    asset_type: AssetType = "stock"
    market: MarketCode = "UNKNOWN"
    source: str = "eastmoney"
    currency: str = "CNY"
    timezone: str = "Asia/Shanghai"
    period: KlinePeriod
    adjustment: Adjustment
    points: list[TechnicalIndicatorPoint]
    summary: TechnicalIndicatorSummary
    as_of: datetime | str | None = None
    fetched_at: datetime
    fetch: FetchMetadata = Field(default_factory=FetchMetadata)
    data_quality: DataQuality = Field(default_factory=DataQuality)

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if self.as_of is None:
            self.as_of = self.points[-1].date if self.points else self.fetched_at

        missing = [] if self.points else ["points"]
        warnings = (
            []
            if len(self.points) >= 20
            else ["技术指标样本少于 20 条，MA20 或波动率解释需谨慎。"]
        )
        self.data_quality = _merge_data_quality(
            self.data_quality,
            missing_fields=missing,
            warnings=warnings,
            status="warning" if missing or warnings else None,
        )
        return self


class FinancialReportItem(BaseModel):
    symbol: str
    name: str | None = None
    secucode: str | None = None
    report_date: datetime | None = None
    data_type: str | None = None
    basic_eps: Decimal | None = None
    revenue: Decimal | None = Field(default=None, description="营业收入")
    parent_net_profit: Decimal | None = Field(default=None, description="归母净利润")
    weighted_roe: Decimal | None = Field(default=None, description="加权 ROE")
    gross_margin: Decimal | None = Field(default=None, description="销售毛利率")
    revenue_yoy: Decimal | None = Field(default=None, description="营业收入同比")
    net_profit_yoy: Decimal | None = Field(default=None, description="净利润同比")
    notice_date: datetime | None = None
    source: str = "eastmoney"
    raw: dict[str, Any] = Field(default_factory=dict)


class FinancialReportsResponse(BaseModel):
    symbol: str
    asset_type: AssetType = "stock"
    source: str = "eastmoney"
    currency: str = "CNY"
    timezone: str = "Asia/Shanghai"
    reports: list[FinancialReportItem]
    as_of: datetime | str | None = None
    fetched_at: datetime
    fetch: FetchMetadata = Field(default_factory=FetchMetadata)
    data_quality: DataQuality = Field(default_factory=DataQuality)

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if self.as_of is None:
            self.as_of = self.reports[0].report_date if self.reports else self.fetched_at

        missing = [] if self.reports else ["reports"]
        warnings = [] if self.reports else ["财务摘要未返回报告期数据。"]
        self.data_quality = _merge_data_quality(
            self.data_quality,
            missing_fields=missing,
            warnings=warnings,
            status="warning" if missing else None,
        )
        return self


class FundamentalIndicatorPoint(BaseModel):
    report_date: datetime | None = None
    data_type: str | None = None
    revenue: Decimal | None = None
    parent_net_profit: Decimal | None = None
    revenue_yoy: Decimal | None = None
    net_profit_yoy: Decimal | None = None
    gross_margin: Decimal | None = None
    weighted_roe: Decimal | None = None
    net_margin: Decimal | None = Field(default=None, description="归母净利率，单位：%")


class FundamentalIndicatorSummary(BaseModel):
    latest_report_date: datetime | None = None
    latest_revenue: Decimal | None = None
    latest_parent_net_profit: Decimal | None = None
    latest_revenue_yoy: Decimal | None = None
    latest_net_profit_yoy: Decimal | None = None
    latest_gross_margin: Decimal | None = None
    latest_weighted_roe: Decimal | None = None
    latest_net_margin: Decimal | None = None
    avg_roe: Decimal | None = None
    avg_gross_margin: Decimal | None = None
    avg_net_margin: Decimal | None = None
    report_count: int = 0


class FundamentalIndicatorsResponse(BaseModel):
    symbol: str
    asset_type: AssetType = "stock"
    source: str = "eastmoney"
    currency: str = "CNY"
    timezone: str = "Asia/Shanghai"
    points: list[FundamentalIndicatorPoint]
    summary: FundamentalIndicatorSummary
    as_of: datetime | str | None = None
    fetched_at: datetime
    fetch: FetchMetadata = Field(default_factory=FetchMetadata)
    data_quality: DataQuality = Field(default_factory=DataQuality)

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if self.as_of is None:
            self.as_of = self.points[0].report_date if self.points else self.fetched_at

        missing = [] if self.points else ["points"]
        warnings = [] if len(self.points) >= 4 else ["财务指标样本少于 4 期，趋势解释需谨慎。"]
        self.data_quality = _merge_data_quality(
            self.data_quality,
            missing_fields=missing,
            warnings=warnings,
            status="warning" if missing or warnings else None,
        )
        return self


class AnnouncementItem(BaseModel):
    art_code: str
    title: str
    symbol: str | None = None
    name: str | None = None
    notice_date: datetime | None = None
    display_time: datetime | None = None
    columns: list[str] = Field(default_factory=list)
    url: str | None = Field(default=None, description="公告详情 URL")
    pdf_url: str | None = Field(default=None, description="公告 PDF URL")
    source: str = "eastmoney"
    raw: dict[str, Any] = Field(default_factory=dict)


class AnnouncementResponse(BaseModel):
    symbol: str
    asset_type: AssetType = "stock"
    source: str = "eastmoney"
    timezone: str = "Asia/Shanghai"
    announcements: list[AnnouncementItem]
    as_of: datetime | str | None = None
    fetched_at: datetime
    fetch: FetchMetadata = Field(default_factory=FetchMetadata)
    data_quality: DataQuality = Field(default_factory=DataQuality)

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if self.as_of is None:
            first = self.announcements[0] if self.announcements else None
            self.as_of = first.notice_date or first.display_time if first else self.fetched_at

        missing = [] if self.announcements else ["announcements"]
        warnings = [] if self.announcements else ["公告接口未返回近期公告。"]
        self.data_quality = _merge_data_quality(
            self.data_quality,
            missing_fields=missing,
            warnings=warnings,
            status="warning" if missing else None,
        )
        return self


StrategySide = Literal["long", "flat"]


class BacktestEquityPoint(BaseModel):
    date: str = Field(description="交易日期")
    close: Decimal | None = Field(default=None, description="收盘价")
    fast_ma: Decimal | None = Field(default=None, description="快线均线")
    slow_ma: Decimal | None = Field(default=None, description="慢线均线")
    position: int = Field(default=0, description="持仓状态，1 为持有，0 为空仓")
    daily_return_pct: Decimal | None = Field(default=None, description="当日标的收益率，单位：%")
    strategy_return_pct: Decimal | None = Field(default=None, description="当日策略收益率，单位：%")
    equity: Decimal = Field(description="策略净值")
    drawdown_pct: Decimal | None = Field(default=None, description="策略净值回撤，单位：%")


class BacktestTrade(BaseModel):
    entry_date: str
    entry_price: Decimal
    exit_date: str | None = None
    exit_price: Decimal | None = None
    return_pct: Decimal | None = Field(default=None, description="单笔交易收益率，单位：%")
    holding_days: int = 0
    status: Literal["open", "closed"] = "open"


class BacktestSummary(BaseModel):
    start_date: str | None = None
    end_date: str | None = None
    sample_count: int = 0
    initial_cash: Decimal
    final_equity: Decimal
    total_return_pct: Decimal | None = None
    benchmark_return_pct: Decimal | None = None
    excess_return_pct: Decimal | None = None
    max_drawdown_pct: Decimal | None = None
    annualized_return_pct: Decimal | None = None
    volatility_annualized_pct: Decimal | None = None
    sharpe: Decimal | None = None
    trade_count: int = 0
    win_rate_pct: Decimal | None = None
    exposure_pct: Decimal | None = None


class BacktestResponse(BaseModel):
    symbol: str
    name: str | None = None
    secid: str
    asset_type: AssetType = "stock"
    market: MarketCode = "UNKNOWN"
    source: str = "eastmoney"
    currency: str = "CNY"
    timezone: str = "Asia/Shanghai"
    strategy_id: str = "ma_crossover"
    strategy_name: str = "均线突破"
    fast_window: int
    slow_window: int
    fee_bps: Decimal
    parameters: dict[str, Any] = Field(default_factory=dict, description="策略参数快照")
    period: KlinePeriod
    adjustment: Adjustment
    side: StrategySide = "long"
    equity_curve: list[BacktestEquityPoint]
    trades: list[BacktestTrade]
    summary: BacktestSummary
    as_of: datetime | str | None = None
    fetched_at: datetime
    fetch: FetchMetadata = Field(default_factory=FetchMetadata)
    data_quality: DataQuality = Field(default_factory=DataQuality)

    @model_validator(mode="after")
    def fill_contract_fields(self) -> Self:
        if self.as_of is None:
            self.as_of = self.equity_curve[-1].date if self.equity_curve else self.fetched_at

        missing = [] if self.equity_curve else ["equity_curve"]
        warnings: list[str] = []
        if len(self.equity_curve) < self.slow_window + 5:
            warnings.append("回测样本偏少，均线策略指标解释需谨慎。")
        if not self.trades:
            warnings.append("样本区间内未产生完整交易。")
        self.data_quality = _merge_data_quality(
            self.data_quality,
            missing_fields=missing,
            warnings=warnings,
            status="warning" if missing or warnings else None,
        )
        return self
