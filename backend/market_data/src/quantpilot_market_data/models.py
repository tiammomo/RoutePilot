from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Literal

from pydantic import BaseModel, Field

MarketCode = Literal["SH", "SZ", "BJ", "UNKNOWN"]


class RealtimeQuote(BaseModel):
    """标准化后的实时行情快照。"""

    symbol: str = Field(description="证券代码，例如 600519")
    secid: str = Field(description="东方财富 secid，例如 1.600519")
    name: str | None = Field(default=None, description="证券名称")
    market: MarketCode = Field(default="UNKNOWN", description="交易市场")
    source: str = Field(default="eastmoney", description="数据源")

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
    fetched_at: datetime = Field(description="本服务获取时间")


class BatchQuoteRequest(BaseModel):
    symbols: list[str] = Field(min_length=1, max_length=100, description="股票代码或东方财富 secid")


class BatchQuoteResponse(BaseModel):
    quotes: list[RealtimeQuote]


class DataProviderInfo(BaseModel):
    id: str = Field(description="数据源或能力编号")
    name: str = Field(description="中文名称")
    category: str = Field(description="能力分类")
    status: Literal["available", "planned", "degraded"] = Field(description="当前状态")
    description: str = Field(description="能力说明")
    endpoints: list[str] = Field(default_factory=list, description="相关 API 端点")


class DataRegistryResponse(BaseModel):
    providers: list[DataProviderInfo]


class SymbolResolveResult(BaseModel):
    query: str = Field(description="原始查询")
    symbol: str = Field(description="证券代码")
    name: str | None = Field(default=None, description="证券名称")
    market: MarketCode = Field(default="UNKNOWN", description="市场")
    secid: str = Field(description="东方财富 secid")
    source: str = Field(default="eastmoney", description="数据源")
    raw: dict[str, Any] = Field(default_factory=dict, description="原始字段")


class SymbolResolveResponse(BaseModel):
    results: list[SymbolResolveResult]
    fetched_at: datetime = Field(description="获取时间")


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
    market: MarketCode = "UNKNOWN"
    source: str = "eastmoney"
    period: KlinePeriod
    adjustment: Adjustment
    bars: list[KlineBar]
    fetched_at: datetime


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
    reports: list[FinancialReportItem]
    fetched_at: datetime


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
    announcements: list[AnnouncementItem]
    fetched_at: datetime
