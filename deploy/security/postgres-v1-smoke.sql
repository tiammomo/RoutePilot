\set ON_ERROR_STOP on

-- Run against a freshly initialized delivery image, before application migrations.
-- A missing extension, wrong major, or unusable native library must fail CI.
DO $smoke$
BEGIN
    IF current_setting('server_version_num')::integer / 10000 <> 17 THEN
        RAISE EXCEPTION 'The delivery image must use PostgreSQL 17';
    END IF;
    IF (SELECT extversion FROM pg_extension WHERE extname = 'postgis')
            IS DISTINCT FROM '3.6.4'
       OR (SELECT extversion FROM pg_extension WHERE extname = 'vector')
            IS DISTINCT FROM '0.8.5' THEN
        RAISE EXCEPTION 'Fresh databases must install the reviewed extension versions';
    END IF;
    IF ST_Distance(ST_Point(0, 0), ST_Point(3, 4)) IS DISTINCT FROM 5.0
       OR ST_SRID(ST_Transform(ST_SetSRID(ST_Point(1, 1), 4326), 3857))
            IS DISTINCT FROM 3857
       OR ('[0,0]'::vector <-> '[3,4]'::vector) IS DISTINCT FROM 5.0 THEN
        RAISE EXCEPTION 'Spatial and vector operations must work';
    END IF;
    IF (SELECT count(*) FROM pg_roles
        WHERE rolname IN ('routepilot_migrator', 'routepilot_api', 'routepilot_worker')
          AND rolcanlogin AND NOT rolsuper AND NOT rolbypassrls
          AND NOT rolcreatedb AND NOT rolcreaterole) <> 3
       OR NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'routepilot_outbox'
                      AND rolcanlogin AND NOT rolsuper AND rolbypassrls
                      AND NOT rolcreatedb AND NOT rolcreaterole) THEN
        RAISE EXCEPTION 'Init must preserve the four least-privilege roles';
    END IF;
END
$smoke$;

SELECT version(), postgis_full_version();
SELECT extname, extversion FROM pg_extension WHERE extname IN ('postgis', 'vector');
