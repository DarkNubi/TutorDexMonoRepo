-- Distance-aware assignments listing (DB-side ordering + keyset pagination).
-- Apply in Supabase SQL Editor (or psql) on an existing DB.
--
-- Adds RPC:
--   public.list_open_assignments_v2(...)
--
-- Notes:
-- - Computes `distance_km` (tutor coords -> assignment coords) when both coords exist.
-- - Supports `p_sort = 'newest' | 'distance'`.
-- - For distance sort pagination, use cursor tuple:
--     (distance_sort_key, last_seen, id)
--   where distance_sort_key = coalesce(distance_km, 1e9).

-- Ensure older DBs have assignment coordinates columns.
alter table public.assignments
  add column if not exists postal_lat double precision;

alter table public.assignments
  add column if not exists postal_lon double precision;

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
  p_agency_name text default null,
  p_learning_mode text default null,
  p_location_query text default null,
  p_min_rate integer default null
)
returns table(
  id bigint,
  external_id text,
  message_link text,
  agency_name text,
  learning_mode text,
  subject text,
  subjects text[],
  level text,
  specific_student_level text,
  address text,
  postal_code text,
  nearest_mrt text,
	  frequency text,
	  duration text,
	  time_slots_note text,
	  hourly_rate text,
	  rate_min integer,
	  rate_max integer,
	  student_gender text,
	  tutor_gender text,
  status text,
  created_at timestamptz,
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
    case
      when a.level = 'International Baccalaureate' then 'IB'
      else a.level
    end as _level_norm,
    coalesce(
      nullif(a.subjects_general, '{}'::text[]),
      nullif(a.subjects_canonical, '{}'::text[]),
      nullif(a.subjects, '{}'::text[]),
      case
        when a.subject is not null and btrim(a.subject) <> '' then array[btrim(a.subject)]
        else '{}'::text[]
      end
    ) as _subject_list,
    lower(concat_ws(' ', nullif(a.address, ''), nullif(a.postal_code, ''), nullif(a.nearest_mrt, ''))) as _loc
  from public.assignments a
  where a.status = 'open'
),
filtered as (
  select *
  from base
  where (p_level is null or _level_norm = (case when p_level = 'International Baccalaureate' then 'IB' else p_level end))
    and (p_specific_student_level is null or specific_student_level = p_specific_student_level)
    and (p_subject is null or p_subject = any(_subject_list))
    and (p_agency_name is null or agency_name = p_agency_name)
    and (p_learning_mode is null or learning_mode = p_learning_mode)
    and (
      p_location_query is null
      or btrim(p_location_query) = ''
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
    -- Newest sort pagination: (last_seen, id) < (cursor_last_seen, cursor_id)
    (coalesce(p_sort, 'newest') <> 'distance' and (
      p_cursor_last_seen is null
      or (s.last_seen, s.id) < (p_cursor_last_seen, p_cursor_id)
    ))
    or
    -- Distance sort pagination: (distance_sort_key asc, last_seen desc, id desc)
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
  subject,
  subjects,
  _level_norm as level,
  specific_student_level,
  address,
  postal_code,
  nearest_mrt,
	  frequency,
	  duration,
	  time_slots_note,
	  hourly_rate,
	  rate_min,
	  rate_max,
	  student_gender,
	  tutor_gender,
  status,
  created_at,
  last_seen,
  freshness_tier,
  distance_km,
  distance_sort_key,
  count(*) over() as total_count
from paged
order by
  -- When sorting by distance, this takes precedence; otherwise all NULLs.
  case when coalesce(p_sort, 'newest') = 'distance' then distance_sort_key else null end asc,
  case when coalesce(p_sort, 'newest') = 'distance' then last_seen else null end desc,
  case when coalesce(p_sort, 'newest') = 'distance' then id else null end desc,
  last_seen desc,
  id desc
limit greatest(1, least(p_limit, 200));
$$;
