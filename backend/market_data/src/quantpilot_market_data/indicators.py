from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from math import sqrt

from quantpilot_market_data.models import (
    KlineResponse,
    TechnicalIndicatorPoint,
    TechnicalIndicatorsResponse,
    TechnicalIndicatorSummary,
)


def _round(value: Decimal | None, places: int = 4) -> Decimal | None:
    if value is None:
        return None
    quant = Decimal("1").scaleb(-places)
    return value.quantize(quant, rounding=ROUND_HALF_UP)


def _mean(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal("0")) / Decimal(len(values))


def _rolling_mean(closes: list[Decimal | None], end_index: int, window: int) -> Decimal | None:
    if end_index + 1 < window:
        return None
    window_values = closes[end_index + 1 - window : end_index + 1]
    if any(value is None for value in window_values):
        return None
    return _mean([value for value in window_values if value is not None])


def _return_pct(current: Decimal | None, previous: Decimal | None) -> Decimal | None:
    if current is None or previous is None or previous == 0:
        return None
    return ((current - previous) / previous) * Decimal("100")


def _drawdown_pct(close: Decimal | None, peak: Decimal | None) -> Decimal | None:
    if close is None or peak is None or peak == 0:
        return None
    return ((close - peak) / peak) * Decimal("100")


def _annualized_volatility_pct(returns: list[Decimal]) -> Decimal | None:
    if len(returns) < 2:
        return None
    mean_return = _mean(returns)
    if mean_return is None:
        return None
    variance = sum((value - mean_return) ** 2 for value in returns) / Decimal(len(returns))
    return Decimal(str(sqrt(float(variance)))) * Decimal(str(sqrt(252)))


def build_technical_indicators(kline: KlineResponse) -> TechnicalIndicatorsResponse:
    closes = [bar.close for bar in kline.bars]
    points: list[TechnicalIndicatorPoint] = []
    peak_close: Decimal | None = None
    returns: list[Decimal] = []

    for index, bar in enumerate(kline.bars):
        if bar.close is not None:
            peak_close = bar.close if peak_close is None else max(peak_close, bar.close)

        return_value = _return_pct(bar.close, closes[index - 1] if index > 0 else None)
        if return_value is not None:
            returns.append(return_value)

        points.append(
            TechnicalIndicatorPoint(
                date=bar.date,
                close=bar.close,
                volume=bar.volume,
                ma5=_round(_rolling_mean(closes, index, 5), 4),
                ma10=_round(_rolling_mean(closes, index, 10), 4),
                ma20=_round(_rolling_mean(closes, index, 20), 4),
                return_pct=_round(return_value, 4),
                drawdown_pct=_round(_drawdown_pct(bar.close, peak_close), 4),
            )
        )

    valid_closes = [close for close in closes if close is not None]
    volumes = [Decimal(bar.volume) for bar in kline.bars[-20:] if bar.volume is not None]
    first_close = valid_closes[0] if valid_closes else None
    latest_close = valid_closes[-1] if valid_closes else None
    drawdowns = [point.drawdown_pct for point in points if point.drawdown_pct is not None]

    summary = TechnicalIndicatorSummary(
        latest_close=latest_close,
        period_return_pct=_round(_return_pct(latest_close, first_close), 4),
        max_drawdown_pct=min(drawdowns) if drawdowns else None,
        volatility_annualized_pct=_round(_annualized_volatility_pct(returns), 4),
        avg_volume20=_round(_mean(volumes), 2),
        ma5=points[-1].ma5 if points else None,
        ma10=points[-1].ma10 if points else None,
        ma20=points[-1].ma20 if points else None,
    )

    return TechnicalIndicatorsResponse(
        symbol=kline.symbol,
        name=kline.name,
        secid=kline.secid,
        asset_type=kline.asset_type,
        market=kline.market,
        source=kline.source,
        period=kline.period,
        adjustment=kline.adjustment,
        points=points,
        summary=summary,
        as_of=kline.as_of,
        fetched_at=kline.fetched_at,
    )
