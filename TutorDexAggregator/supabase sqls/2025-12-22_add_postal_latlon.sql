-- Adds postal geocoding fields (SG postal code -> lat/lon).
-- Apply in Supabase SQL Editor (or psql) on an existing DB.

alter table if exists public.assignments
  add column if not exists postal_lat double precision,
  add column if not exists postal_lon double precision;

alter table if exists public.user_preferences
  add column if not exists postal_code text,
  add column if not exists postal_lat double precision,
  add column if not exists postal_lon double precision;

