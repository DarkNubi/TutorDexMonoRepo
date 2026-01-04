-- Subjects taxonomy v2 (stable canonical codes + general rollups)
-- Apply in Supabase SQL Editor (public schema).
--
-- Adds:
-- - assignments.subjects_canonical text[]
-- - assignments.subjects_general text[]
-- - assignments.canonicalization_version int
-- - assignments.canonicalization_debug jsonb (optional diagnostics)
-- - GIN indexes for fast filtering
-- - Updates RPCs:
--   - public.list_open_assignments(...)
--   - public.list_open_assignments_v2(...)
--   - public.open_assignment_facets(...)
--
-- Back-compat:
-- - Existing `p_subject` filter still works against legacy `signals_subjects` and also matches new codes.
--
-- IMPORTANT (PostgREST overloading):
-- Earlier migrations defined `public.list_open_assignments`, `public.list_open_assignments_v2`, and
-- `public.open_assignment_facets` without v2 subject params. `create or replace` does not remove other
-- overloads with different signatures, so PostgREST may return `PGRST203` (ambiguous function) and the
-- backend will appear to return 0 assignments.
-- These drops remove legacy signatures before installing the v2 versions.
--
-- Additionally, Postgres does NOT allow `create or replace function ... returns table(...)`
-- to change the returned row type. When you add/remove return columns (e.g. `published_at`),
-- you must DROP the existing function first.
--
-- This DO block drops *all* overloads for these RPC names in the `public` schema so the
-- migration is idempotent across schema drift.
do $$
declare
  r record;
begin
  for r in
    select
      n.nspname as schema_name,
      p.proname as fn_name,
      pg_get_function_identity_arguments(p.oid) as args
    from pg_proc p
    join pg_namespace n on n.oid = p.pronamespace
    where n.nspname = 'public'
      and p.proname in ('list_open_assignments', 'list_open_assignments_v2', 'open_assignment_facets')
  loop
    execute format('drop function if exists %I.%I(%s);', r.schema_name, r.fn_name, r.args);
  end loop;
end $$;

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
  integer
);

drop function if exists public.open_assignment_facets(
  text,
  text,
  text,
  text,
  text,
  text,
  integer
);

alter table public.assignments
  add column if not exists subjects_canonical text[] not null default '{}';

alter table public.assignments
  add column if not exists subjects_general text[] not null default '{}';

alter table public.assignments
  add column if not exists canonicalization_version int not null default 2;

alter table public.assignments
  add column if not exists canonicalization_debug jsonb;

alter table public.assignments
  add column if not exists published_at timestamptz;

create index if not exists assignments_subjects_canonical_gin
  on public.assignments using gin (subjects_canonical);

create index if not exists assignments_subjects_general_gin
  on public.assignments using gin (subjects_general);

-- --------------------------------------------------------------------------------
-- Update RPC: public.list_open_assignments (legacy newest-only)
-- --------------------------------------------------------------------------------

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
  signals_subjects text[],
  signals_levels text[],
  signals_specific_student_levels text[],
  subjects_canonical text[],
  subjects_general text[],
  canonicalization_version int,
  status text,
  created_at timestamptz,
  published_at timestamptz,
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
  signals_subjects,
  signals_levels,
  signals_specific_student_levels,
  subjects_canonical,
  subjects_general,
  canonicalization_version,
  status,
  created_at,
  published_at,
  last_seen,
  freshness_tier,
  count(*) over() as total_count
from filtered
order by _sort_ts desc, id desc
limit greatest(1, least(p_limit, 200));
$$;

-- --------------------------------------------------------------------------------
-- Update RPC: public.list_open_assignments_v2 (newest|distance)
-- --------------------------------------------------------------------------------

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
  signals_subjects text[],
  signals_levels text[],
  signals_specific_student_levels text[],
  subjects_canonical text[],
  subjects_general text[],
  canonicalization_version int,
  status text,
  created_at timestamptz,
  published_at timestamptz,
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
  signals_subjects,
  signals_levels,
  signals_specific_student_levels,
  subjects_canonical,
  subjects_general,
  canonicalization_version,
  status,
  created_at,
  published_at,
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

-- --------------------------------------------------------------------------------
-- Update RPC: public.open_assignment_facets
-- --------------------------------------------------------------------------------

create or replace function public.open_assignment_facets(
  p_level text default null,
  p_specific_student_level text default null,
  p_subject text default null,
  p_subject_general text default null,
  p_subject_canonical text default null,
  p_agency_name text default null,
  p_learning_mode text default null,
  p_location_query text default null,
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
      or _loc like '%' || lower(p_location_query) || '%'
    )
    and (p_min_rate is null or (rate_min is not null and rate_min >= p_min_rate))
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
);
$$;

