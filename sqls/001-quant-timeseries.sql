-- QuantPilot component bootstrap SQL.
-- Safe to run repeatedly. Docker uses this on first database creation,
-- and `npm run db:init` can apply it to an existing local database.

CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE SCHEMA IF NOT EXISTS quant;

CREATE TABLE IF NOT EXISTS quant.stock_bars (
  symbol TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  timeframe TEXT NOT NULL,
  adjustment TEXT NOT NULL DEFAULT 'qfq',
  open NUMERIC(20, 8) NOT NULL,
  high NUMERIC(20, 8) NOT NULL,
  low NUMERIC(20, 8) NOT NULL,
  close NUMERIC(20, 8) NOT NULL,
  volume NUMERIC(24, 4) NOT NULL DEFAULT 0,
  amount NUMERIC(24, 4),
  provider TEXT NOT NULL DEFAULT 'unknown',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, timeframe, adjustment, ts)
);

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

SELECT create_hypertable('quant.stock_bars', 'ts', if_not_exists => TRUE, migrate_data => TRUE);

CREATE INDEX IF NOT EXISTS stock_bars_symbol_timeframe_adjustment_ts_desc_idx
  ON quant.stock_bars (symbol, timeframe, adjustment, ts DESC);

CREATE TABLE IF NOT EXISTS quant.stock_factors (
  symbol TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  factor_key TEXT NOT NULL,
  factor_value DOUBLE PRECISION NOT NULL,
  provider TEXT NOT NULL DEFAULT 'unknown',
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (symbol, factor_key, ts)
);

SELECT create_hypertable('quant.stock_factors', 'ts', if_not_exists => TRUE, migrate_data => TRUE);

CREATE INDEX IF NOT EXISTS stock_factors_factor_ts_desc_idx
  ON quant.stock_factors (factor_key, ts DESC);

CREATE TABLE IF NOT EXISTS quant.strategy_signals (
  strategy_id TEXT NOT NULL,
  symbol TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  signal TEXT NOT NULL,
  strength DOUBLE PRECISION,
  price NUMERIC(20, 8),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (strategy_id, symbol, ts)
);

SELECT create_hypertable('quant.strategy_signals', 'ts', if_not_exists => TRUE, migrate_data => TRUE);

CREATE INDEX IF NOT EXISTS strategy_signals_strategy_ts_desc_idx
  ON quant.strategy_signals (strategy_id, ts DESC);

CREATE TABLE IF NOT EXISTS quant.portfolio_snapshots (
  portfolio_id TEXT NOT NULL,
  ts TIMESTAMPTZ NOT NULL,
  total_value NUMERIC(24, 8) NOT NULL,
  cash NUMERIC(24, 8),
  exposure NUMERIC(24, 8),
  drawdown DOUBLE PRECISION,
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (portfolio_id, ts)
);

SELECT create_hypertable('quant.portfolio_snapshots', 'ts', if_not_exists => TRUE, migrate_data => TRUE);

CREATE INDEX IF NOT EXISTS portfolio_snapshots_portfolio_ts_desc_idx
  ON quant.portfolio_snapshots (portfolio_id, ts DESC);
