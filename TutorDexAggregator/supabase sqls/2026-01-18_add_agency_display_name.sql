-- Add agency_display_name to assignments and backfill from existing agency_name
ALTER TABLE IF EXISTS public.assignments
ADD COLUMN IF NOT EXISTS agency_display_name text;

-- Backfill existing rows where display name is missing
UPDATE public.assignments
SET agency_display_name = agency_name
WHERE agency_display_name IS NULL OR agency_display_name = '';

-- Optional: create index for faster filtering by agency_display_name
CREATE INDEX IF NOT EXISTS idx_assignments_agency_display_name ON public.assignments (lower(coalesce(agency_display_name, '')));
