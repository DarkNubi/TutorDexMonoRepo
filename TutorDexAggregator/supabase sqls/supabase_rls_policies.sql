-- RLS policy templates for TutorDex normalized schema.
-- Apply after creating tables (`TutorDexAggregator/supabase_schema_full.sql`).
-- IMPORTANT: Review before applying in production.

-- 1) Enable RLS
alter table public.assignments enable row level security;
alter table public.agencies enable row level security;
alter table public.users enable row level security;
alter table public.user_preferences enable row level security;
alter table public.analytics_events enable row level security;
alter table public.analytics_daily enable row level security;
alter table public.telegram_channels enable row level security;
alter table public.telegram_messages_raw enable row level security;
alter table public.telegram_extractions enable row level security;
alter table public.ingestion_runs enable row level security;
alter table public.ingestion_run_progress enable row level security;

-- 2) Public read access for open assignments (website uses anon key)
drop policy if exists "public_read_open_assignments" on public.assignments;
create policy "public_read_open_assignments"
on public.assignments
for select
to anon
using (status = 'open');

-- 3) Agencies: website doesn't need direct access (lock down)
drop policy if exists "no_agencies_access" on public.agencies;
create policy "no_agencies_access"
on public.agencies
for all
to anon
using (false)
with check (false);

-- 4) Users/preferences/events: keep locked down from anon (backend uses service role)
drop policy if exists "no_users_access" on public.users;
create policy "no_users_access"
on public.users
for all
to anon
using (false)
with check (false);

drop policy if exists "no_prefs_access" on public.user_preferences;
create policy "no_prefs_access"
on public.user_preferences
for all
to anon
using (false)
with check (false);

drop policy if exists "no_events_access" on public.analytics_events;
create policy "no_events_access"
on public.analytics_events
for all
to anon
using (false)
with check (false);

drop policy if exists "no_daily_access" on public.analytics_daily;
create policy "no_daily_access"
on public.analytics_daily
for all
to anon
using (false)
with check (false);

-- 5) Raw ingestion + extraction artifacts: always private (lock down from anon)
drop policy if exists "no_telegram_channels_access" on public.telegram_channels;
create policy "no_telegram_channels_access"
on public.telegram_channels
for all
to anon
using (false)
with check (false);

drop policy if exists "no_telegram_messages_raw_access" on public.telegram_messages_raw;
create policy "no_telegram_messages_raw_access"
on public.telegram_messages_raw
for all
to anon
using (false)
with check (false);

drop policy if exists "no_telegram_extractions_access" on public.telegram_extractions;
create policy "no_telegram_extractions_access"
on public.telegram_extractions
for all
to anon
using (false)
with check (false);

drop policy if exists "no_ingestion_runs_access" on public.ingestion_runs;
create policy "no_ingestion_runs_access"
on public.ingestion_runs
for all
to anon
using (false)
with check (false);

drop policy if exists "no_ingestion_run_progress_access" on public.ingestion_run_progress;
create policy "no_ingestion_run_progress_access"
on public.ingestion_run_progress
for all
to anon
using (false)
with check (false);