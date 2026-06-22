-- Run once by postgres on first start (via docker-entrypoint-initdb.d)
-- Creates a read-only analytics role used by DATABASE_URL_RO

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'analytics_ro') THEN
    CREATE ROLE analytics_ro WITH LOGIN PASSWORD 'analytics_ro_pass' NOSUPERUSER NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;

-- Grant read access on the three whitelisted tables (created by SQLAlchemy create_all)
-- These GRANTs are idempotent and safe to re-run.
GRANT CONNECT ON DATABASE devin_orchestrator TO analytics_ro;
GRANT USAGE ON SCHEMA public TO analytics_ro;

-- Future tables created by the devin user should also be accessible
ALTER DEFAULT PRIVILEGES FOR ROLE devin IN SCHEMA public
  GRANT SELECT ON TABLES TO analytics_ro;
