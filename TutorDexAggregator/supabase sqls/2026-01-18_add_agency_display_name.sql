-- Add agency_display_name + agency_telegram_channel_name to assignments and backfill from existing columns
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'assignments'
      AND column_name = 'agency_name'
  ) AND NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'assignments'
      AND column_name = 'agency_telegram_channel_name'
  ) THEN
    ALTER TABLE public.assignments
      RENAME COLUMN agency_name TO agency_telegram_channel_name;
  ELSIF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_schema = 'public'
      AND table_name = 'assignments'
      AND column_name = 'agency_name'
  ) THEN
    UPDATE public.assignments
      SET agency_telegram_channel_name = COALESCE(NULLIF(agency_telegram_channel_name, ''), agency_name)
      WHERE agency_telegram_channel_name IS NULL OR agency_telegram_channel_name = '';
    ALTER TABLE public.assignments DROP COLUMN IF EXISTS agency_name;
  END IF;
END $$;

ALTER TABLE IF EXISTS public.assignments
  ADD COLUMN IF NOT EXISTS agency_display_name text;

ALTER TABLE IF EXISTS public.assignments
  ADD COLUMN IF NOT EXISTS agency_telegram_channel_name text;

-- Backfill existing rows where display name is missing
UPDATE public.assignments
SET agency_display_name = COALESCE(NULLIF(agency_display_name, ''), agency_telegram_channel_name)
WHERE agency_display_name IS NULL OR agency_display_name = '';

-- Optional: create index for faster filtering by agency_display_name
CREATE INDEX IF NOT EXISTS idx_assignments_agency_display_name ON public.assignments (lower(coalesce(agency_display_name, '')));
