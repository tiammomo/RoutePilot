#!/usr/bin/env bash
set -Eeuo pipefail

: "${POSTGRES_DB:?POSTGRES_DB is required}"
: "${POSTGRES_USER:?POSTGRES_USER is required}"
: "${ROUTEPILOT_MIGRATION_DB_PASSWORD:?migration password is required}"
: "${ROUTEPILOT_API_DB_PASSWORD:?API password is required}"
: "${ROUTEPILOT_WORKER_DB_PASSWORD:?worker password is required}"
: "${ROUTEPILOT_OUTBOX_DB_PASSWORD:?outbox password is required}"

psql --set ON_ERROR_STOP=1 \
  --username "${POSTGRES_USER}" \
  --dbname "${POSTGRES_DB}" \
  --set database_name="${POSTGRES_DB}" \
  --set migration_password="${ROUTEPILOT_MIGRATION_DB_PASSWORD}" \
  --set api_password="${ROUTEPILOT_API_DB_PASSWORD}" \
  --set worker_password="${ROUTEPILOT_WORKER_DB_PASSWORD}" \
  --set outbox_password="${ROUTEPILOT_OUTBOX_DB_PASSWORD}" <<'EOSQL'
SELECT format(
  'CREATE ROLE routepilot_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %L',
  :'migration_password'
) WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'routepilot_migrator') \gexec

SELECT format(
  'CREATE ROLE routepilot_api LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %L',
  :'api_password'
) WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'routepilot_api') \gexec

SELECT format(
  'CREATE ROLE routepilot_worker LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS PASSWORD %L',
  :'worker_password'
) WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'routepilot_worker') \gexec

-- This role can cross tenant RLS only for the one outbox table granted after
-- migration. It receives no privileges on tenant business tables.
SELECT format(
  'CREATE ROLE routepilot_outbox LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT BYPASSRLS PASSWORD %L',
  :'outbox_password'
) WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'routepilot_outbox') \gexec

ALTER ROLE routepilot_migrator PASSWORD :'migration_password';
ALTER ROLE routepilot_api PASSWORD :'api_password';
ALTER ROLE routepilot_worker PASSWORD :'worker_password';
ALTER ROLE routepilot_outbox PASSWORD :'outbox_password';

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT CONNECT ON DATABASE :"database_name" TO
  routepilot_migrator, routepilot_api, routepilot_worker, routepilot_outbox;
GRANT USAGE, CREATE ON SCHEMA public TO routepilot_migrator;
GRANT USAGE ON SCHEMA public TO routepilot_api, routepilot_worker, routepilot_outbox;

CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS postgis;
EOSQL
