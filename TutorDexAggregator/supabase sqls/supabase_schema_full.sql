-- Supabase schema (normalized) for TutorDex.
-- Apply in Supabase SQL Editor.
-- Notes:
-- - This file creates: agencies, assignments, users, user_preferences, analytics_events, analytics_daily,
--   plus private ingestion/artifact tables: telegram_channels, telegram_messages_raw, telegram_extractions,
--   ingestion_runs, ingestion_run_progress.
-- - Consider enabling RLS before exposing any tables directly to clients.

create table if not exists public.agencies (
  id bigserial primary key,
  name text not null,
  channel_link text,
  created_at timestamptz not null default now()
);

-- Additive upgrades for older DBs (avoid failures when creating indexes/functions).
alter table public.agencies
  add column if not exists name text;

alter table public.agencies
  add column if not exists channel_link text;

alter table public.agencies
  add column if not exists created_at timestamptz;

create unique index if not exists agencies_channel_link_uq
  on public.agencies (channel_link)
  where channel_link is not null;

create unique index if not exists agencies_name_uq
  on public.agencies (name);

-- --------------------------------------------------------------------------------
-- Public assignments listing table (materialized from latest extraction output)
--
-- Source of truth for extraction remains:
-- - `public.telegram_messages_raw` (raw post)
-- - `public.telegram_extractions.canonical_json` (v2 display schema)
-- - `public.telegram_extractions.meta` (deterministic signals + diagnostics)
--
-- `public.assignments` is a denormalized, query-friendly projection used by the website/backend.
-- --------------------------------------------------------------------------------

create table if not exists public.assignments (
  id bigserial primary key,
  agency_id bigint references public.agencies(id) on delete set null,
  external_id text not null,

  -- denormalized convenience fields (avoid joins for the website)
  agency_name text,
  agency_link text,

  channel_id text,
  message_id text,
  message_link text,
  raw_text text,

  -- v2 display fields (from `telegram_extractions.canonical_json`)
  assignment_code text,
  academic_display_text text,
  learning_mode text,
  learning_mode_raw_text text,

  address text[],
  postal_code text[],
  postal_code_estimated text[],
  postal_lat double precision,
  postal_lon double precision,
  nearest_mrt text[],
  region text,
  nearest_mrt_computed text,
  nearest_mrt_computed_line text,
  nearest_mrt_computed_distance_m int,
  lesson_schedule text[],
  start_date text,

  time_availability_note text,
  time_availability_explicit jsonb,
  time_availability_estimated jsonb,

  rate_min int,
  rate_max int,
  rate_raw_text text,
  tutor_types jsonb,
  rate_breakdown jsonb,
  additional_remarks text,

  -- deterministic signals rollups (from `telegram_extractions.meta.signals`)
  signals_subjects text[] not null default '{}',
  signals_levels text[] not null default '{}',
  signals_specific_student_levels text[] not null default '{}',
  signals_streams text[] not null default '{}',
  signals_academic_requests jsonb,
  signals_confidence_flags jsonb,

  -- v2 subject taxonomy (stable codes + general rollups)
  subjects_canonical text[] not null default '{}',
  subjects_general text[] not null default '{}',
  canonicalization_version int not null default 2,
  canonicalization_debug jsonb,

  canonical_json jsonb,
  meta jsonb,
  parse_quality_score int not null default 0,

  created_at timestamptz not null default now(),
  published_at timestamptz,
  source_last_seen timestamptz,
  last_seen timestamptz not null default now(),
  bump_count int not null default 0,
  freshness_tier text not null default 'green',
  status text not null default 'open',

  -- duplicate detection fields (added 2026-01-09)
  duplicate_group_id bigint,
  is_primary_in_group boolean not null default true,
  duplicate_confidence_score decimal(5,2)
);

-- Additive upgrades for older DBs (avoid failures when creating indexes/functions).
alter table public.assignments
  add column if not exists agency_id bigint;

alter table public.assignments
  add column if not exists external_id text;

alter table public.assignments
  add column if not exists published_at timestamptz;

alter table public.assignments
  add column if not exists source_last_seen timestamptz;

alter table public.assignments
  add column if not exists agency_name text;

alter table public.assignments
  add column if not exists agency_link text;

alter table public.assignments
  add column if not exists channel_id text;

alter table public.assignments
  add column if not exists message_id text;

alter table public.assignments
  add column if not exists message_link text;

alter table public.assignments
  add column if not exists raw_text text;

alter table public.assignments
  add column if not exists assignment_code text;

alter table public.assignments
  add column if not exists academic_display_text text;

alter table public.assignments
  add column if not exists learning_mode text;

alter table public.assignments
  add column if not exists learning_mode_raw_text text;

alter table public.assignments
  add column if not exists address text[];

alter table public.assignments
  add column if not exists postal_code text[];

alter table public.assignments
  add column if not exists postal_code_estimated text[];

alter table public.assignments
  add column if not exists postal_lat double precision;

alter table public.assignments
  add column if not exists postal_lon double precision;

alter table public.assignments
  add column if not exists nearest_mrt text[];

alter table public.assignments
  add column if not exists region text;

alter table public.assignments
  add column if not exists nearest_mrt_computed text;

alter table public.assignments
  add column if not exists nearest_mrt_computed_line text;

alter table public.assignments
  add column if not exists nearest_mrt_computed_distance_m int;

alter table public.assignments
  add column if not exists lesson_schedule text[];

alter table public.assignments
  add column if not exists start_date text;

alter table public.assignments
  add column if not exists time_availability_note text;

alter table public.assignments
  add column if not exists time_availability_explicit jsonb;

alter table public.assignments
  add column if not exists time_availability_estimated jsonb;

alter table public.assignments
  add column if not exists rate_min integer;

alter table public.assignments
  add column if not exists rate_max integer;

alter table public.assignments
  add column if not exists rate_raw_text text;

alter table public.assignments
  add column if not exists tutor_types jsonb;

alter table public.assignments
  add column if not exists rate_breakdown jsonb;

alter table public.assignments
  add column if not exists additional_remarks text;

alter table public.assignments
  add column if not exists signals_subjects text[];

alter table public.assignments
  add column if not exists signals_levels text[];

alter table public.assignments
  add column if not exists signals_specific_student_levels text[];

alter table public.assignments
  add column if not exists signals_streams text[];

alter table public.assignments
  add column if not exists signals_academic_requests jsonb;

alter table public.assignments
  add column if not exists signals_confidence_flags jsonb;

alter table public.assignments
  add column if not exists subjects_canonical text[];

alter table public.assignments
  add column if not exists subjects_general text[];

alter table public.assignments
  add column if not exists canonicalization_version integer;

alter table public.assignments
  add column if not exists canonicalization_debug jsonb;

alter table public.assignments
  add column if not exists canonical_json jsonb;

alter table public.assignments
  add column if not exists meta jsonb;

alter table public.assignments
  add column if not exists parse_quality_score integer;

alter table public.assignments
  add column if not exists created_at timestamptz;

alter table public.assignments
  add column if not exists last_seen timestamptz;

alter table public.assignments
  add column if not exists bump_count integer;

alter table public.assignments
  add column if not exists freshness_tier text;

alter table public.assignments
  add column if not exists status text;

-- duplicate detection columns (added 2026-01-09)
alter table public.assignments
  add column if not exists duplicate_group_id bigint;

alter table public.assignments
  add column if not exists is_primary_in_group boolean;

alter table public.assignments
  add column if not exists duplicate_confidence_score decimal(5,2);

create unique index if not exists assignments_agency_external_id_uq
  on public.assignments (agency_id, external_id);

create index if not exists assignments_status_created_at_idx
  on public.assignments (status, created_at desc);

create index if not exists assignments_status_last_seen_idx
  on public.assignments (status, last_seen desc);

-- Sorting + tiering support (newer migrations)
create index if not exists assignments_source_last_seen_idx
  on public.assignments (source_last_seen desc);

create index if not exists assignments_published_at_idx
  on public.assignments (published_at desc);

create index if not exists assignments_open_published_at_idx
  on public.assignments (published_at desc, id desc)
  where status = 'open';

create index if not exists assignments_parse_quality_score_idx
  on public.assignments (parse_quality_score desc);

create index if not exists assignments_status_agency_name_idx
  on public.assignments (status, agency_name);

create index if not exists assignments_status_learning_mode_idx
  on public.assignments (status, learning_mode);

create index if not exists assignments_status_region_idx
  on public.assignments (status, region);

create index if not exists assignments_status_nearest_mrt_computed_idx
  on public.assignments (status, nearest_mrt_computed);

create index if not exists assignments_signals_subjects_gin
  on public.assignments using gin (signals_subjects);

create index if not exists assignments_signals_levels_gin
  on public.assignments using gin (signals_levels);

create index if not exists assignments_signals_specific_levels_gin
  on public.assignments using gin (signals_specific_student_levels);

create index if not exists assignments_signals_streams_gin
  on public.assignments using gin (signals_streams);

-- duplicate detection indices (added 2026-01-09)
create index if not exists assignments_duplicate_group_idx
  on public.assignments (duplicate_group_id)
  where duplicate_group_id is not null;

create index if not exists assignments_is_primary_idx
  on public.assignments (is_primary_in_group, status)
  where is_primary_in_group = true and status = 'open';

create index if not exists assignments_duplicate_confidence_idx
  on public.assignments (duplicate_confidence_score desc)
  where duplicate_confidence_score is not null;

create index if not exists assignments_duplicate_lookup_idx
  on public.assignments (duplicate_group_id, is_primary_in_group, status)
  where duplicate_group_id is not null;

-- --------------------------------------------------------------------------------
-- Duplicate detection tables (added 2026-01-09)
-- --------------------------------------------------------------------------------

create table if not exists public.assignment_duplicate_groups (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  primary_assignment_id bigint references public.assignments(id) on delete set null,
  member_count int not null default 2,
  avg_confidence_score decimal(5,2),
  status text not null default 'active',
  detection_algorithm_version text not null default 'v1_revised',
  meta jsonb default '{}'::jsonb
);

create index if not exists duplicate_groups_primary_idx
  on public.assignment_duplicate_groups (primary_assignment_id)
  where primary_assignment_id is not null;

create index if not exists duplicate_groups_status_idx
  on public.assignment_duplicate_groups (status)
  where status = 'active';

create index if not exists duplicate_groups_created_at_idx
  on public.assignment_duplicate_groups (created_at desc);

create table if not exists public.duplicate_detection_config (
  id bigserial primary key,
  config_key text not null unique,
  config_value jsonb not null,
  description text,
  updated_at timestamptz not null default now(),
  updated_by text
);

-- Initial configuration (validated defaults). Safe to re-run.
insert into public.duplicate_detection_config (config_key, config_value, description)
values
  ('enabled', 'true', 'Master switch for duplicate detection'),
  ('thresholds', '{"high_confidence": 90, "medium_confidence": 70, "low_confidence": 55}'::jsonb, 'Similarity score thresholds for duplicate detection'),
  ('weights', '{"postal": 50, "subjects": 35, "levels": 25, "rate": 15, "temporal": 10, "assignment_code": 10, "time": 5}'::jsonb, 'Signal weights for similarity calculation'),
  ('time_window_days', '7'::jsonb, 'Only check assignments from last N days (performance optimization)'),
  ('detection_batch_size', '100'::jsonb, 'Maximum number of assignments to check per detection run'),
  ('fuzzy_postal_tolerance', '2'::jsonb, 'Allow postal codes within ±N digits to match (fuzzy matching)')
on conflict (config_key) do nothing;

create or replace function public.get_duplicate_config(p_config_key text)
returns jsonb
language plpgsql
stable
as $$
declare
  v_config_value jsonb;
begin
  select config_value
  into v_config_value
  from public.duplicate_detection_config
  where config_key = p_config_key;

  return v_config_value;
end;
$$;

create or replace function public.get_duplicate_group_members(p_group_id bigint)
returns table (
  assignment_id bigint,
  agency_name text,
  assignment_code text,
  is_primary boolean,
  confidence_score decimal(5,2),
  published_at timestamptz
)
language plpgsql
stable
as $$
begin
  return query
  select
    a.id as assignment_id,
    a.agency_name,
    a.assignment_code,
    a.is_primary_in_group as is_primary,
    a.duplicate_confidence_score as confidence_score,
    a.published_at
  from public.assignments a
  where a.duplicate_group_id = p_group_id
    and a.status = 'open'
  order by
    a.is_primary_in_group desc,
    a.duplicate_confidence_score desc nulls last,
    a.published_at asc;
end;
$$;

create or replace function public.update_duplicate_group_timestamp()
returns trigger
language plpgsql
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists duplicate_groups_update_timestamp on public.assignment_duplicate_groups;
create trigger duplicate_groups_update_timestamp
before update on public.assignment_duplicate_groups
for each row
execute function public.update_duplicate_group_timestamp();

-- Add foreign key constraint for duplicate_group_id (needs to be after table creation)
do $$
begin
  if not exists (
    select 1 from information_schema.table_constraints
    where constraint_name = 'assignments_duplicate_group_id_fkey'
      and table_name = 'assignments'
  ) then
    alter table public.assignments
      add constraint assignments_duplicate_group_id_fkey
      foreign key (duplicate_group_id)
      references public.assignment_duplicate_groups(id)
      on delete set null;
  end if;
end $$;

-- GIN index to accelerate queries filtering by tutor_types[].canonical using jsonb containment
create index if not exists assignments_tutor_types_gin
  on public.assignments using gin (tutor_types jsonb_path_ops);

-- --------------------------------------------------------------------------------
-- RPC (function) compatibility
--
-- Postgres cannot `CREATE OR REPLACE` a function when the `RETURNS TABLE (...)` OUT parameter list changes.
-- To make this schema file re-runnable across DB states, we proactively drop any existing overloads of the
-- affected RPCs before recreating them.
--
-- Note: we use `CASCADE` to avoid failures if something depends on the old signature (rare, but possible).
-- --------------------------------------------------------------------------------
do $$
declare
  r record;
begin
  for r in
    select
      n.nspname as schema_name,
      p.proname as func_name,
      pg_get_function_identity_arguments(p.oid) as args
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname in (
        'list_open_assignments',
        'list_open_assignments_v2',
        'open_assignment_facets'
      )
  loop
    execute format('drop function if exists %I.%I(%s) cascade;', r.schema_name, r.func_name, r.args);
  end loop;
end $$;

-- Website pagination + facets (server-side filtering)
create or replace function public.list_open_assignments(
  p_limit integer default 50,
  p_cursor_last_seen timestamptz default null,
  p_cursor_id bigint default null,
  p_level text default null,
  p_specific_student_level text default null,
  p_subject text default null,
  p_subject_general text default null,
  p_subject_canonical text default null,
  p_agency_name text default null,
  p_learning_mode text default null,
  p_location_query text default null,
  p_tutor_type text default null,
  p_min_rate integer default null
)
returns table(
  id bigint,
  external_id text,
  message_link text,
  agency_name text,
  learning_mode text,
  assignment_code text,
  academic_display_text text,
  address text[],
  postal_code text[],
  postal_code_estimated text[],
  nearest_mrt text[],
  region text,
  nearest_mrt_computed text,
  nearest_mrt_computed_line text,
  nearest_mrt_computed_distance_m int,
  lesson_schedule text[],
  start_date text,
  time_availability_note text,
  rate_min integer,
  rate_max integer,
  rate_raw_text text,
  tutor_types jsonb,
  rate_breakdown jsonb,
  signals_subjects text[],
  signals_levels text[],
  signals_specific_student_levels text[],
  subjects_canonical text[],
  subjects_general text[],
  canonicalization_version int,
  status text,
  created_at timestamptz,
  published_at timestamptz,
  source_last_seen timestamptz,
  last_seen timestamptz,
  freshness_tier text,
  total_count bigint
)
language sql
stable
set search_path = public, pg_temp
as $$
with base as (
  select
    a.*,
    coalesce(a.published_at, a.created_at, a.last_seen) as _sort_ts,
    lower(
      concat_ws(
        ' ',
        nullif(array_to_string(a.address, ' '), ''),
        nullif(array_to_string(a.postal_code, ' '), ''),
        nullif(array_to_string(a.postal_code_estimated, ' '), ''),
        nullif(array_to_string(a.nearest_mrt, ' '), '')
      )
    ) as _loc
  from public.assignments a
  where a.status = 'open'
),
filtered as (
  select *
  from base
  where (p_level is null or p_level = any(signals_levels))
    and (p_specific_student_level is null or p_specific_student_level = any(signals_specific_student_levels))
    and (p_subject_general is null or p_subject_general = any(subjects_general))
    and (p_subject_canonical is null or p_subject_canonical = any(subjects_canonical))
    and (
      p_subject is null
      or p_subject = any(signals_subjects)
      or p_subject = any(subjects_canonical)
      or p_subject = any(subjects_general)
    )
    and (p_agency_name is null or agency_name = p_agency_name)
    and (p_learning_mode is null or learning_mode = p_learning_mode)
    and (
      p_location_query is null
      or btrim(p_location_query) = ''
      or (
        lower(btrim(p_location_query)) = 'online'
        and lower(coalesce(learning_mode, '')) like '%online%'
      )
      or (
        replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') in ('north', 'east', 'west', 'central', 'north-east', 'northeast')
        and coalesce(region, '') = (
          case
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') = 'north' then 'North'
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') = 'east' then 'East'
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') = 'west' then 'West'
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') = 'central' then 'Central'
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') in ('north-east', 'northeast') then 'North-East'
            else ''
          end
        )
      )
      or _loc like '%' || lower(p_location_query) || '%'
    )
    and (p_min_rate is null or (rate_min is not null and rate_min >= p_min_rate))
    and (p_tutor_type is null or tutor_types @> jsonb_build_array(jsonb_build_object('canonical', p_tutor_type)))
    and (
      p_cursor_last_seen is null
      or (_sort_ts, id) < (p_cursor_last_seen, p_cursor_id)
    )
)
select
  id,
  external_id,
  message_link,
  agency_name,
  learning_mode,
  assignment_code,
  academic_display_text,
  address,
  postal_code,
  postal_code_estimated,
  nearest_mrt,
  region,
  nearest_mrt_computed,
  nearest_mrt_computed_line,
  nearest_mrt_computed_distance_m,
  lesson_schedule,
  start_date,
  time_availability_note,
  rate_min,
  rate_max,
  rate_raw_text,
  tutor_types,
  rate_breakdown,
  signals_subjects,
  signals_levels,
  signals_specific_student_levels,
  subjects_canonical,
  subjects_general,
  canonicalization_version,
  status,
  created_at,
  published_at,
  source_last_seen,
  last_seen,
  freshness_tier,
  count(*) over() as total_count
from filtered
order by _sort_ts desc, id desc
limit greatest(1, least(p_limit, 200));
$$;

-- Distance-aware listing (DB-side ordering). Requires postal_lat/postal_lon on assignments.
-- See: `TutorDexAggregator/supabase sqls/2025-12-29_assignments_distance_sort.sql`
create or replace function public.list_open_assignments_v2(
  p_limit integer default 50,
  p_sort text default 'newest',
  p_tutor_lat double precision default null,
  p_tutor_lon double precision default null,

  p_cursor_last_seen timestamptz default null,
  p_cursor_id bigint default null,
  p_cursor_distance_km double precision default null,

  p_level text default null,
  p_specific_student_level text default null,
  p_subject text default null,
  p_subject_general text default null,
  p_subject_canonical text default null,
  p_agency_name text default null,
  p_learning_mode text default null,
  p_location_query text default null,
  p_tutor_type text default null,
  p_min_rate integer default null,
  p_show_duplicates boolean default true  -- NEW: filter duplicates
)
returns table(
  id bigint,
  external_id text,
  message_link text,
  agency_name text,
  learning_mode text,
  assignment_code text,
  academic_display_text text,
  address text[],
  postal_code text[],
  postal_code_estimated text[],
  nearest_mrt text[],
  region text,
  nearest_mrt_computed text,
  nearest_mrt_computed_line text,
  nearest_mrt_computed_distance_m int,
  lesson_schedule text[],
  start_date text,
  time_availability_note text,
  rate_min integer,
  rate_max integer,
  rate_raw_text text,
  tutor_types jsonb,
  rate_breakdown jsonb,
  signals_subjects text[],
  signals_levels text[],
  signals_specific_student_levels text[],
  subjects_canonical text[],
  subjects_general text[],
  canonicalization_version int,
  status text,
  created_at timestamptz,
  published_at timestamptz,
  source_last_seen timestamptz,
  last_seen timestamptz,
  freshness_tier text,
  distance_km double precision,
  distance_sort_key double precision,
  postal_coords_estimated boolean,
  total_count bigint
)
language sql
stable
set search_path = public, pg_temp
as $$
with base as (
  select
    a.*,
    coalesce(a.published_at, a.created_at, a.last_seen) as _sort_ts,
    lower(
      concat_ws(
        ' ',
        nullif(array_to_string(a.address, ' '), ''),
        nullif(array_to_string(a.postal_code, ' '), ''),
        nullif(array_to_string(a.postal_code_estimated, ' '), ''),
        nullif(array_to_string(a.nearest_mrt, ' '), '')
      )
    ) as _loc
  from public.assignments a
  where a.status = 'open'
),
filtered as (
  select *
  from base
  where (p_level is null or p_level = any(signals_levels))
    and (p_specific_student_level is null or p_specific_student_level = any(signals_specific_student_levels))
    and (p_subject_general is null or p_subject_general = any(subjects_general))
    and (p_subject_canonical is null or p_subject_canonical = any(subjects_canonical))
    and (
      p_subject is null
      or p_subject = any(signals_subjects)
      or p_subject = any(subjects_canonical)
      or p_subject = any(subjects_general)
    )
    and (p_agency_name is null or agency_name = p_agency_name)
    and (p_learning_mode is null or learning_mode = p_learning_mode)
    and (
      p_location_query is null
      or btrim(p_location_query) = ''
      or (
        lower(btrim(p_location_query)) = 'online'
        and lower(coalesce(learning_mode, '')) like '%online%'
      )
      or (
        replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') in ('north', 'east', 'west', 'central', 'north-east', 'northeast')
        and coalesce(region, '') = (
          case
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') = 'north' then 'North'
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') = 'east' then 'East'
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') = 'west' then 'West'
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') = 'central' then 'Central'
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') in ('north-east', 'northeast') then 'North-East'
            else ''
          end
        )
      )
      or _loc like '%' || lower(p_location_query) || '%'
    )
    and (p_min_rate is null or (rate_min is not null and rate_min >= p_min_rate))
    -- NEW: Duplicate filter
    and (
      coalesce(p_show_duplicates, true) = true  -- Show all if true
      or is_primary_in_group = true  -- Only show primary if false
    )
    -- NEW: Tutor type filter - expects tutor_types to be array of objects with 'canonical' property
    -- Format: [{"canonical": "full-timer", "original": "FT", "agency": null, "confidence": 0.9}, ...]
    and (p_tutor_type is null or tutor_types @> jsonb_build_array(jsonb_build_object('canonical', p_tutor_type)))
),
scored as (
  select
    f.*,
    case
      when p_tutor_lat is not null
        and p_tutor_lon is not null
        and f.postal_lat is not null
        and f.postal_lon is not null
      then
        2.0 * 6371.0 * asin(
          sqrt(
            pow(sin(radians((f.postal_lat - p_tutor_lat) / 2.0)), 2)
            +
            cos(radians(p_tutor_lat)) * cos(radians(f.postal_lat))
            * pow(sin(radians((f.postal_lon - p_tutor_lon) / 2.0)), 2)
          )
        )
      else null
    end as distance_km
  from filtered f
),
scored2 as (
  select
    s.*,
    coalesce(s.distance_km, 1e9) as distance_sort_key
  from scored s
),
paged as (
  select
    s.*
  from scored2 s
  where (
    (coalesce(p_sort, 'newest') <> 'distance' and (
      p_cursor_last_seen is null
      or (s._sort_ts, s.id) < (p_cursor_last_seen, p_cursor_id)
    ))
    or
    (coalesce(p_sort, 'newest') = 'distance' and (
      p_cursor_distance_km is null
      or s.distance_sort_key > p_cursor_distance_km
      or (s.distance_sort_key = p_cursor_distance_km and s.last_seen < p_cursor_last_seen)
      or (s.distance_sort_key = p_cursor_distance_km and s.last_seen = p_cursor_last_seen and s.id < p_cursor_id)
    ))
  )
)
select
  id,
  external_id,
  message_link,
  agency_name,
  learning_mode,
  assignment_code,
  academic_display_text,
  address,
  postal_code,
  postal_code_estimated,
  nearest_mrt,
  region,
  nearest_mrt_computed,
  nearest_mrt_computed_line,
  nearest_mrt_computed_distance_m,
  lesson_schedule,
  start_date,
  time_availability_note,
  rate_min,
  rate_max,
  rate_raw_text,
  tutor_types,
  rate_breakdown,
  signals_subjects,
  signals_levels,
  signals_specific_student_levels,
  subjects_canonical,
  subjects_general,
  canonicalization_version,
  status,
  created_at,
  published_at,
  source_last_seen,
  last_seen,
  freshness_tier,
  distance_km,
  distance_sort_key,
  coalesce(postal_coords_estimated, false) as postal_coords_estimated,
  count(*) over() as total_count
from paged
order by
  case when coalesce(p_sort, 'newest') = 'distance' then distance_sort_key else null end asc,
  case when coalesce(p_sort, 'newest') = 'distance' then last_seen else null end desc,
  case when coalesce(p_sort, 'newest') = 'distance' then id else null end desc,
  _sort_ts desc,
  id desc
limit greatest(1, least(p_limit, 200));
$$;

create or replace function public.open_assignment_facets(
  p_level text default null,
  p_specific_student_level text default null,
  p_subject text default null,
  p_subject_general text default null,
  p_subject_canonical text default null,
  p_agency_name text default null,
  p_learning_mode text default null,
  p_location_query text default null,
  p_tutor_type text default null,
  p_min_rate integer default null
)
returns jsonb
language sql
stable
set search_path = public, pg_temp
as $$
with base as (
  select
    a.*,
    lower(
      concat_ws(
        ' ',
        nullif(array_to_string(a.address, ' '), ''),
        nullif(array_to_string(a.postal_code, ' '), ''),
        nullif(array_to_string(a.postal_code_estimated, ' '), ''),
        nullif(array_to_string(a.nearest_mrt, ' '), '')
      )
    ) as _loc
  from public.assignments a
  where a.status = 'open'
),
filtered as (
  select *
  from base
  where (p_level is null or p_level = any(signals_levels))
    and (p_specific_student_level is null or p_specific_student_level = any(signals_specific_student_levels))
    and (p_subject_general is null or p_subject_general = any(subjects_general))
    and (p_subject_canonical is null or p_subject_canonical = any(subjects_canonical))
    and (
      p_subject is null
      or p_subject = any(signals_subjects)
      or p_subject = any(subjects_canonical)
      or p_subject = any(subjects_general)
    )
    and (p_agency_name is null or agency_name = p_agency_name)
    and (p_learning_mode is null or learning_mode = p_learning_mode)
    and (
      p_location_query is null
      or btrim(p_location_query) = ''
      or (
        lower(btrim(p_location_query)) = 'online'
        and lower(coalesce(learning_mode, '')) like '%online%'
      )
      or (
        replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') in ('north', 'east', 'west', 'central', 'north-east', 'northeast')
        and coalesce(region, '') = (
          case
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') = 'north' then 'North'
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') = 'east' then 'East'
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') = 'west' then 'West'
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') = 'central' then 'Central'
            when replace(replace(lower(btrim(p_location_query)), ' ', ''), '_', '-') in ('north-east', 'northeast') then 'North-East'
            else ''
          end
        )
      )
      or _loc like '%' || lower(p_location_query) || '%'
    )
      and (p_min_rate is null or (rate_min is not null and rate_min >= p_min_rate))
      and (p_tutor_type is null or tutor_types @> jsonb_build_array(jsonb_build_object('canonical', p_tutor_type)))
)
select jsonb_build_object(
  'total', (select count(*) from filtered),
  'levels', (
    select coalesce(
      jsonb_agg(jsonb_build_object('value', level, 'count', c) order by c desc, level asc),
      '[]'::jsonb
    )
    from (
      select level, count(*) as c
      from (
        select distinct id, unnest(signals_levels) as level
        from filtered
      ) d
      where level is not null and btrim(level) <> ''
      group by level
    ) s
  ),
  'specific_levels', (
    select coalesce(
      jsonb_agg(jsonb_build_object('value', specific_student_level, 'count', c) order by c desc, specific_student_level asc),
      '[]'::jsonb
    )
    from (
      select specific_student_level, count(*) as c
      from (
        select distinct id, unnest(signals_specific_student_levels) as specific_student_level
        from filtered
      ) d
      where specific_student_level is not null and btrim(specific_student_level) <> ''
      group by specific_student_level
    ) s
  ),
  -- Legacy: subject label facets from `signals_subjects` (kept for back-compat).
  'subjects', (
    select coalesce(
      jsonb_agg(jsonb_build_object('value', subject, 'count', c) order by c desc, subject asc),
      '[]'::jsonb
    )
    from (
      select subject, count(*) as c
      from (
        select distinct id, unnest(signals_subjects) as subject
        from filtered
      ) d
      where subject is not null and btrim(subject) <> ''
      group by subject
    ) s
  ),
  -- v2: general category code facets.
  'subjects_general', (
    select coalesce(
      jsonb_agg(jsonb_build_object('value', subject_general, 'count', c) order by c desc, subject_general asc),
      '[]'::jsonb
    )
    from (
      select subject_general, count(*) as c
      from (
        select distinct id, unnest(subjects_general) as subject_general
        from filtered
      ) d
      where subject_general is not null and btrim(subject_general) <> ''
      group by subject_general
    ) s
  ),
  -- v2: canonical subject code facets.
  'subjects_canonical', (
    select coalesce(
      jsonb_agg(jsonb_build_object('value', subject_canonical, 'count', c) order by c desc, subject_canonical asc),
      '[]'::jsonb
    )
    from (
      select subject_canonical, count(*) as c
      from (
        select distinct id, unnest(subjects_canonical) as subject_canonical
        from filtered
      ) d
      where subject_canonical is not null and btrim(subject_canonical) <> ''
      group by subject_canonical
    ) s
  ),
  'agencies', (
    select coalesce(
      jsonb_agg(jsonb_build_object('value', agency_name, 'count', c) order by c desc, agency_name asc),
      '[]'::jsonb
    )
    from (
      select agency_name, count(*) as c
      from filtered
      where agency_name is not null and btrim(agency_name) <> ''
      group by agency_name
    ) s
  ),
  'learning_modes', (
    select coalesce(
      jsonb_agg(jsonb_build_object('value', learning_mode, 'count', c) order by c desc, learning_mode asc),
      '[]'::jsonb
    )
    from (
      select learning_mode, count(*) as c
      from filtered
      where learning_mode is not null and btrim(learning_mode) <> ''
      group by learning_mode
    ) s
  )
  , 'tutor_types', (
    select coalesce(
      jsonb_agg(jsonb_build_object('value', t, 'count', c) order by c desc, t asc),
      '[]'::jsonb
    )
    from (
      select t, count(*) as c
      from (
        select distinct id, jsonb_array_elements(tutor_types) ->> 'canonical' as t
        from filtered
      ) d
      where t is not null and btrim(t) <> ''
      group by t
    ) s
  )
);
$$;

create table if not exists public.users (
  id bigserial primary key,
  firebase_uid text not null unique,
  name text,
  email text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.users
  add column if not exists firebase_uid text;

alter table public.users
  add column if not exists name text;

alter table public.users
  add column if not exists email text;

alter table public.users
  add column if not exists created_at timestamptz;

alter table public.users
  add column if not exists updated_at timestamptz;

-- Note: `firebase_uid text not null unique` already creates a unique index (typically `users_firebase_uid_key`).
-- Avoid creating a second identical index.
drop index if exists public.users_firebase_uid_uq;

create table if not exists public.user_preferences (
  id bigserial primary key,
  user_id bigint not null unique references public.users(id) on delete cascade,
  subjects text[],
  levels text[],
  subject_pairs jsonb,
  assignment_types text[],
  tutor_kinds text[],
  learning_modes text[],
  postal_code text,
  postal_lat double precision,
  postal_lon double precision,
  desired_assignments_per_day integer default 10,
  updated_at timestamptz not null default now()
);

alter table public.user_preferences
  add column if not exists user_id bigint;

alter table public.user_preferences
  add column if not exists subjects text[];

alter table public.user_preferences
  add column if not exists levels text[];

alter table public.user_preferences
  add column if not exists subject_pairs jsonb;

alter table public.user_preferences
  add column if not exists assignment_types text[];

alter table public.user_preferences
  add column if not exists tutor_kinds text[];

alter table public.user_preferences
  add column if not exists learning_modes text[];

alter table public.user_preferences
  add column if not exists postal_code text;

alter table public.user_preferences
  add column if not exists postal_lat double precision;

alter table public.user_preferences
  add column if not exists postal_lon double precision;

alter table public.user_preferences
  add column if not exists desired_assignments_per_day integer;

alter table public.user_preferences
  add column if not exists updated_at timestamptz;

-- Note: `user_id ... unique` already creates a unique index (typically `user_preferences_user_id_key`).
-- Avoid creating a second identical index.
drop index if exists public.user_preferences_user_id_uq;

create table if not exists public.tutor_assignment_ratings (
  id bigserial primary key,
  user_id bigint not null references public.users(id) on delete cascade,
  assignment_id bigint not null references public.assignments(id) on delete cascade,
  rating_score double precision not null,
  distance_km double precision,
  rate_min integer,
  rate_max integer,
  match_score integer not null,
  sent_at timestamptz not null default now(),
  created_at timestamptz not null default now(),
  unique(user_id, assignment_id)
);

create index if not exists tutor_assignment_ratings_user_id_sent_at_idx
  on public.tutor_assignment_ratings(user_id, sent_at desc);

create index if not exists tutor_assignment_ratings_assignment_id_idx
  on public.tutor_assignment_ratings(assignment_id);

create index if not exists tutor_assignment_ratings_user_id_rating_idx
  on public.tutor_assignment_ratings(user_id, rating_score desc);

-- Calculate adaptive rating threshold for a tutor based on historical assignment ratings.
create or replace function public.calculate_tutor_rating_threshold(
  p_user_id bigint,
  p_desired_per_day integer default 10,
  p_lookback_days integer default 7
) returns double precision as $$
declare
  v_count integer;
  v_threshold double precision;
  v_total_days double precision;
  v_target_count integer;
  v_percentile double precision;
begin
  select extract(epoch from (max(sent_at) - min(sent_at))) / 86400.0
  into v_total_days
  from public.tutor_assignment_ratings
  where user_id = p_user_id
    and sent_at >= now() - (p_lookback_days || ' days')::interval;

  if v_total_days is null or v_total_days < 0.5 then
    return 0.0;
  end if;

  select count(*) into v_count
  from public.tutor_assignment_ratings
  where user_id = p_user_id
    and sent_at >= now() - (p_lookback_days || ' days')::interval;

  if v_count = 0 then
    return 0.0;
  end if;

  v_target_count := greatest(1, round(p_desired_per_day * v_total_days));
  if v_count > v_target_count then
    v_percentile := 1.0 - (v_target_count::double precision / v_count::double precision);
  else
    v_percentile := 0.0;
  end if;

  select percentile_cont(v_percentile) within group (order by rating_score)
  into v_threshold
  from public.tutor_assignment_ratings
  where user_id = p_user_id
    and sent_at >= now() - (p_lookback_days || ' days')::interval;

  return coalesce(v_threshold, 0.0);
end;
$$ language plpgsql stable;

-- Calculate average rate from past assignments shown to tutor (for rate bonus calculation).
create or replace function public.get_tutor_avg_rate(
  p_user_id bigint,
  p_lookback_days integer default 30
) returns double precision as $$
declare
  v_avg_rate double precision;
begin
  select avg((rate_min + coalesce(rate_max, rate_min)) / 2.0)
  into v_avg_rate
  from public.tutor_assignment_ratings
  where user_id = p_user_id
    and sent_at >= now() - (p_lookback_days || ' days')::interval
    and rate_min is not null
    and rate_min > 0;

  return coalesce(v_avg_rate, 0.0);
end;
$$ language plpgsql stable;

create table if not exists public.analytics_events (
  id bigserial primary key,
  assignment_id bigint references public.assignments(id) on delete set null,
  user_id bigint references public.users(id) on delete set null,
  event_type text not null,
  event_time timestamptz not null default now(),
  meta jsonb
);

alter table public.analytics_events
  add column if not exists assignment_id bigint;

alter table public.analytics_events
  add column if not exists user_id bigint;

alter table public.analytics_events
  add column if not exists event_type text;

alter table public.analytics_events
  add column if not exists event_time timestamptz;

alter table public.analytics_events
  add column if not exists meta jsonb;

create index if not exists analytics_events_time_idx
  on public.analytics_events (event_time desc);

-- Covering indexes for FK columns (perf advisor).
create index if not exists analytics_events_assignment_id_idx
  on public.analytics_events (assignment_id);

create index if not exists analytics_events_user_id_idx
  on public.analytics_events (user_id);

create table if not exists public.analytics_daily (
  id bigserial primary key,
  day date not null,
  assignment_id bigint references public.assignments(id) on delete set null,
  event_type text not null,
  count int not null default 0,
  created_at timestamptz not null default now()
);

alter table public.analytics_daily
  add column if not exists day date;

alter table public.analytics_daily
  add column if not exists assignment_id bigint;

alter table public.analytics_daily
  add column if not exists event_type text;

alter table public.analytics_daily
  add column if not exists count integer;

alter table public.analytics_daily
  add column if not exists created_at timestamptz;

create unique index if not exists analytics_daily_uq
  on public.analytics_daily (day, assignment_id, event_type);

-- Covering index for FK column (perf advisor).
create index if not exists analytics_daily_assignment_id_idx
  on public.analytics_daily (assignment_id);

-- --------------------------------------------------------------------------------
-- Private ingestion + extraction artifacts (lock down with RLS; not for anon access)
-- --------------------------------------------------------------------------------

create table if not exists public.telegram_channels (
  id bigserial primary key,
  channel_link text not null,
  channel_id text,
  title text,
  created_at timestamptz not null default now()
);

alter table public.telegram_channels
  add column if not exists channel_link text;

alter table public.telegram_channels
  add column if not exists channel_id text;

alter table public.telegram_channels
  add column if not exists title text;

alter table public.telegram_channels
  add column if not exists created_at timestamptz;

create unique index if not exists telegram_channels_channel_link_uq
  on public.telegram_channels (channel_link);

create index if not exists telegram_channels_channel_id_idx
  on public.telegram_channels (channel_id);

create table if not exists public.telegram_messages_raw (
  id bigserial primary key,
  channel_link text not null,
  channel_id text,
  message_id text not null,
  message_date timestamptz not null,
  sender_id text,
  is_forward boolean not null default false,
  is_reply boolean not null default false,
  raw_text text,
  entities_json jsonb,
  media_json jsonb,
  views int,
  forwards int,
  reply_count int,
  edit_date timestamptz,
  message_json jsonb not null,
  first_seen_at timestamptz not null default now(),
  last_seen_at timestamptz not null default now(),
  deleted_at timestamptz
);

alter table public.telegram_messages_raw
  add column if not exists channel_link text;

alter table public.telegram_messages_raw
  add column if not exists channel_id text;

alter table public.telegram_messages_raw
  add column if not exists message_id text;

alter table public.telegram_messages_raw
  add column if not exists message_date timestamptz;

alter table public.telegram_messages_raw
  add column if not exists sender_id text;

alter table public.telegram_messages_raw
  add column if not exists is_forward boolean;

alter table public.telegram_messages_raw
  add column if not exists is_reply boolean;

alter table public.telegram_messages_raw
  add column if not exists raw_text text;

alter table public.telegram_messages_raw
  add column if not exists entities_json jsonb;

alter table public.telegram_messages_raw
  add column if not exists media_json jsonb;

alter table public.telegram_messages_raw
  add column if not exists views integer;

alter table public.telegram_messages_raw
  add column if not exists forwards integer;

alter table public.telegram_messages_raw
  add column if not exists reply_count integer;

alter table public.telegram_messages_raw
  add column if not exists edit_date timestamptz;

alter table public.telegram_messages_raw
  add column if not exists message_json jsonb;

alter table public.telegram_messages_raw
  add column if not exists first_seen_at timestamptz;

alter table public.telegram_messages_raw
  add column if not exists last_seen_at timestamptz;

alter table public.telegram_messages_raw
  add column if not exists deleted_at timestamptz;

create unique index if not exists telegram_messages_raw_uq
  on public.telegram_messages_raw (channel_link, message_id);

create index if not exists telegram_messages_raw_channel_date_idx
  on public.telegram_messages_raw (channel_link, message_date desc);

create index if not exists telegram_messages_raw_last_seen_idx
  on public.telegram_messages_raw (last_seen_at desc);

create index if not exists telegram_messages_raw_deleted_idx
  on public.telegram_messages_raw (deleted_at)
  where deleted_at is not null;

create table if not exists public.telegram_extractions (
  id bigserial primary key,
  raw_id bigint not null references public.telegram_messages_raw(id) on delete cascade,
  pipeline_version text not null,
  llm_model text,
  status text not null,
  channel_link text,
  message_id text,
  message_date timestamptz,
  canonical_json jsonb,
  error_json jsonb,
  meta jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.telegram_extractions
  add column if not exists raw_id bigint;

alter table public.telegram_extractions
  add column if not exists pipeline_version text;

alter table public.telegram_extractions
  add column if not exists llm_model text;

alter table public.telegram_extractions
  add column if not exists status text;

alter table public.telegram_extractions
  add column if not exists channel_link text;

alter table public.telegram_extractions
  add column if not exists message_id text;

alter table public.telegram_extractions
  add column if not exists message_date timestamptz;

alter table public.telegram_extractions
  add column if not exists canonical_json jsonb;

alter table public.telegram_extractions
  add column if not exists error_json jsonb;

alter table public.telegram_extractions
  add column if not exists meta jsonb;

alter table public.telegram_extractions
  add column if not exists created_at timestamptz;

alter table public.telegram_extractions
  add column if not exists updated_at timestamptz;

create unique index if not exists telegram_extractions_raw_version_uq
  on public.telegram_extractions (raw_id, pipeline_version);

create index if not exists telegram_extractions_status_idx
  on public.telegram_extractions (status);

create index if not exists telegram_extractions_pipeline_version_idx
  on public.telegram_extractions (pipeline_version);

create index if not exists telegram_extractions_channel_date_idx
  on public.telegram_extractions (channel_link, message_date desc);

create index if not exists telegram_extractions_created_at_idx
  on public.telegram_extractions (created_at desc);

create table if not exists public.ingestion_runs (
  id bigserial primary key,
  run_type text not null,
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running',
  channels jsonb,
  meta jsonb
);

alter table public.ingestion_runs
  add column if not exists run_type text;

alter table public.ingestion_runs
  add column if not exists started_at timestamptz;

alter table public.ingestion_runs
  add column if not exists finished_at timestamptz;

alter table public.ingestion_runs
  add column if not exists status text;

alter table public.ingestion_runs
  add column if not exists channels jsonb;

alter table public.ingestion_runs
  add column if not exists meta jsonb;

create index if not exists ingestion_runs_started_at_idx
  on public.ingestion_runs (started_at desc);

create table if not exists public.ingestion_run_progress (
  id bigserial primary key,
  run_id bigint not null references public.ingestion_runs(id) on delete cascade,
  channel_link text not null,
  last_message_id text,
  last_message_date timestamptz,
  scanned_count int not null default 0,
  inserted_count int not null default 0,
  updated_count int not null default 0,
  error_count int not null default 0,
  updated_at timestamptz not null default now()
);

alter table public.ingestion_run_progress
  add column if not exists run_id bigint;

alter table public.ingestion_run_progress
  add column if not exists channel_link text;

alter table public.ingestion_run_progress
  add column if not exists last_message_id text;

alter table public.ingestion_run_progress
  add column if not exists last_message_date timestamptz;

alter table public.ingestion_run_progress
  add column if not exists scanned_count integer;

alter table public.ingestion_run_progress
  add column if not exists inserted_count integer;

alter table public.ingestion_run_progress
  add column if not exists updated_count integer;

alter table public.ingestion_run_progress
  add column if not exists error_count integer;

alter table public.ingestion_run_progress
  add column if not exists updated_at timestamptz;

create unique index if not exists ingestion_run_progress_uq
  on public.ingestion_run_progress (run_id, channel_link);

-- Click tracking tables (fresh installs)
create table if not exists public.assignment_clicks (
  external_id text primary key,
  original_url text not null,
  clicks integer not null default 0,
  last_click_at timestamptz
);

alter table public.assignment_clicks
  add column if not exists external_id text;

alter table public.assignment_clicks
  add column if not exists original_url text;

alter table public.assignment_clicks
  add column if not exists clicks integer;

alter table public.assignment_clicks
  add column if not exists last_click_at timestamptz;

create table if not exists public.broadcast_messages (
  external_id text primary key references public.assignment_clicks(external_id) on delete cascade,
  original_url text not null,
  sent_chat_id bigint not null,
  sent_message_id bigint not null,
  message_html text not null,
  last_rendered_clicks integer,
  last_edited_at timestamptz,
  deleted_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.broadcast_messages
  add column if not exists external_id text;

alter table public.broadcast_messages
  add column if not exists original_url text;

alter table public.broadcast_messages
  add column if not exists sent_chat_id bigint;

alter table public.broadcast_messages
  add column if not exists sent_message_id bigint;

alter table public.broadcast_messages
  add column if not exists message_html text;

alter table public.broadcast_messages
  add column if not exists last_rendered_clicks integer;

alter table public.broadcast_messages
  add column if not exists last_edited_at timestamptz;

alter table public.broadcast_messages
  add column if not exists deleted_at timestamptz;

alter table public.broadcast_messages
  add column if not exists created_at timestamptz;

alter table public.broadcast_messages
  add column if not exists updated_at timestamptz;

create unique index if not exists broadcast_messages_chat_msg_uidx
  on public.broadcast_messages(sent_chat_id, sent_message_id);

-- Click-count incrementer used by the backend click beacon tracking.
create or replace function public.increment_assignment_clicks(
  p_external_id text,
  p_original_url text,
  p_delta integer default 1
)
returns integer
language plpgsql
set search_path = public, pg_temp
as $$
declare
  v_clicks integer;
begin
  insert into public.assignment_clicks(external_id, original_url, clicks, last_click_at)
  values (p_external_id, p_original_url, greatest(0, p_delta), now())
  on conflict (external_id) do update
    set clicks = public.assignment_clicks.clicks + greatest(0, p_delta),
        last_click_at = now(),
        original_url = excluded.original_url
  returning clicks into v_clicks;

  update public.broadcast_messages
    set updated_at = now()
    where external_id = p_external_id;

  return v_clicks;
end;
$$;

-- --------------------------------------------------------------------------------
-- Row Level Security (RLS)
-- --------------------------------------------------------------------------------
-- Default posture: deny all access for anon/authenticated unless you explicitly add policies.
-- Service-role requests (backend) are allowed.

alter table if exists public.agencies enable row level security;
alter table if exists public.assignments enable row level security;
alter table if exists public.users enable row level security;
alter table if exists public.user_preferences enable row level security;
alter table if exists public.analytics_events enable row level security;
alter table if exists public.analytics_daily enable row level security;
alter table if exists public.telegram_channels enable row level security;
alter table if exists public.telegram_messages_raw enable row level security;
alter table if exists public.telegram_extractions enable row level security;
alter table if exists public.ingestion_runs enable row level security;
alter table if exists public.ingestion_run_progress enable row level security;
alter table if exists public.assignment_clicks enable row level security;
alter table if exists public.broadcast_messages enable row level security;

do $$
begin
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='agencies' and policyname='agencies_service_role_all') then
    create policy agencies_service_role_all on public.agencies for all to service_role using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='assignments' and policyname='assignments_service_role_all') then
    create policy assignments_service_role_all on public.assignments for all to service_role using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='users' and policyname='users_service_role_all') then
    create policy users_service_role_all on public.users for all to service_role using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='user_preferences' and policyname='user_preferences_service_role_all') then
    create policy user_preferences_service_role_all on public.user_preferences for all to service_role using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='analytics_events' and policyname='analytics_events_service_role_all') then
    create policy analytics_events_service_role_all on public.analytics_events for all to service_role using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='analytics_daily' and policyname='analytics_daily_service_role_all') then
    create policy analytics_daily_service_role_all on public.analytics_daily for all to service_role using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='telegram_channels' and policyname='telegram_channels_service_role_all') then
    create policy telegram_channels_service_role_all on public.telegram_channels for all to service_role using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='telegram_messages_raw' and policyname='telegram_messages_raw_service_role_all') then
    create policy telegram_messages_raw_service_role_all on public.telegram_messages_raw for all to service_role using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='telegram_extractions' and policyname='telegram_extractions_service_role_all') then
    create policy telegram_extractions_service_role_all on public.telegram_extractions for all to service_role using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='ingestion_runs' and policyname='ingestion_runs_service_role_all') then
    create policy ingestion_runs_service_role_all on public.ingestion_runs for all to service_role using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='ingestion_run_progress' and policyname='ingestion_run_progress_service_role_all') then
    create policy ingestion_run_progress_service_role_all on public.ingestion_run_progress for all to service_role using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='assignment_clicks' and policyname='assignment_clicks_service_role_all') then
    create policy assignment_clicks_service_role_all on public.assignment_clicks for all to service_role using (true) with check (true);
  end if;
  if not exists (select 1 from pg_policies where schemaname='public' and tablename='broadcast_messages' and policyname='broadcast_messages_service_role_all') then
    create policy broadcast_messages_service_role_all on public.broadcast_messages for all to service_role using (true) with check (true);
  end if;
end $$;

-- Queue RPC helpers for the "raw collector + extraction worker" pipeline.
-- Apply in Supabase SQL Editor (or psql) on your existing DB.
--
-- This uses `public.telegram_extractions` as a work queue keyed by (raw_id, pipeline_version).
-- The worker claims jobs via `FOR UPDATE SKIP LOCKED` to avoid double-processing.

create or replace function public.enqueue_telegram_extractions(
  p_pipeline_version text,
  p_channel_link text,
  p_message_ids text[],
  p_force boolean default false
)
returns integer
language sql
as $$
  with src as (
    select id as raw_id, channel_link, message_id, message_date
    from public.telegram_messages_raw
    where channel_link = p_channel_link
      and message_id = any(p_message_ids)
      and deleted_at is null
  ),
  upserted as (
    insert into public.telegram_extractions (
      raw_id,
      pipeline_version,
      status,
      channel_link,
      message_id,
      message_date,
      created_at,
      updated_at
    )
    select
      s.raw_id,
      p_pipeline_version,
      'pending',
      s.channel_link,
      s.message_id,
      s.message_date,
      now(),
      now()
    from src s
    on conflict (raw_id, pipeline_version) do update
      set
        status = case
          when public.telegram_extractions.status = 'ok' and not p_force then public.telegram_extractions.status
          else 'pending'
        end,
        channel_link = excluded.channel_link,
        message_id = excluded.message_id,
        message_date = excluded.message_date,
        updated_at = now()
      where p_force or public.telegram_extractions.status <> 'ok'
    returning 1
  )
  select count(*)::int from upserted;
$$;


create or replace function public.claim_telegram_extractions(
  p_pipeline_version text,
  p_limit integer default 20
)
returns setof public.telegram_extractions
language plpgsql
as $$
begin
  return query
    with cte as (
      select te.id
      from public.telegram_extractions te
      where te.pipeline_version = p_pipeline_version
        and te.status = 'pending'
      order by te.created_at asc, te.id asc
      for update skip locked
      limit greatest(1, p_limit)
    )
    update public.telegram_extractions te
      set
        status = 'processing',
        updated_at = now(),
        meta = coalesce(te.meta, '{}'::jsonb)
              || jsonb_build_object(
                'processing_started_at', now(),
                'attempt', coalesce(nullif((te.meta->>'attempt'), '')::int, 0) + 1
              )
    from cte
    where te.id = cte.id
    returning te.*;
end;
$$;

alter function public.enqueue_telegram_extractions(text, text, text[], boolean)
  set search_path = public, extensions;

alter function public.claim_telegram_extractions(text, integer)
  set search_path = public, extensions;

-- Simplify `public.telegram_extractions` to a single-pass extract+canonicalize pipeline.
--
-- This removes the legacy stage A/B columns and replaces them with:
-- - llm_model (text)
-- - error_json (jsonb)
--
-- Safe to run once on an existing DB. Review before applying in production.

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'telegram_extractions'
      and column_name = 'stage_b_errors'
  ) and not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'telegram_extractions'
      and column_name = 'error_json'
  ) then
    alter table public.telegram_extractions rename column stage_b_errors to error_json;
  end if;

  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'telegram_extractions'
      and column_name = 'model_a'
  ) and not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'telegram_extractions'
      and column_name = 'llm_model'
  ) then
    alter table public.telegram_extractions rename column model_a to llm_model;
  end if;
end $$;

alter table public.telegram_extractions
  add column if not exists llm_model text,
  add column if not exists error_json jsonb,
  add column if not exists updated_at timestamptz not null default now();

alter table public.telegram_extractions
  drop column if exists model_b,
  drop column if exists stage_a_json,
  drop column if exists stage_a_errors,
  drop column if exists compilation_assignment_ids,
  drop column if exists bump_applied_at,
  drop column if exists bump_applied_count,
  drop column if exists bump_applied_errors;

drop index if exists public.telegram_extractions_bump_applied_at_idx;

create index if not exists telegram_extractions_created_at_idx
  on public.telegram_extractions (created_at desc);
