from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

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
