-- Website pagination + facets (server-side filtering)
-- Apply to your Supabase Postgres (public schema).
--
-- Provides:
-- - public.list_open_assignments(...) -> paginated rows + total_count
-- - public.open_assignment_facets(...) -> filter dropdown counts + total
--
-- Notes:
-- - Uses `last_seen desc, id desc` ordering for stable pagination.
-- - Subject filtering/facets prefer subjects_general -> subjects_canonical -> subjects -> subject.

create index if not exists assignments_status_level_idx
  on public.assignments (status, level);

create index if not exists assignments_status_agency_name_idx
  on public.assignments (status, agency_name);

create index if not exists assignments_subjects_gin
  on public.assignments using gin (subjects);

create or replace function public.list_open_assignments(
  p_limit integer default 50,
  p_cursor_last_seen timestamptz default null,
  p_cursor_id bigint default null,
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
    and (
      p_cursor_last_seen is null
      or (last_seen, id) < (p_cursor_last_seen, p_cursor_id)
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
  count(*) over() as total_count
from filtered
order by last_seen desc, id desc
limit greatest(1, least(p_limit, 200));
$$;

create or replace function public.open_assignment_facets(
  p_level text default null,
  p_specific_student_level text default null,
  p_subject text default null,
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
)
select jsonb_build_object(
  'total', (select count(*) from filtered),
  'levels', (
    select coalesce(
      jsonb_agg(jsonb_build_object('value', level, 'count', c) order by c desc, level asc),
      '[]'::jsonb
    )
    from (
      select _level_norm as level, count(*) as c
      from filtered
      where _level_norm is not null and btrim(_level_norm) <> ''
      group by _level_norm
    ) s
  ),
  'specific_levels', (
    select coalesce(
      jsonb_agg(jsonb_build_object('value', specific_student_level, 'count', c) order by c desc, specific_student_level asc),
      '[]'::jsonb
    )
    from (
      select specific_student_level, count(*) as c
      from filtered
      where specific_student_level is not null and btrim(specific_student_level) <> ''
      group by specific_student_level
    ) s
  ),
  'subjects', (
    select coalesce(
      jsonb_agg(jsonb_build_object('value', subject, 'count', c) order by c desc, subject asc),
      '[]'::jsonb
    )
    from (
      select subject, count(*) as c
      from (
        select distinct id, unnest(_subject_list) as subject
        from filtered
      ) d
      where subject is not null and btrim(subject) <> ''
      group by subject
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
