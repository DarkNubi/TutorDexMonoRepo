-- TutorDex: expose `source_last_seen` in website RPCs
-- Apply in Supabase SQL Editor (public schema).
--
-- Why:
-- Website cards show both:
-- - Posted: `published_at`
-- - Bumped/Updated: `source_last_seen`
--
-- Postgres note:
-- You cannot change the OUT/return shape of an existing function via CREATE OR REPLACE,
-- so we DROP the current signatures first.

drop function if exists public.list_open_assignments(
  integer,
  timestamptz,
  bigint,
  text,
  text,
  text,
  text,
  text,
  text,
  text,
  text,
  integer
);

drop function if exists public.list_open_assignments_v2(
  integer,
  text,
  double precision,
  double precision,
  timestamptz,
  bigint,
  double precision,
  text,
  text,
  text,
  text,
  text,
  text,
  text,
  text,
  integer
);

create or replace function public.list_open_assignments(
  p_limit integer default 50,
  p_cursor_last_seen timestamptz default null,
  p_cursor_id bigint default null,
  p_level text default null,
  p_specific_student_level text default null,
  p_subject text default null,
  p_subject_general text default null,
  p_subject_canonical text default null,
  p_agency_display_name text default null,
  p_learning_mode text default null,
  p_location_query text default null,
  p_min_rate integer default null
)
returns table(
  id bigint,
  external_id text,
  message_link text,
  agency_display_name text,
  agency_telegram_channel_name text,
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
    and (p_agency_display_name is null or coalesce(agency_display_name, agency_telegram_channel_name) = p_agency_display_name)
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
    and (
      p_cursor_last_seen is null
      or (_sort_ts, id) < (p_cursor_last_seen, p_cursor_id)
    )
)
select
  id,
  external_id,
  message_link,
  agency_display_name,
  agency_telegram_channel_name,
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
  p_agency_display_name text default null,
  p_learning_mode text default null,
  p_location_query text default null,
  p_min_rate integer default null
)
returns table(
  id bigint,
  external_id text,
  message_link text,
  agency_display_name text,
  agency_telegram_channel_name text,
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
    and (p_agency_display_name is null or coalesce(agency_display_name, agency_telegram_channel_name) = p_agency_display_name)
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
  agency_display_name,
  agency_telegram_channel_name,
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
