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
    IngestionJobSummary,
    KlineResponse,
    LocalKlineBar,
    LocalKlineResponse,
    LocalKlineSummary,
    MarketDataCoverageItem,
    RealtimeQuote,
    ResearchUniverse,
    ResearchUniverseMember,
    ResearchUniverseSummary,
    SymbolResolveResult,
)

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
DEFAULT_UNIVERSE_ID = "a-share-sample-research-pool"
ROOT_DIR = Path(__file__).resolve().parents[4]
SECTOR_HINT_LABELS = {
    "semiconductor": "半导体",
    "gaming": "游戏",
    "bank": "银行",
    "gold-retail": "黄金珠宝",
    "liquor": "白酒",
    "home-appliance": "家电",
    "battery": "电池",
    "new-energy-auto": "新能源汽车",
    "insurance": "保险",
    "utility": "公用事业",
    "solar": "光伏",
    "pharma": "医药",
    "display-panel": "面板",
    "security-equipment": "安防设备",
    "telecom": "通信服务",
    "oil-gas": "石油石化",
    "construction": "建筑工程",
    "petrochemical": "石油化工",
    "coal-chemical": "煤化工",
    "chemical": "化工",
    "soda-ash": "纯碱",
    "fiberglass": "玻璃纤维",
}


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


def trade_date_datetime(value: date | str) -> datetime:
    parsed_date = date.fromisoformat(value) if isinstance(value, str) else value
    return datetime.combine(parsed_date, time.min, tzinfo=SHANGHAI_TZ).astimezone(UTC)


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


def decimal_subtract(
    left: Decimal | int | None,
    right: Decimal | int | None,
) -> Decimal | None:
    left_decimal = decimal_or_none(left)
    right_decimal = decimal_or_none(right)
    if left_decimal is None or right_decimal is None:
        return None
    return left_decimal - right_decimal


def amplitude_percent(
    high: Decimal | int | None,
    low: Decimal | int | None,
    previous_close: Decimal | int | None,
) -> Decimal | None:
    high_decimal = decimal_or_none(high)
    low_decimal = decimal_or_none(low)
    previous_decimal = decimal_or_none(previous_close)
    if high_decimal is None or low_decimal is None or previous_decimal in (None, Decimal("0")):
        return None
    return ((high_decimal - low_decimal) / previous_decimal) * Decimal("100")


def decimal_from_json(value: Any) -> Decimal | None:
    if value in (None, "", "-"):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def bool_or_none(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "t", "yes", "y"}:
        return True
    if normalized in {"0", "false", "f", "no", "n"}:
        return False
    return None


def json_array(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def json_object(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_decimal(*values: Any) -> Decimal | None:
    for value in values:
        parsed = decimal_from_json(value)
        if parsed is not None:
            return parsed
    return None


def first_text(*values: Any) -> str | None:
    for value in values:
        if isinstance(value, str):
            text = value.strip()
            if text and text not in {"-", "--", "无", "暂无"}:
                return text
        elif value is not None:
            text = str(value).strip()
            if text and text not in {"-", "--", "无", "暂无"}:
                return text
    return None


def split_sector_values(value: Any) -> list[str]:
    if isinstance(value, list):
        values = value
    elif isinstance(value, str):
        normalized = (
            value.replace("，", ",")
            .replace("、", ",")
            .replace("；", ",")
            .replace(";", ",")
            .replace("|", ",")
        )
        values = normalized.split(",")
    else:
        values = []
    return [
        text
        for item in values
        if (text := str(item).strip()) and text not in {"-", "--", "无", "暂无"}
    ]


def unique_non_empty(values: list[str | None]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not value:
            continue
        text = value.strip()
        if not text or text in {"-", "--", "无", "暂无"} or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def security_sector_fields(metadata_value: Any) -> dict[str, Any]:
    metadata = json_object(metadata_value)
    raw = json_object(metadata.get("raw"))
    sector_hint = first_text(metadata.get("sector_hint"), raw.get("sector_hint"))
    sector_hint_label = SECTOR_HINT_LABELS.get(sector_hint or "", sector_hint)
    industry = first_text(metadata.get("industry"), raw.get("industry"), raw.get("f100"))
    region = first_text(metadata.get("region"), raw.get("region"), raw.get("f102"))
    concepts = split_sector_values(
        metadata.get("concepts")
        or raw.get("concepts")
        or raw.get("f103")
    )
    sector_tags = unique_non_empty([industry, *concepts[:3], region, sector_hint_label])
    return {
        "industry": industry,
        "region": region,
        "concepts": concepts,
        "sector_hint": sector_hint,
        "sector_tags": sector_tags,
    }


def coverage_status(row_count: int | None, last_ts: datetime | None) -> str:
    if not row_count:
        return "missing"
    if last_ts is None:
        return "missing"
    return "ready"


def percent_change(current: Decimal | None, base: Decimal | None) -> Decimal | None:
    if current is None or base is None or base == 0:
        return None
    return (current / base - Decimal("1")) * Decimal("100")


def universe_trend_status(
    *,
    latest_close: Decimal | None,
    ma20: Decimal | None,
    ma60: Decimal | None,
    sample_count: int,
) -> str:
    if sample_count < 60 or latest_close is None or ma20 is None or ma60 is None:
        return "insufficient"
    if latest_close >= ma20 >= ma60:
        return "bullish"
    if latest_close <= ma20 <= ma60:
        return "bearish"
    return "sideways"


def research_member_from_row(row: dict[str, Any]) -> ResearchUniverseMember:
    row_count = int(row["row_count"] or 0)
    sector_fields = security_sector_fields(row["security_metadata"])
    latest_close = decimal_or_none(row["latest_close"])
    previous_close = decimal_or_none(row["previous_close"])
    latest_change_percent = decimal_or_none(row.get("latest_change_percent"))
    close_20d = decimal_or_none(row["close_20d"])
    close_60d = decimal_or_none(row["close_60d"])
    ma20 = decimal_or_none(row["ma20"])
    ma60 = decimal_or_none(row["ma60"])
    sample_count = int(row["sample_count"] or 0)
    return ResearchUniverseMember(
        symbol=str(row["symbol"]),
        code=str(row["code"]),
        name=row["security_name"],
        industry=sector_fields["industry"],
        region=sector_fields["region"],
        concepts=sector_fields["concepts"],
        sector_hint=sector_fields["sector_hint"],
        sector_tags=sector_fields["sector_tags"],
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
        latest_close=latest_close,
        latest_change_pct=(
            latest_change_percent
            if latest_change_percent is not None
            else percent_change(latest_close, previous_close)
        ),
        latest_amount=decimal_or_none(row.get("latest_amount")),
        latest_turnover=decimal_or_none(row.get("latest_turnover")),
        strength_20d_pct=percent_change(latest_close, close_20d),
        strength_60d_pct=percent_change(latest_close, close_60d),
        ma20=ma20,
        ma60=ma60,
        trend_status=universe_trend_status(
            latest_close=latest_close,
            ma20=ma20,
            ma60=ma60,
            sample_count=sample_count,
        ),
        avg_amount_20d=decimal_or_none(row["avg_amount_20d"]),
        avg_volume_20d=decimal_or_none(row["avg_volume_20d"]),
        avg_turnover_20d=decimal_or_none(row.get("avg_turnover_20d")),
        trade_status=row.get("trade_status"),
        is_st=bool_or_none(row.get("is_st")),
        limit_up=bool_or_none(row.get("limit_up")),
        limit_down=bool_or_none(row.get("limit_down")),
        pe_ttm=decimal_or_none(row.get("pe_ttm")),
        pb_mrq=decimal_or_none(row.get("pb_mrq")),
        ps_ttm=decimal_or_none(row.get("ps_ttm")),
        pcf_ncf_ttm=decimal_or_none(row.get("pcf_ncf_ttm")),
        data_status=coverage_status(row_count, row["last_ts"]),
    )


async def get_universe_fetch_targets(universe_id: str) -> list[dict[str, str]]:
    async with await connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(
            """
                SELECT securities.symbol, securities.code, securities.secid
                FROM quant.security_universe_members members
                JOIN quant.securities securities
                  ON securities.symbol = members.symbol
                WHERE members.universe_id = %s
                ORDER BY
                  CASE
                    WHEN members.metadata->>'order' ~ '^[0-9]+$'
                    THEN (members.metadata->>'order')::INT
                  END NULLS LAST,
                  securities.symbol
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
                  securities.metadata AS security_metadata,
                  securities.status AS security_status,
                  members.role,
                  members.weight,
                  sync_state.first_ts,
                  sync_state.last_ts,
                  sync_state.provider AS data_provider,
                  COALESCE(sync_state.row_count, 0) AS row_count,
                  market_metrics.sample_count,
                  market_metrics.latest_close,
                  market_metrics.previous_close,
                  market_metrics.latest_change_percent,
                  market_metrics.latest_amount,
                  market_metrics.latest_turnover,
                  market_metrics.close_20d,
                  market_metrics.close_60d,
                  market_metrics.ma20,
                  market_metrics.ma60,
                  market_metrics.avg_amount_20d,
                  market_metrics.avg_volume_20d,
                  market_metrics.avg_turnover_20d,
                  market_metrics.trade_status,
                  market_metrics.is_st,
                  market_metrics.limit_up,
                  market_metrics.limit_down,
                  factor_metrics.pe_ttm,
                  factor_metrics.pb_mrq,
                  factor_metrics.ps_ttm,
                  factor_metrics.pcf_ncf_ttm
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
                LEFT JOIN LATERAL (
                  SELECT
                    count(*)::INT AS sample_count,
                    (array_agg(recent.close ORDER BY recent.ts DESC))[1] AS latest_close,
                    (array_agg(recent.close ORDER BY recent.ts DESC))[2] AS previous_close,
                    (array_agg(recent.change_percent ORDER BY recent.ts DESC))[1]
                      AS latest_change_percent,
                    (array_agg(recent.amount ORDER BY recent.ts DESC))[1] AS latest_amount,
                    (array_agg(recent.turnover ORDER BY recent.ts DESC))[1] AS latest_turnover,
                    (array_agg(recent.close ORDER BY recent.ts DESC))[21] AS close_20d,
                    (array_agg(recent.close ORDER BY recent.ts DESC))[61] AS close_60d,
                    avg(recent.close) FILTER (WHERE recent.rn <= 20) AS ma20,
                    avg(recent.close) FILTER (WHERE recent.rn <= 60) AS ma60,
                    avg(recent.amount) FILTER (
                      WHERE recent.rn <= 20 AND recent.amount IS NOT NULL
                    ) AS avg_amount_20d,
                    avg(recent.volume) FILTER (WHERE recent.rn <= 20) AS avg_volume_20d,
                    avg(recent.turnover) FILTER (
                      WHERE recent.rn <= 20 AND recent.turnover IS NOT NULL
                    ) AS avg_turnover_20d,
                    (array_agg(recent.trade_status ORDER BY recent.ts DESC))[1] AS trade_status,
                    (array_agg(recent.is_st ORDER BY recent.ts DESC))[1] AS is_st,
                    (array_agg(recent.limit_up ORDER BY recent.ts DESC))[1] AS limit_up,
                    (array_agg(recent.limit_down ORDER BY recent.ts DESC))[1] AS limit_down
                  FROM (
                    SELECT
                      bars.ts,
                      bars.close,
                      bars.amount,
                      bars.volume,
                      bars.change_percent,
                      bars.turnover,
                      bars.trade_status,
                      bars.is_st,
                      bars.limit_up,
                      bars.limit_down,
                      row_number() OVER (ORDER BY bars.ts DESC) AS rn
                    FROM quant.stock_bars bars
                    WHERE bars.symbol = securities.symbol
                      AND bars.timeframe = COALESCE(
                        universes.metadata->>'default_timeframe',
                        'daily'
                      )
                      AND bars.adjustment = COALESCE(
                        universes.metadata->>'default_adjustment',
                        'qfq'
                      )
                    ORDER BY bars.ts DESC
                    LIMIT 61
                  ) recent
                ) market_metrics ON TRUE
                LEFT JOIN LATERAL (
                  SELECT
                    max(factor_value) FILTER (WHERE factor_key = 'pe_ttm') AS pe_ttm,
                    max(factor_value) FILTER (WHERE factor_key = 'pb_mrq') AS pb_mrq,
                    max(factor_value) FILTER (WHERE factor_key = 'ps_ttm') AS ps_ttm,
                    max(factor_value) FILTER (WHERE factor_key = 'pcf_ncf_ttm')
                      AS pcf_ncf_ttm
                  FROM (
                    SELECT DISTINCT ON (factor_key)
                      factor_key,
                      factor_value
                    FROM quant.stock_factors
                    WHERE symbol = securities.symbol
                    ORDER BY factor_key, ts DESC
                  ) latest_factors
                ) factor_metrics ON TRUE
                ORDER BY
                  CASE
                    WHEN universes.metadata->>'display_order' ~ '^[0-9]+$'
                    THEN (universes.metadata->>'display_order')::INT
                  END NULLS LAST,
                  universes.created_at,
                  CASE
                    WHEN members.metadata->>'order' ~ '^[0-9]+$'
                    THEN (members.metadata->>'order')::INT
                  END NULLS LAST,
                  securities.symbol
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
            universes[universe_id].members.append(research_member_from_row(row))

    for universe in universes.values():
        universe.member_count = len(universe.members)
        universe.stock_count = sum(
            1 for member in universe.members if member.asset_type == "stock"
        )
        universe.etf_count = sum(1 for member in universe.members if member.asset_type == "etf")
        universe.index_count = sum(
            1 for member in universe.members if member.asset_type == "index"
        )
        universe.fund_count = sum(
            1 for member in universe.members if member.asset_type == "fund"
        )
        universe.ready_count = sum(
            1 for member in universe.members if member.data_status == "ready"
        )
        universe.bar_count = sum(member.row_count for member in universe.members)
        universe.latest_ts = max(
            (member.last_ts for member in universe.members if member.last_ts),
            default=None,
        )
    return list(universes.values())


async def list_research_universe_summaries() -> list[ResearchUniverseSummary]:
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
                  count(members.symbol)::INT AS member_count,
                  count(*) FILTER (WHERE securities.asset_type = 'stock')::INT AS stock_count,
                  count(*) FILTER (WHERE securities.asset_type = 'etf')::INT AS etf_count,
                  count(*) FILTER (WHERE securities.asset_type = 'index')::INT AS index_count,
                  count(*) FILTER (WHERE securities.asset_type = 'fund')::INT AS fund_count,
                  count(*) FILTER (
                    WHERE COALESCE(sync_state.row_count, 0) > 0
                      AND sync_state.last_ts IS NOT NULL
                  )::INT AS ready_count,
                  COALESCE(sum(sync_state.row_count), 0)::BIGINT AS bar_count,
                  max(sync_state.last_ts) AS latest_ts
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
                GROUP BY
                  universes.id,
                  universes.name,
                  universes.description,
                  universes.status,
                  universes.source,
                  universes.tags,
                  universes.metadata,
                  universes.created_at,
                  universes.updated_at
                ORDER BY
                  CASE
                    WHEN universes.metadata->>'display_order' ~ '^[0-9]+$'
                    THEN (universes.metadata->>'display_order')::INT
                  END NULLS LAST,
                  universes.created_at
                """,
        )
        rows = await cursor.fetchall()

    summaries: list[ResearchUniverseSummary] = []
    for row in rows:
        metadata = json_object(row["universe_metadata"])
        summaries.append(
            ResearchUniverseSummary(
                id=str(row["id"]),
                name=str(row["name"]),
                description=row["description"],
                status=str(row["status"]),
                source=str(row["source"]),
                tags=json_array(row["tags"]),
                default_timeframe=metadata.get("default_timeframe") or "daily",
                default_adjustment=metadata.get("default_adjustment") or "qfq",
                provider=metadata.get("provider") or "eastmoney",
                member_count=int(row["member_count"] or 0),
                stock_count=int(row["stock_count"] or 0),
                etf_count=int(row["etf_count"] or 0),
                index_count=int(row["index_count"] or 0),
                fund_count=int(row["fund_count"] or 0),
                ready_count=int(row["ready_count"] or 0),
                bar_count=int(row["bar_count"] or 0),
                latest_ts=row["latest_ts"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )
    return summaries


async def list_research_universe_members_page(
    *,
    universe_id: str,
    page: int = 1,
    page_size: int = 10,
    keyword: str | None = None,
) -> tuple[list[ResearchUniverseMember], int, int, int]:
    clean_keyword = (keyword or "").strip()
    keyword_pattern = f"%{clean_keyword}%"
    page_size = max(1, min(page_size, 100))

    filter_params = (
        universe_id,
        clean_keyword,
        keyword_pattern,
        keyword_pattern,
        keyword_pattern,
        keyword_pattern,
        keyword_pattern,
        keyword_pattern,
    )
    filter_sql = """
        members.universe_id = %s
        AND (
          %s = ''
          OR securities.symbol ILIKE %s
          OR securities.code ILIKE %s
          OR securities.name ILIKE %s
          OR securities.exchange ILIKE %s
          OR securities.asset_type ILIKE %s
          OR COALESCE(securities.metadata::TEXT, '') ILIKE %s
        )
    """

    async with await connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(
            f"""
                SELECT count(*)::INT AS total
                FROM quant.security_universe_members members
                JOIN quant.securities securities
                  ON securities.symbol = members.symbol
                WHERE {filter_sql}
                """,
            filter_params,
        )
        total_row = await cursor.fetchone()
        total = int(total_row["total"] or 0) if total_row else 0
        total_pages = max(1, (total + page_size - 1) // page_size)
        current_page = min(max(1, page), total_pages)
        offset = (current_page - 1) * page_size

        await cursor.execute(
            f"""
                WITH filtered_members AS (
                  SELECT
                    universes.metadata AS universe_metadata,
                    securities.symbol,
                    securities.code,
                    securities.name AS security_name,
                    securities.exchange,
                    securities.asset_type,
                    securities.currency,
                    securities.timezone,
                    securities.secid,
                    securities.provider,
                    securities.metadata AS security_metadata,
                    securities.status AS security_status,
                    members.role,
                    members.weight,
                    CASE
                      WHEN members.metadata->>'order' ~ '^[0-9]+$'
                      THEN (members.metadata->>'order')::INT
                    END AS member_order
                  FROM quant.security_universe_members members
                  JOIN quant.security_universes universes
                    ON universes.id = members.universe_id
                  JOIN quant.securities securities
                    ON securities.symbol = members.symbol
                  WHERE {filter_sql}
                  ORDER BY member_order NULLS LAST, securities.symbol
                  LIMIT %s OFFSET %s
                )
                SELECT
                  filtered_members.symbol,
                  filtered_members.code,
                  filtered_members.security_name,
                  filtered_members.exchange,
                  filtered_members.asset_type,
                  filtered_members.currency,
                  filtered_members.timezone,
                  filtered_members.secid,
                  filtered_members.provider,
                  filtered_members.security_metadata,
                  filtered_members.security_status,
                  filtered_members.role,
                  filtered_members.weight,
                  sync_state.first_ts,
                  sync_state.last_ts,
                  sync_state.provider AS data_provider,
                  COALESCE(sync_state.row_count, 0) AS row_count,
                  market_metrics.sample_count,
                  market_metrics.latest_close,
                  market_metrics.previous_close,
                  market_metrics.latest_change_percent,
                  market_metrics.latest_amount,
                  market_metrics.latest_turnover,
                  market_metrics.close_20d,
                  market_metrics.close_60d,
                  market_metrics.ma20,
                  market_metrics.ma60,
                  market_metrics.avg_amount_20d,
                  market_metrics.avg_volume_20d,
                  market_metrics.avg_turnover_20d,
                  market_metrics.trade_status,
                  market_metrics.is_st,
                  market_metrics.limit_up,
                  market_metrics.limit_down,
                  factor_metrics.pe_ttm,
                  factor_metrics.pb_mrq,
                  factor_metrics.ps_ttm,
                  factor_metrics.pcf_ncf_ttm
                FROM filtered_members
                LEFT JOIN LATERAL (
                  SELECT sync_row.*
                  FROM quant.market_data_sync_state sync_row
                  WHERE sync_row.symbol = filtered_members.symbol
                    AND sync_row.timeframe = COALESCE(
                      filtered_members.universe_metadata->>'default_timeframe',
                      'daily'
                    )
                    AND sync_row.adjustment = COALESCE(
                      filtered_members.universe_metadata->>'default_adjustment',
                      'qfq'
                    )
                  ORDER BY (
                    sync_row.provider = COALESCE(
                      filtered_members.universe_metadata->>'provider',
                      'eastmoney'
                    )
                  ) DESC, sync_row.last_ts DESC NULLS LAST
                  LIMIT 1
                ) sync_state ON TRUE
                LEFT JOIN LATERAL (
                  SELECT
                    count(*)::INT AS sample_count,
                    (array_agg(recent.close ORDER BY recent.ts DESC))[1] AS latest_close,
                    (array_agg(recent.close ORDER BY recent.ts DESC))[2] AS previous_close,
                    (array_agg(recent.change_percent ORDER BY recent.ts DESC))[1]
                      AS latest_change_percent,
                    (array_agg(recent.amount ORDER BY recent.ts DESC))[1] AS latest_amount,
                    (array_agg(recent.turnover ORDER BY recent.ts DESC))[1] AS latest_turnover,
                    (array_agg(recent.close ORDER BY recent.ts DESC))[21] AS close_20d,
                    (array_agg(recent.close ORDER BY recent.ts DESC))[61] AS close_60d,
                    avg(recent.close) FILTER (WHERE recent.rn <= 20) AS ma20,
                    avg(recent.close) FILTER (WHERE recent.rn <= 60) AS ma60,
                    avg(recent.amount) FILTER (
                      WHERE recent.rn <= 20 AND recent.amount IS NOT NULL
                    ) AS avg_amount_20d,
                    avg(recent.volume) FILTER (WHERE recent.rn <= 20) AS avg_volume_20d,
                    avg(recent.turnover) FILTER (
                      WHERE recent.rn <= 20 AND recent.turnover IS NOT NULL
                    ) AS avg_turnover_20d,
                    (array_agg(recent.trade_status ORDER BY recent.ts DESC))[1] AS trade_status,
                    (array_agg(recent.is_st ORDER BY recent.ts DESC))[1] AS is_st,
                    (array_agg(recent.limit_up ORDER BY recent.ts DESC))[1] AS limit_up,
                    (array_agg(recent.limit_down ORDER BY recent.ts DESC))[1] AS limit_down
                  FROM (
                    SELECT
                      bars.ts,
                      bars.close,
                      bars.amount,
                      bars.volume,
                      bars.change_percent,
                      bars.turnover,
                      bars.trade_status,
                      bars.is_st,
                      bars.limit_up,
                      bars.limit_down,
                      row_number() OVER (ORDER BY bars.ts DESC) AS rn
                    FROM quant.stock_bars bars
                    WHERE bars.symbol = filtered_members.symbol
                      AND bars.timeframe = COALESCE(
                        filtered_members.universe_metadata->>'default_timeframe',
                        'daily'
                      )
                      AND bars.adjustment = COALESCE(
                        filtered_members.universe_metadata->>'default_adjustment',
                        'qfq'
                      )
                    ORDER BY bars.ts DESC
                    LIMIT 61
                  ) recent
                ) market_metrics ON TRUE
                LEFT JOIN LATERAL (
                  SELECT
                    max(factor_value) FILTER (WHERE factor_key = 'pe_ttm') AS pe_ttm,
                    max(factor_value) FILTER (WHERE factor_key = 'pb_mrq') AS pb_mrq,
                    max(factor_value) FILTER (WHERE factor_key = 'ps_ttm') AS ps_ttm,
                    max(factor_value) FILTER (WHERE factor_key = 'pcf_ncf_ttm')
                      AS pcf_ncf_ttm
                  FROM (
                    SELECT DISTINCT ON (factor_key)
                      factor_key,
                      factor_value
                    FROM quant.stock_factors
                    WHERE symbol = filtered_members.symbol
                    ORDER BY factor_key, ts DESC
                  ) latest_factors
                ) factor_metrics ON TRUE
                ORDER BY filtered_members.member_order NULLS LAST, filtered_members.symbol
                """,
            (*filter_params, page_size, offset),
        )
        rows = await cursor.fetchall()

    return [research_member_from_row(row) for row in rows], total, current_page, total_pages


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
        "industry": security.raw.get("industry") or security.raw.get("f100"),
        "region": security.raw.get("region") or security.raw.get("f102"),
        "concepts": security.raw.get("concepts") or security.raw.get("f103"),
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

    members, _, _, _ = await list_research_universe_members_page(
        universe_id=universe_id,
        page=1,
        page_size=10,
        keyword=symbol,
    )
    for member in members:
        if member.symbol == symbol:
            return member
    raise DatabaseError(f"股票已写入但无法读取股票池成员：{symbol}")


async def add_securities_to_universe(
    *,
    universe_id: str,
    securities: list[SymbolResolveResult],
    role: str = "member",
    added_source: str = "a-share-batch-import",
) -> list[ResearchUniverseMember]:
    if not securities:
        return []

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
            SELECT COALESCE(max((members.metadata->>'order')::INT), 0) + 1 AS next_order
            FROM quant.security_universe_members members
            WHERE members.universe_id = %s
              AND members.metadata->>'order' ~ '^[0-9]+$'
            """,
            (universe_id,),
        )
        order_row = await cursor.fetchone()
        next_order = int(order_row["next_order"] or 1) if order_row else 1

        symbols: list[str] = []
        for offset, security in enumerate(securities):
            symbol = canonical_symbol(security.symbol, security.market)
            symbols.append(symbol)
            metadata = {
                "query": security.query,
                "raw": security.raw,
                "industry": security.raw.get("industry") or security.raw.get("f100"),
                "region": security.raw.get("region") or security.raw.get("f102"),
                "concepts": security.raw.get("concepts") or security.raw.get("f103"),
                "added_source": added_source,
            }
            await cursor.execute(
                """
                INSERT INTO quant.securities (
                  symbol, code, name, exchange, asset_type, currency, timezone, secid,
                  provider, metadata, created_at, updated_at
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
                INSERT INTO quant.security_universe_members (
                  universe_id, symbol, role, weight, metadata, added_at
                )
                VALUES (%s, %s, %s, NULL, %s, now())
                ON CONFLICT (universe_id, symbol) DO UPDATE SET
                  role = EXCLUDED.role,
                  metadata = CASE
                    WHEN quant.security_universe_members.metadata ? 'order'
                    THEN quant.security_universe_members.metadata || (EXCLUDED.metadata - 'order')
                    ELSE quant.security_universe_members.metadata || EXCLUDED.metadata
                  END
                """,
                (
                    universe_id,
                    symbol,
                    role or "member",
                    Jsonb(
                        {
                            "order": next_order + offset,
                            "added_source": added_source,
                        }
                    ),
                ),
            )

    universes = await list_research_universes()
    member_by_symbol = {
        member.symbol: member
        for universe in universes
        if universe.id == universe_id
        for member in universe.members
    }
    return [member_by_symbol[symbol] for symbol in symbols if symbol in member_by_symbol]


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
                    ORDER BY
                      CASE
                        WHEN members.metadata->>'order' ~ '^[0-9]+$'
                        THEN (members.metadata->>'order')::INT
                      END NULLS LAST,
                      securities.symbol
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
                previous_close=ordered[0].previous_close,
                volume=sum((item.volume for item in ordered), Decimal("0")),
                amount=sum(amount_values, Decimal("0")) if amount_values else None,
                turnover=sum(turnover_values, Decimal("0")) if turnover_values else None,
                trade_status=ordered[-1].trade_status,
                is_st=ordered[-1].is_st,
                limit_up=None,
                limit_down=None,
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
        base_close = bar.previous_close or previous_close
        change_amount = bar.change_amount
        change_percent = bar.change_percent
        if (
            bar.close is not None
            and base_close is not None
            and base_close != 0
        ):
            calculated_amount = bar.close - base_close
            change_amount = change_amount if change_amount is not None else calculated_amount
            change_percent = (
                change_percent
                if change_percent is not None
                else (calculated_amount / base_close) * Decimal("100")
            )
        enriched.append(
            bar.model_copy(
                update={
                    "previous_close": base_close,
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
            WITH ranked_bars AS (
              SELECT
                stock_bars.*,
                row_number() OVER (
                  PARTITION BY stock_bars.symbol, stock_bars.timeframe, stock_bars.adjustment,
                               stock_bars.ts
                  ORDER BY
                    CASE
                      WHEN stock_bars.provider = %s THEN 0
                      WHEN stock_bars.provider = 'eastmoney' THEN 1
                      WHEN stock_bars.provider = 'baostock' THEN 2
                      WHEN stock_bars.provider = 'akshare' THEN 3
                      ELSE 4
                    END,
                    stock_bars.created_at DESC
                ) AS provider_rank
              FROM quant.stock_bars
              WHERE stock_bars.symbol = %s
                AND stock_bars.timeframe = %s
                AND stock_bars.adjustment = %s
                AND (COALESCE(%s::text, '') = '' OR stock_bars.provider = %s)
            ),
            matching_bars AS (
              SELECT ranked_bars.*
              FROM ranked_bars
              WHERE ranked_bars.provider_rank = 1
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
              selected_bars.previous_close,
              selected_bars.volume,
              selected_bars.amount,
              selected_bars.amplitude,
              selected_bars.change_percent,
              selected_bars.change_amount,
              selected_bars.turnover,
              selected_bars.trade_status,
              selected_bars.is_st,
              selected_bars.limit_up,
              selected_bars.limit_down,
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
                provider,
                symbol,
                query_timeframe,
                adjustment,
                provider,
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
                previous_close=first_decimal(row["previous_close"], metadata.get("previous_close")),
                volume=row["volume"],
                amount=row["amount"],
                amplitude=first_decimal(row["amplitude"], metadata.get("amplitude")),
                change_percent=first_decimal(
                    row["change_percent"],
                    metadata.get("change_percent"),
                ),
                change_amount=first_decimal(
                    row["change_amount"],
                    metadata.get("change_amount"),
                ),
                turnover=first_decimal(row["turnover"], metadata.get("turnover")),
                trade_status=first_text(row["trade_status"], metadata.get("trade_status")),
                is_st=(
                    bool_or_none(row["is_st"])
                    if row["is_st"] is not None
                    else bool_or_none(metadata.get("is_st"))
                ),
                limit_up=(
                    bool_or_none(row["limit_up"])
                    if row["limit_up"] is not None
                    else bool_or_none(metadata.get("limit_up"))
                ),
                limit_down=(
                    bool_or_none(row["limit_down"])
                    if row["limit_down"] is not None
                    else bool_or_none(metadata.get("limit_down"))
                ),
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
        previous_close=(previous.close if previous else latest.previous_close if latest else None),
        return_pct=calculate_return_pct(
            latest.close if latest else None,
            previous.close if previous else latest.previous_close if latest else None,
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
        provider=str(first_row["data_provider"] or first_row["provider"]),
        timeframe=timeframe,
        adjustment=str(first_row["adjustment"] or adjustment),
        bars=bars,
        summary=summary,
    )


async def create_ingestion_job(
    *,
    job_id: str,
    universe_id: str | None,
    provider: str,
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
                VALUES (%s, %s, %s, %s, %s, 'running', %s, %s, now(), now(), now())
                ON CONFLICT (id) DO UPDATE SET
                  provider = EXCLUDED.provider,
                  status = 'running',
                  total_symbols = EXCLUDED.total_symbols,
                  metadata = quant.market_data_ingestion_jobs.metadata || EXCLUDED.metadata,
                  started_at = now(),
                  updated_at = now()
                """,
            (job_id, universe_id, provider, timeframe, adjustment, total_symbols, Jsonb(metadata)),
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
                    {
                        "symbol_results": [
                            item.model_dump(mode="json") for item in response.symbols
                        ],
                        "batch_offset": response.batch_offset,
                        "batch_size": response.batch_size,
                        "next_offset": response.next_offset,
                        "universe_total_symbols": response.universe_total_symbols,
                    }
                ),
                response.completed_at,
                response.job_id,
            ),
        )


async def list_ingestion_jobs(
    *,
    universe_id: str | None = None,
    limit: int = 20,
) -> list[IngestionJobSummary]:
    normalized_limit = max(1, min(limit, 100))
    params: tuple[Any, ...]
    where_sql = ""
    if universe_id:
        where_sql = "WHERE universe_id = %s"
        params = (universe_id, normalized_limit)
    else:
        params = (normalized_limit,)

    async with await connect() as connection, connection.cursor(row_factory=dict_row) as cursor:
        await cursor.execute(
            f"""
                SELECT
                  id,
                  universe_id,
                  provider,
                  timeframe,
                  adjustment,
                  status,
                  total_symbols,
                  completed_symbols,
                  failed_symbols,
                  rows_received,
                  rows_upserted,
                  error,
                  metadata,
                  started_at,
                  completed_at,
                  created_at,
                  updated_at
                FROM quant.market_data_ingestion_jobs
                {where_sql}
                ORDER BY created_at DESC
                LIMIT %s
                """,
            params,
        )
        rows = await cursor.fetchall()

    return [
        IngestionJobSummary(
            id=str(row["id"]),
            universe_id=row["universe_id"],
            provider=str(row["provider"]),
            timeframe=str(row["timeframe"]),
            adjustment=str(row["adjustment"]),
            status=str(row["status"]),
            total_symbols=int(row["total_symbols"] or 0),
            completed_symbols=int(row["completed_symbols"] or 0),
            failed_symbols=int(row["failed_symbols"] or 0),
            rows_received=int(row["rows_received"] or 0),
            rows_upserted=int(row["rows_upserted"] or 0),
            error=row["error"],
            metadata=json_object(row["metadata"]),
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]


async def upsert_kline_response(
    kline: KlineResponse,
    *,
    universe_id: str | None,
    lookback_years: int | None = 5,
) -> tuple[str, int, str | None, str | None]:
    symbol = canonical_symbol(kline.symbol, kline.market)
    cutoff = lookback_cutoff_datetime(lookback_years)
    bars: list[tuple[Any, ...]] = []
    factor_rows: list[tuple[Any, ...]] = []
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
            "previous_close": (
                str(bar.previous_close) if bar.previous_close is not None else None
            ),
            "amplitude": str(bar.amplitude) if bar.amplitude is not None else None,
            "change_percent": (
                str(bar.change_percent) if bar.change_percent is not None else None
            ),
            "change_amount": (
                str(bar.change_amount) if bar.change_amount is not None else None
            ),
            "turnover": str(bar.turnover) if bar.turnover is not None else None,
            "trade_status": bar.trade_status,
            "is_st": bar.is_st,
            "limit_up": bar.limit_up,
            "limit_down": bar.limit_down,
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
                decimal_or_none(bar.previous_close),
                decimal_or_zero(bar.volume),
                decimal_or_none(bar.amount),
                decimal_or_none(bar.amplitude),
                decimal_or_none(bar.change_percent),
                decimal_or_none(bar.change_amount),
                decimal_or_none(bar.turnover),
                bar.trade_status,
                bar.is_st,
                bar.limit_up,
                bar.limit_down,
                kline.source,
                Jsonb(bar_metadata),
            )
        )
        factors = json_object(bar.metadata.get("factors"))
        for factor_key, factor_value in factors.items():
            parsed_factor = decimal_from_json(factor_value)
            if parsed_factor is None:
                continue
            factor_rows.append(
                (
                    symbol,
                    ts,
                    factor_key,
                    float(parsed_factor),
                    kline.source,
                    Jsonb(
                        {
                            "source": kline.source,
                            "source_bar": bar.metadata,
                            "universe_id": universe_id,
                        }
                    ),
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
                  symbol, ts, timeframe, adjustment, open, high, low, close, previous_close,
                  volume, amount, amplitude, change_percent, change_amount, turnover,
                  trade_status, is_st, limit_up, limit_down, provider, metadata, created_at
                )
                VALUES (
                  %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  %s, %s, %s, now()
                )
                ON CONFLICT (symbol, timeframe, adjustment, ts) DO UPDATE SET
                  open = EXCLUDED.open,
                  high = EXCLUDED.high,
                  low = EXCLUDED.low,
                  close = EXCLUDED.close,
                  previous_close = COALESCE(
                    EXCLUDED.previous_close,
                    quant.stock_bars.previous_close
                  ),
                  volume = EXCLUDED.volume,
                  amount = COALESCE(EXCLUDED.amount, quant.stock_bars.amount),
                  amplitude = COALESCE(EXCLUDED.amplitude, quant.stock_bars.amplitude),
                  change_percent = COALESCE(
                    EXCLUDED.change_percent,
                    quant.stock_bars.change_percent
                  ),
                  change_amount = COALESCE(
                    EXCLUDED.change_amount,
                    quant.stock_bars.change_amount
                  ),
                  turnover = COALESCE(EXCLUDED.turnover, quant.stock_bars.turnover),
                  trade_status = COALESCE(EXCLUDED.trade_status, quant.stock_bars.trade_status),
                  is_st = COALESCE(EXCLUDED.is_st, quant.stock_bars.is_st),
                  limit_up = COALESCE(EXCLUDED.limit_up, quant.stock_bars.limit_up),
                  limit_down = COALESCE(EXCLUDED.limit_down, quant.stock_bars.limit_down),
                  provider = CASE
                    WHEN EXCLUDED.amount IS NULL
                     AND EXCLUDED.turnover IS NULL
                     AND (
                       quant.stock_bars.amount IS NOT NULL
                       OR quant.stock_bars.turnover IS NOT NULL
                     )
                    THEN quant.stock_bars.provider
                    ELSE EXCLUDED.provider
                  END,
                  metadata = quant.stock_bars.metadata || jsonb_strip_nulls(EXCLUDED.metadata)
            """,
            bars,
        )
        if factor_rows:
            await cursor.executemany(
                """
                    INSERT INTO quant.stock_factors (
                      symbol, ts, factor_key, factor_value, provider, metadata, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, now())
                    ON CONFLICT (symbol, factor_key, ts) DO UPDATE SET
                      factor_value = EXCLUDED.factor_value,
                      provider = EXCLUDED.provider,
                      metadata = quant.stock_factors.metadata || EXCLUDED.metadata
                    """,
                factor_rows,
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


async def upsert_realtime_quote_snapshot(
    quote: RealtimeQuote,
    *,
    universe_id: str | None,
    trade_date: date | str | None = None,
    adjustment: str = "qfq",
) -> tuple[str, int, str | None, str | None]:
    if quote.open is None or quote.high is None or quote.low is None or quote.price is None:
        return canonical_symbol(quote.symbol, quote.market), 0, None, None

    local_trade_date = (
        date.fromisoformat(trade_date)
        if isinstance(trade_date, str)
        else trade_date
        if trade_date is not None
        else (quote.quote_time or quote.fetched_at).astimezone(SHANGHAI_TZ).date()
    )
    ts = trade_date_datetime(local_trade_date)
    symbol = canonical_symbol(quote.symbol, quote.market)
    change_amount = quote.change_amount or decimal_subtract(quote.price, quote.previous_close)
    amplitude = quote.amplitude or amplitude_percent(quote.high, quote.low, quote.previous_close)
    bar_metadata = {
        "secid": quote.secid,
        "name": quote.name,
        "market": quote.market,
        "asset_type": quote.asset_type,
        "currency": quote.currency,
        "timezone": quote.timezone,
        "source": quote.source,
        "source_bar": {
            "quote_time": quote.quote_time.isoformat() if quote.quote_time else None,
            "fetched_at": quote.fetched_at.isoformat(),
            "price": str(quote.price) if quote.price is not None else None,
            "previous_close": (
                str(quote.previous_close) if quote.previous_close is not None else None
            ),
            "amplitude": str(amplitude) if amplitude is not None else None,
            "change_percent": (
                str(quote.change_percent) if quote.change_percent is not None else None
            ),
            "change_amount": str(change_amount) if change_amount is not None else None,
            "turnover": str(quote.turnover) if quote.turnover is not None else None,
        },
        "previous_close": str(quote.previous_close) if quote.previous_close is not None else None,
        "amplitude": str(amplitude) if amplitude is not None else None,
        "change_percent": str(quote.change_percent) if quote.change_percent is not None else None,
        "change_amount": str(change_amount) if change_amount is not None else None,
        "turnover": str(quote.turnover) if quote.turnover is not None else None,
        "universe_id": universe_id,
        "ingestion_mode": "realtime_snapshot",
    }

    async with await connect() as connection, connection.cursor() as cursor:
        await cursor.execute(
            """
                INSERT INTO quant.securities (
                  symbol, code, name, exchange, asset_type, currency, timezone,
                  secid, provider, metadata, created_at, updated_at
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
                quote.symbol,
                quote.name,
                quote.market,
                quote.asset_type,
                quote.currency,
                quote.timezone,
                quote.secid,
                quote.source,
                Jsonb({"source": quote.source, "fetched_at": quote.fetched_at.isoformat()}),
            ),
        )
        await cursor.execute(
            """
                INSERT INTO quant.stock_bars (
                  symbol, ts, timeframe, adjustment, open, high, low, close, previous_close,
                  volume, amount, amplitude, change_percent, change_amount, turnover,
                  trade_status, is_st, limit_up, limit_down, provider, metadata, created_at
                )
                VALUES (
                  %s, %s, 'daily', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                  NULL, NULL, NULL, NULL, %s, %s, now()
                )
                ON CONFLICT (symbol, timeframe, adjustment, ts) DO UPDATE SET
                  open = EXCLUDED.open,
                  high = EXCLUDED.high,
                  low = EXCLUDED.low,
                  close = EXCLUDED.close,
                  previous_close = COALESCE(
                    EXCLUDED.previous_close,
                    quant.stock_bars.previous_close
                  ),
                  volume = EXCLUDED.volume,
                  amount = COALESCE(EXCLUDED.amount, quant.stock_bars.amount),
                  amplitude = COALESCE(EXCLUDED.amplitude, quant.stock_bars.amplitude),
                  change_percent = COALESCE(
                    EXCLUDED.change_percent,
                    quant.stock_bars.change_percent
                  ),
                  change_amount = COALESCE(EXCLUDED.change_amount, quant.stock_bars.change_amount),
                  turnover = COALESCE(EXCLUDED.turnover, quant.stock_bars.turnover),
                  provider = EXCLUDED.provider,
                  metadata = quant.stock_bars.metadata || jsonb_strip_nulls(EXCLUDED.metadata)
                """,
            (
                symbol,
                ts,
                adjustment,
                quote.open,
                quote.high,
                quote.low,
                quote.price,
                decimal_or_none(quote.previous_close),
                decimal_or_zero(quote.volume),
                decimal_or_none(quote.amount),
                decimal_or_none(amplitude),
                decimal_or_none(quote.change_percent),
                decimal_or_none(change_amount),
                decimal_or_none(quote.turnover),
                quote.source,
                Jsonb(bar_metadata),
            ),
        )
        await cursor.execute(
            """
                INSERT INTO quant.market_data_sync_state (
                  symbol, timeframe, adjustment, provider, first_ts, last_ts, row_count,
                  last_success_at, last_error, metadata, created_at, updated_at
                )
                SELECT
                  %s,
                  'daily',
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
                  AND timeframe = 'daily'
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
                adjustment,
                quote.source,
                Jsonb({"name": quote.name, "secid": quote.secid, "universe_id": universe_id}),
                symbol,
                adjustment,
                quote.source,
            ),
        )

    trade_date_text = local_trade_date.isoformat()
    return symbol, 1, trade_date_text, trade_date_text
