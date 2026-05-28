-- QuantPilot strategy research platform bootstrap SQL.
-- This file is intentionally idempotent so first-use setup can run it repeatedly.

CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE SCHEMA IF NOT EXISTS quant;

ALTER TABLE quant.stock_bars
  ADD COLUMN IF NOT EXISTS adjustment TEXT NOT NULL DEFAULT 'qfq';

DO $$
DECLARE
  has_adjustment_in_pk BOOLEAN;
BEGIN
  SELECT EXISTS (
    SELECT 1
    FROM pg_constraint constraint_info
    JOIN pg_class table_info
      ON table_info.oid = constraint_info.conrelid
    JOIN pg_namespace schema_info
      ON schema_info.oid = table_info.relnamespace
    JOIN unnest(constraint_info.conkey) WITH ORDINALITY column_key(attnum, ord)
      ON TRUE
    JOIN pg_attribute column_info
      ON column_info.attrelid = table_info.oid
     AND column_info.attnum = column_key.attnum
    WHERE schema_info.nspname = 'quant'
      AND table_info.relname = 'stock_bars'
      AND constraint_info.contype = 'p'
      AND column_info.attname = 'adjustment'
  ) INTO has_adjustment_in_pk;

  IF NOT has_adjustment_in_pk THEN
    IF EXISTS (
      SELECT 1
      FROM pg_constraint constraint_info
      JOIN pg_class table_info
        ON table_info.oid = constraint_info.conrelid
      JOIN pg_namespace schema_info
        ON schema_info.oid = table_info.relnamespace
      WHERE schema_info.nspname = 'quant'
        AND table_info.relname = 'stock_bars'
        AND constraint_info.conname = 'stock_bars_pkey'
    ) THEN
      ALTER TABLE quant.stock_bars DROP CONSTRAINT stock_bars_pkey;
    END IF;

    ALTER TABLE quant.stock_bars
      ADD CONSTRAINT stock_bars_pkey PRIMARY KEY (symbol, timeframe, adjustment, ts);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS stock_bars_symbol_timeframe_adjustment_ts_desc_idx
  ON quant.stock_bars (symbol, timeframe, adjustment, ts DESC);

CREATE TABLE IF NOT EXISTS quant.securities (
  symbol TEXT PRIMARY KEY,
  code TEXT NOT NULL,
  name TEXT,
  exchange TEXT NOT NULL DEFAULT 'UNKNOWN',
  asset_type TEXT NOT NULL DEFAULT 'stock',
  currency TEXT NOT NULL DEFAULT 'CNY',
  timezone TEXT NOT NULL DEFAULT 'Asia/Shanghai',
  secid TEXT,
  provider TEXT NOT NULL DEFAULT 'eastmoney',
  listed_at DATE,
  status TEXT NOT NULL DEFAULT 'active',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS securities_provider_secid_idx
  ON quant.securities (provider, secid)
  WHERE secid IS NOT NULL;

CREATE TABLE IF NOT EXISTS quant.security_universes (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT,
  status TEXT NOT NULL DEFAULT 'active',
  source TEXT NOT NULL DEFAULT 'manual',
  tags JSONB NOT NULL DEFAULT '[]'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS quant.security_universe_members (
  universe_id TEXT NOT NULL REFERENCES quant.security_universes(id) ON DELETE CASCADE,
  symbol TEXT NOT NULL REFERENCES quant.securities(symbol) ON DELETE CASCADE,
  role TEXT NOT NULL DEFAULT 'member',
  weight NUMERIC(12, 8),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  added_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (universe_id, symbol)
);

CREATE INDEX IF NOT EXISTS security_universe_members_symbol_idx
  ON quant.security_universe_members (symbol);

CREATE TABLE IF NOT EXISTS quant.market_data_ingestion_jobs (
  id TEXT PRIMARY KEY,
  universe_id TEXT REFERENCES quant.security_universes(id) ON DELETE SET NULL,
  provider TEXT NOT NULL DEFAULT 'eastmoney',
  timeframe TEXT NOT NULL DEFAULT 'daily',
  adjustment TEXT NOT NULL DEFAULT 'qfq',
  requested_start DATE,
  requested_end DATE,
  status TEXT NOT NULL DEFAULT 'queued',
  total_symbols INT NOT NULL DEFAULT 0,
  completed_symbols INT NOT NULL DEFAULT 0,
  failed_symbols INT NOT NULL DEFAULT 0,
  rows_received INT NOT NULL DEFAULT 0,
  rows_upserted INT NOT NULL DEFAULT 0,
  error TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS market_data_ingestion_jobs_created_idx
  ON quant.market_data_ingestion_jobs (created_at DESC);

CREATE TABLE IF NOT EXISTS quant.market_data_sync_state (
  symbol TEXT NOT NULL REFERENCES quant.securities(symbol) ON DELETE CASCADE,
  timeframe TEXT NOT NULL DEFAULT 'daily',
  adjustment TEXT NOT NULL DEFAULT 'qfq',
  provider TEXT NOT NULL DEFAULT 'eastmoney',
  first_ts TIMESTAMPTZ,
  last_ts TIMESTAMPTZ,
  row_count INT NOT NULL DEFAULT 0,
  last_success_at TIMESTAMPTZ,
  last_error TEXT,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, timeframe, adjustment, provider)
);

CREATE INDEX IF NOT EXISTS market_data_sync_state_last_ts_idx
  ON quant.market_data_sync_state (last_ts DESC);

CREATE TABLE IF NOT EXISTS quant.backtest_runs (
  id TEXT PRIMARY KEY,
  universe_id TEXT REFERENCES quant.security_universes(id) ON DELETE SET NULL,
  strategy_id TEXT NOT NULL,
  strategy_name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  timeframe TEXT NOT NULL DEFAULT 'daily',
  adjustment TEXT NOT NULL DEFAULT 'qfq',
  parameters JSONB NOT NULL DEFAULT '{}'::jsonb,
  metrics JSONB NOT NULL DEFAULT '{}'::jsonb,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS backtest_runs_created_idx
  ON quant.backtest_runs (created_at DESC);

CREATE TABLE IF NOT EXISTS quant.backtest_orders (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL REFERENCES quant.backtest_runs(id) ON DELETE CASCADE,
  symbol TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  side TEXT NOT NULL,
  quantity NUMERIC(24, 8) NOT NULL,
  price NUMERIC(20, 8) NOT NULL,
  amount NUMERIC(24, 8) NOT NULL,
  fee NUMERIC(20, 8) NOT NULL DEFAULT 0,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS backtest_orders_run_ts_idx
  ON quant.backtest_orders (run_id, ts);

CREATE OR REPLACE VIEW quant.market_data_coverage AS
SELECT
  bars.symbol,
  bars.timeframe,
  bars.adjustment,
  bars.provider,
  min(bars.ts) AS first_ts,
  max(bars.ts) AS last_ts,
  count(*)::INT AS row_count
FROM quant.stock_bars bars
GROUP BY bars.symbol, bars.timeframe, bars.adjustment, bars.provider;

INSERT INTO quant.securities (symbol, code, name, exchange, asset_type, secid, provider, metadata)
VALUES
  ('002156.SZ', '002156', '通富微电', 'SZ', 'stock', '0.002156', 'eastmoney', '{"sector_hint":"semiconductor"}'::jsonb),
  ('002555.SZ', '002555', '三七互娱', 'SZ', 'stock', '0.002555', 'eastmoney', '{"sector_hint":"gaming"}'::jsonb),
  ('002624.SZ', '002624', '完美世界', 'SZ', 'stock', '0.002624', 'eastmoney', '{"sector_hint":"gaming"}'::jsonb),
  ('601398.SH', '601398', '工商银行', 'SH', 'stock', '1.601398', 'eastmoney', '{"sector_hint":"bank"}'::jsonb),
  ('600916.SH', '600916', '中国黄金', 'SH', 'stock', '1.600916', 'eastmoney', '{"sector_hint":"gold-retail"}'::jsonb)
ON CONFLICT (symbol) DO UPDATE SET
  code = EXCLUDED.code,
  name = EXCLUDED.name,
  exchange = EXCLUDED.exchange,
  asset_type = EXCLUDED.asset_type,
  secid = EXCLUDED.secid,
  provider = EXCLUDED.provider,
  metadata = quant.securities.metadata || EXCLUDED.metadata,
  updated_at = now();

INSERT INTO quant.security_universes (id, name, description, status, source, tags, metadata)
VALUES (
  'a-share-sample-research-pool',
  'A 股示例研究池',
  '用于策略平台打通本地行情覆盖、数据质量检查和回测链路的默认股票池。',
  'active',
  'seed',
  '["A股","东方财富","策略回测"]'::jsonb,
  '{"default_timeframe":"daily","default_adjustment":"qfq","provider":"eastmoney","lookback_years":5,"suggested_limit":1260}'::jsonb
)
ON CONFLICT (id) DO UPDATE SET
  name = EXCLUDED.name,
  description = EXCLUDED.description,
  status = EXCLUDED.status,
  source = EXCLUDED.source,
  tags = EXCLUDED.tags,
  metadata = quant.security_universes.metadata || EXCLUDED.metadata,
  updated_at = now();

INSERT INTO quant.security_universe_members (universe_id, symbol, role, weight, metadata)
VALUES
  ('a-share-sample-research-pool', '002156.SZ', 'member', 0.20, '{"order":1}'::jsonb),
  ('a-share-sample-research-pool', '002555.SZ', 'member', 0.20, '{"order":2}'::jsonb),
  ('a-share-sample-research-pool', '002624.SZ', 'member', 0.20, '{"order":3}'::jsonb),
  ('a-share-sample-research-pool', '601398.SH', 'member', 0.20, '{"order":4}'::jsonb),
  ('a-share-sample-research-pool', '600916.SH', 'member', 0.20, '{"order":5}'::jsonb)
ON CONFLICT (universe_id, symbol) DO UPDATE SET
  role = EXCLUDED.role,
  weight = EXCLUDED.weight,
  metadata = quant.security_universe_members.metadata || EXCLUDED.metadata;
