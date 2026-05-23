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
    volume: int | None = Field(default=None, description="成交量")
    amount: Decimal | None = Field(default=None, description="成交额")
    amplitude: Decimal | None = Field(default=None, description="振幅，单位：%")
    change_percent: Decimal | None = Field(default=None, description="涨跌幅，单位：%")
    change_amount: Decimal | None = Field(default=None, description="涨跌额")
    turnover: Decimal | None = Field(default=None, description="换手率，单位：%")


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
