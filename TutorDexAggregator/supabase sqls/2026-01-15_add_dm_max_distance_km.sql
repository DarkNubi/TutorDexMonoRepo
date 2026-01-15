-- Add per-tutor DM distance radius (km) preference.
-- Default is 5km (launch-simple).

alter table public.user_preferences
  add column if not exists dm_max_distance_km double precision not null default 5;

