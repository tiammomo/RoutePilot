from __future__ import annotations

import os
from datetime import UTC, date, datetime, time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from quantpilot_market_data.models import (
    HistoryIngestionResponse,
    KlineResponse,
    LocalKlineBar,
    LocalKlineResponse,
    LocalKlineSummary,
    MarketDataCoverageItem,
    ResearchUniverse,
    ResearchUniverseMember,
    SymbolResolveResult,
)

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_UNIVERSE_ID = "a-share-sample-research-pool"
ROOT_DIR = Path(__file__).resolve().parents[4]


class DatabaseError(RuntimeError):
    """数据库不可用或量化表结构未初始化。"""


def load_local_env_if_needed() -> None:
    if os.getenv("DATABASE_URL"):
        return
    for env_file in (ROOT_DIR / ".env", ROOT_DIR / ".env.local"):
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                os.environ.setdefault(key, value)


def database_url_from_env() -> str:
    load_local_env_if_needed()
    url = os.getenv("DATABASE_URL", "").strip()
    if not url:
        raise DatabaseError("DATABASE_URL 未配置，无法写入本地 TimescaleDB。")
    if not (url.startswith("postgresql://") or url.startswith("postgres://")):
        raise DatabaseError("DATABASE_URL 必须指向 PostgreSQL/TimescaleDB。")
    parsed = urlsplit(url)
    query = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if key != "schema"
    ]
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


async def connect() -> psycopg.AsyncConnection:
    try:
        return await psycopg.AsyncConnection.connect(database_url_from_env())
    except psycopg.OperationalError as error:
        raise DatabaseError(f"无法连接 TimescaleDB：{error}") from error


def normalize_fetch_symbol(symbol: str) -> str:
    value = symbol.strip()
    upper = value.upper()
    if len(upper) == 9 and upper[:6].isdigit() and upper[6] == "." and upper[7:] in {
        "SH",
        "SZ",
        "BJ",
    }:
        return upper[:6]
    return value


def canonical_symbol(code: str, market: str | None) -> str:
    clean_code = code.strip().upper()
    if len(clean_code) == 9 and clean_code[:6].isdigit() and clean_code[6] == ".":
        return clean_code
    if market in {"SH", "SZ", "BJ"} and clean_code.isdigit():
        return f"{clean_code}.{market}"
    return clean_code


def parse_bar_datetime(value: str) -> datetime:
    raw = value.strip()
    if not raw:
        raise ValueError("K 线日期为空")
    if len(raw) == 10:
        parsed_date = date.fromisoformat(raw)
        return datetime.combine(parsed_date, time.min, tzinfo=SHANGHAI_TZ).astimezone(UTC)
    normalized = raw.replace(" ", "T")
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=SHANGHAI_TZ)
    return parsed.astimezone(UTC)


def lookback_cutoff_datetime(years: int | None) -> datetime | None:
    if years is None or years <= 0:
        return None
    today = datetime.now(SHANGHAI_TZ).date()
    try:
        cutoff_date = today.replace(year=today.year - years)
    except ValueError:
        cutoff_date = today.replace(year=today.year - years, day=28)
    return datetime.combine(cutoff_date, time.min, tzinfo=SHANGHAI_TZ).astimezone(UTC)


def decimal_or_zero(value: Decimal | int | None) -> Decimal:
    if value is None:
        return Decimal("0")
    return value if isinstance(value, Decimal) else Decimal(str(value))


def decimal_or_none(value: Decimal | int | None) -> Decimal | None:
    if value is None:
        return None
    return value if isinstance(value, Decimal) else Decimal(str(value))


def decimal_from_json(value: Any) -> Decimal | None:
    if value in (None, "", "-"):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def json_array(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def coverage_status(row_count: int | None, last_ts: datetime | None) -> str:
    if not row_count:
        return "missing"
    if last_ts is None:
        return "missing"
    return "ready"


async def get_universe_fetch_targets(universe_id: str) -> list[dict[str, str]]:
    async with await connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(
            """
                SELECT securities.symbol, securities.code, securities.secid
                FROM quant.security_universe_members members
                JOIN quant.securities securities
                  ON securities.symbol = members.symbol
                WHERE members.universe_id = %s
                ORDER BY members.metadata->>'order', securities.symbol
                """,
            (universe_id,),
        )
        rows = await cursor.fetchall()
    return [
        {
            "symbol": str(row["symbol"]),
            "query": str(row["secid"] or row["code"] or row["symbol"]),
        }
        for row in rows
    ]


async def list_research_universes() -> list[ResearchUniverse]:
    async with await connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(
            """
                SELECT
                  universes.id,
                  universes.name,
                  universes.description,
                  universes.status,
                  universes.source,
                  universes.tags,
                  universes.metadata AS universe_metadata,
                  universes.created_at,
                  universes.updated_at,
                  securities.symbol,
                  securities.code,
                  securities.name AS security_name,
                  securities.exchange,
                  securities.asset_type,
                  securities.currency,
                  securities.timezone,
                  securities.secid,
                  securities.provider,
                  securities.status AS security_status,
                  members.role,
                  members.weight,
                  sync_state.first_ts,
                  sync_state.last_ts,
                  sync_state.provider AS data_provider,
                  COALESCE(sync_state.row_count, 0) AS row_count
                FROM quant.security_universes universes
                LEFT JOIN quant.security_universe_members members
                  ON members.universe_id = universes.id
                LEFT JOIN quant.securities securities
                  ON securities.symbol = members.symbol
                LEFT JOIN LATERAL (
                  SELECT sync_row.*
                  FROM quant.market_data_sync_state sync_row
                  WHERE sync_row.symbol = securities.symbol
                    AND sync_row.timeframe = COALESCE(
                      universes.metadata->>'default_timeframe',
                      'daily'
                    )
                    AND sync_row.adjustment = COALESCE(
                      universes.metadata->>'default_adjustment',
                      'qfq'
                    )
                  ORDER BY (
                    sync_row.provider = COALESCE(universes.metadata->>'provider', 'eastmoney')
                  ) DESC, sync_row.last_ts DESC NULLS LAST
                  LIMIT 1
                ) sync_state ON TRUE
                ORDER BY universes.created_at, members.metadata->>'order', securities.symbol
                """,
        )
        rows = await cursor.fetchall()

    universes: dict[str, ResearchUniverse] = {}
    for row in rows:
        universe_id = str(row["id"])
        metadata = json_object(row["universe_metadata"])
        if universe_id not in universes:
            universes[universe_id] = ResearchUniverse(
                id=universe_id,
                name=str(row["name"]),
                description=row["description"],
                status=str(row["status"]),
                source=str(row["source"]),
                tags=json_array(row["tags"]),
                default_timeframe=metadata.get("default_timeframe") or "daily",
                default_adjustment=metadata.get("default_adjustment") or "qfq",
                provider=metadata.get("provider") or "eastmoney",
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        if row["symbol"]:
            row_count = int(row["row_count"] or 0)
            universes[universe_id].members.append(
                ResearchUniverseMember(
                    symbol=str(row["symbol"]),
                    code=str(row["code"]),
                    name=row["security_name"],
                    exchange=row["exchange"],
                    asset_type=row["asset_type"],
                    currency=row["currency"],
                    timezone=row["timezone"],
                    secid=row["secid"],
                    provider=str(row["provider"] or "eastmoney"),
                    security_status=str(row["security_status"] or "active"),
                    role=str(row["role"] or "member"),
                    weight=decimal_or_none(row["weight"]),
                    row_count=row_count,
                    first_ts=row["first_ts"],
                    last_ts=row["last_ts"],
                    data_provider=row["data_provider"],
                    data_status=coverage_status(row_count, row["last_ts"]),
                )
            )
    return list(universes.values())


async def add_security_to_universe(
    *,
    universe_id: str,
    security: SymbolResolveResult,
    role: str = "member",
    weight: Decimal | None = None,
) -> ResearchUniverseMember:
    symbol = canonical_symbol(security.symbol, security.market)
    metadata = {
        "query": security.query,
        "raw": security.raw,
        "added_source": "strategy-platform",
    }
    async with await connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(
            """
            SELECT id
            FROM quant.security_universes
            WHERE id = %s
            """,
            (universe_id,),
        )
        if await cursor.fetchone() is None:
            raise DatabaseError(f"股票池不存在：{universe_id}")

        await cursor.execute(
            """
            INSERT INTO quant.securities (
              symbol, code, name, exchange, asset_type, currency, timezone, secid, provider,
              metadata, created_at, updated_at
            )
            VALUES (%s, %s, %s, %s, %s, 'CNY', 'Asia/Shanghai', %s, %s, %s, now(), now())
            ON CONFLICT (symbol) DO UPDATE SET
              code = EXCLUDED.code,
              name = COALESCE(EXCLUDED.name, quant.securities.name),
              exchange = EXCLUDED.exchange,
              asset_type = EXCLUDED.asset_type,
              secid = EXCLUDED.secid,
              provider = EXCLUDED.provider,
              metadata = quant.securities.metadata || EXCLUDED.metadata,
              updated_at = now()
            """,
            (
                symbol,
                security.symbol,
                security.name,
                security.market,
                security.asset_type,
                security.secid,
                security.source,
                Jsonb(metadata),
            ),
        )
        await cursor.execute(
            """
            SELECT COALESCE(max((members.metadata->>'order')::INT), 0) + 1 AS next_order
            FROM quant.security_universe_members members
            WHERE members.universe_id = %s
              AND members.metadata->>'order' ~ '^[0-9]+$'
            """,
            (universe_id,),
        )
        order_row = await cursor.fetchone()
        next_order = int(order_row["next_order"] or 1) if order_row else 1
        await cursor.execute(
            """
            INSERT INTO quant.security_universe_members (
              universe_id, symbol, role, weight, metadata, added_at
            )
            VALUES (%s, %s, %s, %s, %s, now())
            ON CONFLICT (universe_id, symbol) DO UPDATE SET
              role = EXCLUDED.role,
              weight = EXCLUDED.weight,
              metadata = quant.security_universe_members.metadata || EXCLUDED.metadata
            """,
            (
                universe_id,
                symbol,
                role or "member",
                weight,
                Jsonb({"order": next_order, "added_source": "strategy-platform"}),
            ),
        )

    universes = await list_research_universes()
    for universe in universes:
        if universe.id != universe_id:
            continue
        for member in universe.members:
            if member.symbol == symbol:
                return member
    raise DatabaseError(f"股票已写入但无法读取股票池成员：{symbol}")


async def list_market_data_coverage(
    universe_id: str | None = None,
) -> list[MarketDataCoverageItem]:
    async with await connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        if universe_id:
            await cursor.execute(
                """
                    SELECT
                      securities.symbol,
                      securities.name,
                      COALESCE(
                        coverage.timeframe,
                        universes.metadata->>'default_timeframe',
                        'daily'
                      ) AS timeframe,
                      COALESCE(
                        coverage.adjustment,
                        universes.metadata->>'default_adjustment',
                        'qfq'
                      ) AS adjustment,
                      COALESCE(
                        coverage.provider,
                        universes.metadata->>'provider',
                        'eastmoney'
                      ) AS provider,
                      coverage.first_ts,
                      coverage.last_ts,
                      COALESCE(coverage.row_count, 0) AS row_count
                    FROM quant.security_universe_members members
                    JOIN quant.security_universes universes
                      ON universes.id = members.universe_id
                    JOIN quant.securities securities
                      ON securities.symbol = members.symbol
                    LEFT JOIN LATERAL (
                      SELECT coverage_row.*
                      FROM quant.market_data_coverage coverage_row
                      WHERE coverage_row.symbol = securities.symbol
                        AND coverage_row.timeframe = COALESCE(
                          universes.metadata->>'default_timeframe',
                          'daily'
                        )
                        AND coverage_row.adjustment = COALESCE(
                          universes.metadata->>'default_adjustment',
                          'qfq'
                        )
                      ORDER BY (
                        coverage_row.provider = COALESCE(
                          universes.metadata->>'provider',
                          'eastmoney'
                        )
                      ) DESC, coverage_row.last_ts DESC NULLS LAST
                      LIMIT 1
                    ) coverage ON TRUE
                    WHERE members.universe_id = %s
                    ORDER BY members.metadata->>'order', securities.symbol
                    """,
                (universe_id,),
            )
        else:
            await cursor.execute(
                """
                    SELECT
                      coverage.symbol,
                      securities.name,
                      coverage.timeframe,
                      coverage.adjustment,
                      coverage.provider,
                      coverage.first_ts,
                      coverage.last_ts,
                      coverage.row_count
                    FROM quant.market_data_coverage coverage
                    LEFT JOIN quant.securities securities
                      ON securities.symbol = coverage.symbol
                    ORDER BY coverage.symbol, coverage.timeframe, coverage.adjustment
                    """,
            )
        rows = await cursor.fetchall()

    return [
        MarketDataCoverageItem(
            symbol=str(row["symbol"]),
            name=row["name"],
            timeframe=row["timeframe"],
            adjustment=row["adjustment"],
            provider=str(row["provider"]),
            first_ts=row["first_ts"],
            last_ts=row["last_ts"],
            row_count=int(row["row_count"] or 0),
            data_status=coverage_status(int(row["row_count"] or 0), row["last_ts"]),
        )
        for row in rows
    ]


def calculate_return_pct(
    latest_close: Decimal | None,
    previous_close: Decimal | None,
) -> Decimal | None:
    if latest_close is None or previous_close is None or previous_close == 0:
        return None
    return ((latest_close - previous_close) / previous_close) * Decimal("100")


def aggregate_local_bars(
    bars: list[LocalKlineBar],
    timeframe: str,
) -> list[LocalKlineBar]:
    if timeframe not in {"weekly", "monthly"}:
        return bars

    grouped: dict[tuple[int, int], list[LocalKlineBar]] = {}
    for bar in bars:
        local_date = bar.ts.astimezone(SHANGHAI_TZ).date()
        if timeframe == "weekly":
            iso_year, iso_week, _ = local_date.isocalendar()
            key = (iso_year, iso_week)
        else:
            key = (local_date.year, local_date.month)
        grouped.setdefault(key, []).append(bar)

    aggregated: list[LocalKlineBar] = []
    for _, bucket_bars in sorted(grouped.items()):
        ordered = sorted(bucket_bars, key=lambda item: item.ts)
        amount_values = [item.amount for item in ordered if item.amount is not None]
        turnover_values = [item.turnover for item in ordered if item.turnover is not None]
        aggregated.append(
            LocalKlineBar(
                ts=ordered[-1].ts,
                open=ordered[0].open,
                high=max(item.high for item in ordered),
                low=min(item.low for item in ordered),
                close=ordered[-1].close,
                volume=sum((item.volume for item in ordered), Decimal("0")),
                amount=sum(amount_values, Decimal("0")) if amount_values else None,
                turnover=sum(turnover_values, Decimal("0")) if turnover_values else None,
                provider=ordered[-1].provider,
                metadata={
                    "aggregated_from": "daily",
                    "source_bar_count": len(ordered),
                    "source_first_ts": ordered[0].ts.isoformat(),
                    "source_last_ts": ordered[-1].ts.isoformat(),
                },
            )
        )
    return aggregated


def enrich_local_change_fields(bars: list[LocalKlineBar]) -> list[LocalKlineBar]:
    enriched: list[LocalKlineBar] = []
    previous_close: Decimal | None = None
    for bar in bars:
        change_amount = bar.change_amount
        change_percent = bar.change_percent
        if (
            bar.close is not None
            and previous_close is not None
            and previous_close != 0
        ):
            calculated_amount = bar.close - previous_close
            change_amount = change_amount if change_amount is not None else calculated_amount
            change_percent = (
                change_percent
                if change_percent is not None
                else (calculated_amount / previous_close) * Decimal("100")
            )
        enriched.append(
            bar.model_copy(
                update={
                    "change_amount": change_amount,
                    "change_percent": change_percent,
                }
            )
        )
        previous_close = bar.close
    return enriched


async def get_local_kline(
    *,
    symbol: str,
    timeframe: str = "daily",
    adjustment: str = "qfq",
    provider: str | None = None,
    limit: int = 240,
) -> LocalKlineResponse:
    normalized_limit = max(1, min(limit, 2000))
    query_timeframe = "daily" if timeframe in {"weekly", "monthly"} else timeframe
    source_limit = 8000 if timeframe in {"weekly", "monthly"} else normalized_limit

    async with await connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(
            """
            WITH selected_provider AS (
              SELECT stock_bars.provider
              FROM quant.stock_bars stock_bars
              WHERE stock_bars.symbol = %s
                AND stock_bars.timeframe = %s
                AND stock_bars.adjustment = %s
              GROUP BY stock_bars.provider
              ORDER BY max(stock_bars.ts) DESC, count(*) DESC
              LIMIT 1
            ),
            matching_bars AS (
              SELECT stock_bars.*
              FROM quant.stock_bars stock_bars
              WHERE stock_bars.symbol = %s
                AND stock_bars.timeframe = %s
                AND stock_bars.adjustment = %s
                AND stock_bars.provider = COALESCE(%s, (SELECT provider FROM selected_provider))
            ),
            coverage_summary AS (
              SELECT
                count(*)::INT AS coverage_row_count,
                min(ts) AS coverage_first_ts,
                max(ts) AS coverage_last_ts
              FROM matching_bars
            ),
            selected_bars AS (
              SELECT matching_bars.*
              FROM matching_bars
              ORDER BY matching_bars.ts DESC
              LIMIT %s
            )
            SELECT
              selected_bars.ts,
              selected_bars.timeframe,
              selected_bars.adjustment,
              selected_bars.open,
              selected_bars.high,
              selected_bars.low,
              selected_bars.close,
              selected_bars.volume,
              selected_bars.amount,
              selected_bars.provider AS data_provider,
              selected_bars.metadata AS bar_metadata,
              coverage_summary.coverage_row_count,
              coverage_summary.coverage_first_ts,
              coverage_summary.coverage_last_ts,
              securities.symbol,
              securities.code,
              securities.name,
              securities.exchange,
              securities.asset_type,
              securities.currency,
              securities.timezone,
              securities.secid,
              securities.provider
            FROM selected_bars
            CROSS JOIN coverage_summary
            LEFT JOIN quant.securities securities
              ON securities.symbol = selected_bars.symbol
            ORDER BY selected_bars.ts ASC
            """,
            (
                symbol,
                query_timeframe,
                adjustment,
                symbol,
                query_timeframe,
                adjustment,
                provider,
                source_limit,
            ),
        )
        rows = await cursor.fetchall()

    if not rows:
        return LocalKlineResponse(
            symbol=symbol,
            timeframe=timeframe,
            adjustment=adjustment,
            bars=[],
            summary=LocalKlineSummary(),
        )

    source_bars: list[LocalKlineBar] = []
    for row in rows:
        metadata = json_object(row["bar_metadata"])
        source_bars.append(
            LocalKlineBar(
                ts=row["ts"],
                open=row["open"],
                high=row["high"],
                low=row["low"],
                close=row["close"],
                volume=row["volume"],
                amount=row["amount"],
                amplitude=decimal_from_json(metadata.get("amplitude")),
                change_percent=decimal_from_json(metadata.get("change_percent")),
                change_amount=decimal_from_json(metadata.get("change_amount")),
                turnover=decimal_from_json(metadata.get("turnover")),
                provider=str(row["data_provider"]),
                metadata=metadata,
            )
        )
    enriched_source_bars = enrich_local_change_fields(source_bars)
    aggregated_bars = enrich_local_change_fields(
        aggregate_local_bars(enriched_source_bars, timeframe)
    )
    all_bars = aggregated_bars if timeframe in {"weekly", "monthly"} else enriched_source_bars
    bars = all_bars[-normalized_limit:]
    latest = bars[-1] if bars else None
    previous = bars[-2] if len(bars) > 1 else None
    first_row = rows[0]
    summary_first_ts = all_bars[0].ts if all_bars else None
    summary_last_ts = all_bars[-1].ts if all_bars else None
    if timeframe not in {"weekly", "monthly"}:
        summary_first_ts = first_row["coverage_first_ts"] or summary_first_ts
        summary_last_ts = first_row["coverage_last_ts"] or summary_last_ts
    summary = LocalKlineSummary(
        row_count=(
            len(all_bars)
            if timeframe in {"weekly", "monthly"}
            else int(first_row["coverage_row_count"] or len(bars))
        ),
        first_ts=summary_first_ts,
        last_ts=summary_last_ts,
        latest_close=latest.close if latest else None,
        previous_close=previous.close if previous else None,
        return_pct=calculate_return_pct(
            latest.close if latest else None,
            previous.close if previous else None,
        ),
        high=max((bar.high for bar in bars), default=None),
        low=min((bar.low for bar in bars), default=None),
        total_volume=sum((bar.volume for bar in bars), Decimal("0")),
        total_amount=sum((bar.amount or Decimal("0") for bar in bars), Decimal("0")),
    )
    return LocalKlineResponse(
        symbol=str(first_row["symbol"] or symbol),
        code=first_row["code"],
        name=first_row["name"],
        exchange=first_row["exchange"] or "UNKNOWN",
        asset_type=first_row["asset_type"] or "stock",
        currency=first_row["currency"] or "CNY",
        timezone=first_row["timezone"] or "Asia/Shanghai",
        secid=first_row["secid"],
        provider=first_row["provider"],
        timeframe=timeframe,
        adjustment=str(first_row["adjustment"] or adjustment),
        bars=bars,
        summary=summary,
    )


async def create_ingestion_job(
    *,
    job_id: str,
    universe_id: str | None,
    timeframe: str,
    adjustment: str,
    total_symbols: int,
    metadata: dict[str, Any],
) -> None:
    async with await connect() as connection, connection.cursor() as cursor:
        await cursor.execute(
            """
                INSERT INTO quant.market_data_ingestion_jobs (
                  id, universe_id, provider, timeframe, adjustment, status, total_symbols,
                  metadata, started_at, created_at, updated_at
                )
                VALUES (%s, %s, 'eastmoney', %s, %s, 'running', %s, %s, now(), now(), now())
                ON CONFLICT (id) DO UPDATE SET
                  status = 'running',
                  total_symbols = EXCLUDED.total_symbols,
                  metadata = quant.market_data_ingestion_jobs.metadata || EXCLUDED.metadata,
                  started_at = now(),
                  updated_at = now()
                """,
            (job_id, universe_id, timeframe, adjustment, total_symbols, Jsonb(metadata)),
        )


async def finish_ingestion_job(response: HistoryIngestionResponse) -> None:
    errors = [
        {"symbol": item.symbol, "error": item.error}
        for item in response.symbols
        if item.status == "failed" and item.error
    ]
    async with await connect() as connection, connection.cursor() as cursor:
        await cursor.execute(
            """
                UPDATE quant.market_data_ingestion_jobs
                SET
                  status = %s,
                  completed_symbols = %s,
                  failed_symbols = %s,
                  rows_received = %s,
                  rows_upserted = %s,
                  error = %s,
                  metadata = metadata || %s,
                  completed_at = %s,
                  updated_at = now()
                WHERE id = %s
                """,
            (
                response.status,
                response.completed_symbols,
                response.failed_symbols,
                response.rows_received,
                response.rows_upserted,
                "; ".join(f"{item['symbol']}: {item['error']}" for item in errors)[:2000]
                or None,
                Jsonb(
                    {"symbol_results": [item.model_dump(mode="json") for item in response.symbols]}
                ),
                response.completed_at,
                response.job_id,
            ),
        )


async def upsert_kline_response(
    kline: KlineResponse,
    *,
    universe_id: str | None,
    lookback_years: int | None = 5,
) -> tuple[str, int, str | None, str | None]:
    symbol = canonical_symbol(kline.symbol, kline.market)
    cutoff = lookback_cutoff_datetime(lookback_years)
    bars: list[tuple[Any, ...]] = []
    first_date: str | None = None
    last_date: str | None = None
    for bar in kline.bars:
        if bar.open is None or bar.high is None or bar.low is None or bar.close is None:
            continue
        ts = parse_bar_datetime(bar.date)
        if cutoff is not None and ts < cutoff:
            continue
        first_date = first_date or bar.date
        last_date = bar.date
        bar_metadata = {
            "secid": kline.secid,
            "name": kline.name,
            "market": kline.market,
            "asset_type": kline.asset_type,
            "currency": kline.currency,
            "timezone": kline.timezone,
            "source": kline.source,
            "source_response": kline.metadata,
            "source_bar": bar.metadata,
            "amplitude": str(bar.amplitude) if bar.amplitude is not None else None,
            "change_percent": (
                str(bar.change_percent) if bar.change_percent is not None else None
            ),
            "change_amount": (
                str(bar.change_amount) if bar.change_amount is not None else None
            ),
            "turnover": str(bar.turnover) if bar.turnover is not None else None,
            "universe_id": universe_id,
        }
        bars.append(
            (
                symbol,
                ts,
                kline.period,
                kline.adjustment,
                bar.open,
                bar.high,
                bar.low,
                bar.close,
                decimal_or_zero(bar.volume),
                decimal_or_none(bar.amount),
                kline.source,
                Jsonb(bar_metadata),
            )
        )

    if not bars:
        return symbol, 0, first_date, last_date

    async with await connect() as connection, connection.cursor() as cursor:
        await cursor.execute(
            """
                INSERT INTO quant.securities (
                  symbol, code, name, exchange, asset_type, currency, timezone, secid, provider,
                  metadata, created_at, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now(), now())
                ON CONFLICT (symbol) DO UPDATE SET
                  code = EXCLUDED.code,
                  name = COALESCE(EXCLUDED.name, quant.securities.name),
                  exchange = EXCLUDED.exchange,
                  asset_type = EXCLUDED.asset_type,
                  currency = EXCLUDED.currency,
                  timezone = EXCLUDED.timezone,
                  secid = EXCLUDED.secid,
                  metadata = quant.securities.metadata || EXCLUDED.metadata,
                  updated_at = now()
                """,
            (
                symbol,
                kline.symbol,
                kline.name,
                kline.market,
                kline.asset_type,
                kline.currency,
                kline.timezone,
                kline.secid,
                kline.source,
                Jsonb({"source": kline.source, "fetched_at": kline.fetched_at.isoformat()}),
            ),
        )
        await cursor.executemany(
            """
                INSERT INTO quant.stock_bars (
                  symbol, ts, timeframe, adjustment, open, high, low, close, volume, amount,
                  provider, metadata, created_at
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, now())
                ON CONFLICT (symbol, timeframe, adjustment, ts) DO UPDATE SET
                  open = EXCLUDED.open,
                  high = EXCLUDED.high,
                  low = EXCLUDED.low,
                  close = EXCLUDED.close,
                  volume = EXCLUDED.volume,
                  amount = COALESCE(EXCLUDED.amount, quant.stock_bars.amount),
                  provider = CASE
                    WHEN EXCLUDED.amount IS NULL
                     AND EXCLUDED.metadata->>'turnover' IS NULL
                     AND (
                       quant.stock_bars.amount IS NOT NULL
                       OR quant.stock_bars.metadata->>'turnover' IS NOT NULL
                     )
                    THEN quant.stock_bars.provider
                    ELSE EXCLUDED.provider
                  END,
                  metadata = quant.stock_bars.metadata || jsonb_strip_nulls(EXCLUDED.metadata)
                """,
            bars,
        )
        if cutoff is not None:
            await cursor.execute(
                """
                DELETE FROM quant.stock_bars
                WHERE symbol = %s
                  AND timeframe = %s
                  AND adjustment = %s
                  AND provider = %s
                  AND ts < %s
                """,
                (symbol, kline.period, kline.adjustment, kline.source, cutoff),
            )
        await cursor.execute(
            """
                INSERT INTO quant.market_data_sync_state (
                  symbol, timeframe, adjustment, provider, first_ts, last_ts, row_count,
                  last_success_at, last_error, metadata, created_at, updated_at
                )
                SELECT
                  %s,
                  %s,
                  %s,
                  %s,
                  min(ts),
                  max(ts),
                  count(*)::INT,
                  now(),
                  NULL,
                  %s,
                  now(),
                  now()
                FROM quant.stock_bars
                WHERE symbol = %s
                  AND timeframe = %s
                  AND adjustment = %s
                  AND provider = %s
                ON CONFLICT (symbol, timeframe, adjustment, provider) DO UPDATE SET
                  first_ts = EXCLUDED.first_ts,
                  last_ts = EXCLUDED.last_ts,
                  row_count = EXCLUDED.row_count,
                  last_success_at = now(),
                  last_error = NULL,
                  metadata = quant.market_data_sync_state.metadata || EXCLUDED.metadata,
                  updated_at = now()
                """,
            (
                symbol,
                kline.period,
                kline.adjustment,
                kline.source,
                Jsonb({"name": kline.name, "secid": kline.secid, "universe_id": universe_id}),
                symbol,
                kline.period,
                kline.adjustment,
                kline.source,
            ),
        )

    return symbol, len(bars), first_date, last_date
