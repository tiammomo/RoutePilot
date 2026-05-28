from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol

from quantpilot_market_data.models import Adjustment, KlinePeriod, KlineResponse

ProviderStatus = Literal["available", "degraded", "planned"]
ProviderMarket = Literal["a-share", "hk", "us", "global", "mixed", "index-etf"]


@dataclass(frozen=True)
class ProviderCapability:
    """Provider metadata used by routers and the data-platform registry."""

    status: ProviderStatus
    markets: tuple[ProviderMarket, ...]
    supports_realtime: bool = False
    supports_history_kline: bool = False
    supports_events: bool = False
    supports_fundamentals: bool = False
    requires_key: bool = False
    notes: tuple[str, ...] = field(default_factory=tuple)


class MarketDataProvider(Protocol):
    """Common metadata contract for market data providers."""

    id: str
    name: str
    capability: ProviderCapability


class HistoricalKlineProvider(MarketDataProvider, Protocol):
    """Provider contract for historical OHLCV/K-line data."""

    async def get_kline(
        self,
        symbol_or_secid: str,
        *,
        period: KlinePeriod = "daily",
        adjustment: Adjustment = "qfq",
        limit: int = 120,
        end: str = "20500101",
        allow_fallback: bool = True,
    ) -> KlineResponse: ...
