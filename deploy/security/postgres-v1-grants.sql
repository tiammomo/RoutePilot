-- Run as routepilot_migrator after every Alembic upgrade. This file grants only
-- runtime DML and forces RLS on V1 tables; it does not grant schema creation.
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO routepilot_api, routepilot_worker, routepilot_outbox;

DO $routepilot_runtime_grants$
DECLARE
  relation_name text;
BEGIN
  FOR relation_name IN
    SELECT c.relname
      FROM pg_class AS c
      JOIN pg_namespace AS n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind IN ('r', 'p')
       AND c.relname LIKE 'v1\_%' ESCAPE '\'
  LOOP
    EXECUTE format('REVOKE ALL ON TABLE %I FROM PUBLIC', relation_name);
    EXECUTE format('ALTER TABLE %I FORCE ROW LEVEL SECURITY', relation_name);
    EXECUTE format(
      'GRANT SELECT, INSERT, UPDATE ON TABLE %I TO routepilot_api, routepilot_worker',
      relation_name
    );
  END LOOP;
END
$routepilot_runtime_grants$;

-- A BYPASSRLS credential is acceptable only with this single-table grant. It
-- cannot read Trip, Run, Artifact, knowledge, or public-event content.
REVOKE ALL ON ALL TABLES IN SCHEMA public FROM routepilot_outbox;
GRANT SELECT, UPDATE ON TABLE v1_outbox_events TO routepilot_outbox;

-- Public share routing is deliberately non-enumerable to runtime roles. The
-- API may register a newly-created opaque public ID, but tenant resolution is
-- possible only through the exact-match SECURITY DEFINER function.
REVOKE ALL ON TABLE routepilot_share_public_lookup FROM
  routepilot_api, routepilot_worker, routepilot_outbox;
GRANT INSERT ON TABLE routepilot_share_public_lookup TO routepilot_api;
REVOKE ALL ON TABLE v1_shares, v1_share_snapshots, v1_share_sessions,
  v1_share_idempotency_keys FROM routepilot_worker;
GRANT DELETE ON TABLE v1_share_sessions TO routepilot_api;
REVOKE ALL ON FUNCTION routepilot_resolve_share_tenant(text) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION routepilot_resolve_share_tenant(text) TO routepilot_api;

DO $routepilot_sequence_grants$
DECLARE
  sequence_name text;
BEGIN
  FOR sequence_name IN
    SELECT c.relname
      FROM pg_class AS c
      JOIN pg_namespace AS n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind = 'S'
       AND c.relname LIKE 'v1\_%' ESCAPE '\'
  LOOP
    EXECUTE format(
      'GRANT USAGE, SELECT ON SEQUENCE %I TO routepilot_api, routepilot_worker',
      sequence_name
    );
  END LOOP;
END
$routepilot_sequence_grants$;
