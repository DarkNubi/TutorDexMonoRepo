-- ================================================================================
-- Migration: Duplicate Assignment Detection
-- Date: 2026-01-09
-- Purpose: Add schema for detecting and tracking duplicate assignments across agencies
-- 
-- This migration adds:
-- 1. assignment_duplicate_groups table (track duplicate groups)
-- 2. duplicate_detection_config table (tunable algorithm parameters)
-- 3. Columns to assignments table (duplicate_group_id, is_primary_in_group, duplicate_confidence_score)
-- 4. Indices for performance
-- 
-- Algorithm weights (validated against production data):
-- - Postal code: 50 points (PRIMARY signal)
-- - Subjects: 35 points (STRONG signal)
-- - Levels: 25 points (STRONG signal)
-- - Rate: 15 points (MODERATE signal)
-- - Temporal: 10 points (SUPPLEMENTARY signal)
-- - Assignment code: 10 points (WEAK signal - agency-specific formats)
-- - Time availability: 5 points (WEAK signal)
-- 
-- Detection threshold: ≥70 = likely duplicate
-- ================================================================================

-- ================================================================================
-- 1. Create duplicate groups table
-- ================================================================================

CREATE TABLE IF NOT EXISTS public.assignment_duplicate_groups (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Primary assignment (best quality, earliest timestamp, or highest agency reputation)
    primary_assignment_id BIGINT REFERENCES public.assignments(id) ON DELETE SET NULL,
    
    -- Group metadata
    member_count INT NOT NULL DEFAULT 2,
    avg_confidence_score DECIMAL(5,2),
    status TEXT NOT NULL DEFAULT 'active',
    
    -- Algorithm version for traceability
    detection_algorithm_version TEXT NOT NULL DEFAULT 'v1_revised',
    
    -- Additional metadata (member IDs, detection timestamp, etc.)
    meta JSONB DEFAULT '{}'::jsonb
);

COMMENT ON TABLE public.assignment_duplicate_groups IS 
    'Tracks groups of duplicate assignments posted by different agencies';

COMMENT ON COLUMN public.assignment_duplicate_groups.primary_assignment_id IS 
    'Assignment selected as primary (best parse quality, earliest timestamp, agency reputation)';

COMMENT ON COLUMN public.assignment_duplicate_groups.avg_confidence_score IS 
    'Average similarity score across all members in the group (0-100)';

COMMENT ON COLUMN public.assignment_duplicate_groups.detection_algorithm_version IS 
    'Version of detection algorithm used (for monitoring algorithm changes over time)';

-- Indices for duplicate groups
CREATE INDEX IF NOT EXISTS duplicate_groups_primary_idx 
    ON public.assignment_duplicate_groups(primary_assignment_id)
    WHERE primary_assignment_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS duplicate_groups_status_idx 
    ON public.assignment_duplicate_groups(status) 
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS duplicate_groups_created_at_idx 
    ON public.assignment_duplicate_groups(created_at DESC);

-- ================================================================================
-- 2. Add duplicate-related columns to assignments table
-- ================================================================================

ALTER TABLE public.assignments 
    ADD COLUMN IF NOT EXISTS duplicate_group_id BIGINT 
        REFERENCES public.assignment_duplicate_groups(id) ON DELETE SET NULL;

ALTER TABLE public.assignments 
    ADD COLUMN IF NOT EXISTS is_primary_in_group BOOLEAN NOT NULL DEFAULT TRUE;

ALTER TABLE public.assignments 
    ADD COLUMN IF NOT EXISTS duplicate_confidence_score DECIMAL(5,2);

COMMENT ON COLUMN public.assignments.duplicate_group_id IS 
    'ID of duplicate group this assignment belongs to (NULL if no duplicates detected)';

COMMENT ON COLUMN public.assignments.is_primary_in_group IS 
    'Whether this assignment is the primary/representative in its duplicate group';

COMMENT ON COLUMN public.assignments.duplicate_confidence_score IS 
    'Similarity score (0-100) between this assignment and the primary in its group';

-- Indices for duplicate columns
CREATE INDEX IF NOT EXISTS assignments_duplicate_group_idx 
    ON public.assignments(duplicate_group_id) 
    WHERE duplicate_group_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS assignments_is_primary_idx 
    ON public.assignments(is_primary_in_group, status) 
    WHERE is_primary_in_group = TRUE AND status = 'open';

CREATE INDEX IF NOT EXISTS assignments_duplicate_confidence_idx 
    ON public.assignments(duplicate_confidence_score DESC) 
    WHERE duplicate_confidence_score IS NOT NULL;

-- Composite index for efficient duplicate queries
CREATE INDEX IF NOT EXISTS assignments_duplicate_lookup_idx 
    ON public.assignments(duplicate_group_id, is_primary_in_group, status)
    WHERE duplicate_group_id IS NOT NULL;

-- ================================================================================
-- 3. Configuration table for tunable parameters
-- ================================================================================

CREATE TABLE IF NOT EXISTS public.duplicate_detection_config (
    id BIGSERIAL PRIMARY KEY,
    config_key TEXT NOT NULL UNIQUE,
    config_value JSONB NOT NULL,
    description TEXT,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT
);

COMMENT ON TABLE public.duplicate_detection_config IS 
    'Configuration parameters for duplicate detection algorithm (tunable without code changes)';

-- Initial configuration (REVISED weights based on validation)
INSERT INTO public.duplicate_detection_config (config_key, config_value, description) 
VALUES
    ('enabled', 
     'true',
     'Master switch for duplicate detection'),
    
    ('thresholds', 
     '{"high_confidence": 90, "medium_confidence": 70, "low_confidence": 55}'::jsonb,
     'Similarity score thresholds for duplicate detection (high=90, medium=70, low=55)'),
    
    ('weights', 
     '{"postal": 50, "subjects": 35, "levels": 25, "rate": 15, "temporal": 10, "assignment_code": 10, "time": 5}'::jsonb,
     'Signal weights for similarity calculation (REVISED: postal code is PRIMARY signal)'),
    
    ('time_window_days', 
     '7'::jsonb,
     'Only check assignments from last N days (performance optimization)'),
    
    ('detection_batch_size', 
     '100'::jsonb,
     'Maximum number of assignments to check per detection run'),
    
    ('fuzzy_postal_tolerance', 
     '2'::jsonb,
     'Allow postal codes within ±N digits to match (fuzzy matching)')
ON CONFLICT (config_key) DO NOTHING;

-- ================================================================================
-- 4. Helper function: Get duplicate configuration
-- ================================================================================

CREATE OR REPLACE FUNCTION public.get_duplicate_config(p_config_key TEXT)
RETURNS JSONB
LANGUAGE plpgsql
STABLE
AS $$
DECLARE
    v_config_value JSONB;
BEGIN
    SELECT config_value 
    INTO v_config_value
    FROM public.duplicate_detection_config
    WHERE config_key = p_config_key;
    
    RETURN v_config_value;
END;
$$;

COMMENT ON FUNCTION public.get_duplicate_config IS 
    'Retrieve duplicate detection configuration value by key';

-- ================================================================================
-- 5. Helper function: Get assignments in duplicate group
-- ================================================================================

CREATE OR REPLACE FUNCTION public.get_duplicate_group_members(p_group_id BIGINT)
RETURNS TABLE (
    assignment_id BIGINT,
    agency_name TEXT,
    assignment_code TEXT,
    is_primary BOOLEAN,
    confidence_score DECIMAL(5,2),
    published_at TIMESTAMPTZ
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.id as assignment_id,
        a.agency_name,
        a.assignment_code,
        a.is_primary_in_group as is_primary,
        a.duplicate_confidence_score as confidence_score,
        a.published_at
    FROM public.assignments a
    WHERE a.duplicate_group_id = p_group_id
        AND a.status = 'open'
    ORDER BY 
        a.is_primary_in_group DESC,
        a.duplicate_confidence_score DESC NULLS LAST,
        a.published_at ASC;
END;
$$;

COMMENT ON FUNCTION public.get_duplicate_group_members IS 
    'Retrieve all assignments in a duplicate group (sorted by primary status, confidence, and time)';

-- ================================================================================
-- 6. Update timestamp trigger for duplicate groups
-- ================================================================================

CREATE OR REPLACE FUNCTION public.update_duplicate_group_timestamp()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS duplicate_groups_update_timestamp ON public.assignment_duplicate_groups;

CREATE TRIGGER duplicate_groups_update_timestamp
    BEFORE UPDATE ON public.assignment_duplicate_groups
    FOR EACH ROW
    EXECUTE FUNCTION public.update_duplicate_group_timestamp();

-- ================================================================================
-- 7. Validation queries (run after migration to verify)
-- ================================================================================

-- Verify tables created
-- SELECT 
--     schemaname,
--     tablename,
--     tableowner
-- FROM pg_tables
-- WHERE schemaname = 'public' 
--     AND tablename IN ('assignment_duplicate_groups', 'duplicate_detection_config')
-- ORDER BY tablename;

-- Verify columns added to assignments
-- SELECT 
--     column_name,
--     data_type,
--     is_nullable,
--     column_default
-- FROM information_schema.columns
-- WHERE table_schema = 'public'
--     AND table_name = 'assignments'
--     AND column_name IN ('duplicate_group_id', 'is_primary_in_group', 'duplicate_confidence_score')
-- ORDER BY column_name;

-- Verify indices created
-- SELECT 
--     indexname,
--     indexdef
-- FROM pg_indexes
-- WHERE schemaname = 'public'
--     AND (
--         tablename = 'assignment_duplicate_groups'
--         OR (tablename = 'assignments' AND indexname LIKE '%duplicate%')
--     )
-- ORDER BY tablename, indexname;

-- Verify configuration loaded
-- SELECT 
--     config_key,
--     config_value,
--     description
-- FROM public.duplicate_detection_config
-- ORDER BY config_key;

-- ================================================================================
-- Migration complete
-- ================================================================================
