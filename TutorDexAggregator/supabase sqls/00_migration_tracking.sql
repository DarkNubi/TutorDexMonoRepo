-- Migration Tracking System
-- This table tracks which migrations have been applied to prevent duplicate execution

CREATE TABLE IF NOT EXISTS public.schema_migrations (
    id SERIAL PRIMARY KEY,
    migration_name TEXT UNIQUE NOT NULL,
    applied_at TIMESTAMPTZ DEFAULT NOW() NOT NULL,
    checksum TEXT,
    execution_time_ms INTEGER
);

-- Index for quick lookups
CREATE INDEX IF NOT EXISTS idx_schema_migrations_name ON public.schema_migrations(migration_name);
CREATE INDEX IF NOT EXISTS idx_schema_migrations_applied_at ON public.schema_migrations(applied_at DESC);

-- Add comment
COMMENT ON TABLE public.schema_migrations IS 'Tracks applied database migrations to ensure idempotent deployments';
COMMENT ON COLUMN public.schema_migrations.migration_name IS 'File name (stem) of the migration, e.g., 2025-12-22_add_postal_latlon';
COMMENT ON COLUMN public.schema_migrations.checksum IS 'Optional SHA256 hash of migration content for integrity verification';
COMMENT ON COLUMN public.schema_migrations.execution_time_ms IS 'Time taken to execute the migration in milliseconds';
