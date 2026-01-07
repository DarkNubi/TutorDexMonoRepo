-- Add postal_coords_estimated column to track when coordinates come from estimated postal code
-- Apply in Supabase SQL Editor (or psql) on an existing DB.

-- Add the column to assignments table
alter table public.assignments
  add column if not exists postal_coords_estimated boolean default false;

-- Add comment for documentation
comment on column public.assignments.postal_coords_estimated is 
  'True when postal_lat/postal_lon were derived from postal_code_estimated rather than explicit postal_code';
