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

create unique index if not exists agencies_channel_link_uq
  on public.agencies (channel_link)
  where channel_link is not null;

create unique index if not exists agencies_name_uq
  on public.agencies (name);

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

  subject text,
  subjects text[],
  level text,
  specific_student_level text,
  type text,
  address text,
  postal_code text,
  postal_lat double precision,
  postal_lon double precision,
  nearest_mrt text,
  learning_mode text,
  student_gender text,
  tutor_gender text,
  frequency text,
  duration text,
  hourly_rate text,
  rate_min int,
  rate_max int,
  time_slots jsonb,
  estimated_time_slots jsonb,
  time_slots_note text,
  additional_remarks text,

  payload_json jsonb,
  parsed_json jsonb,
  parse_quality_score int not null default 0,

  -- canonicalization artifacts (optional but used by aggregator)
  subjects_canonical text[] not null default '{}',
  subjects_general text[] not null default '{}',
  tags text[] not null default '{}',
  canonicalization_version int not null default 1,

  created_at timestamptz not null default now(),
  last_seen timestamptz not null default now(),
  bump_count int not null default 0,
  freshness_tier text not null default 'green',
  status text not null default 'open'
);

create unique index if not exists assignments_agency_external_id_uq
  on public.assignments (agency_id, external_id);

create index if not exists assignments_status_created_at_idx
  on public.assignments (status, created_at desc);

create index if not exists assignments_status_last_seen_idx
  on public.assignments (status, last_seen desc);

create index if not exists assignments_parse_quality_score_idx
  on public.assignments (parse_quality_score desc);

create index if not exists assignments_status_level_idx
  on public.assignments (status, level);

create index if not exists assignments_status_agency_name_idx
  on public.assignments (status, agency_name);

create index if not exists assignments_subjects_gin
  on public.assignments using gin (subjects);

create index if not exists assignments_subjects_canonical_gin
  on public.assignments using gin (subjects_canonical);

create index if not exists assignments_subjects_general_gin
  on public.assignments using gin (subjects_general);

create index if not exists assignments_tags_gin
  on public.assignments using gin (tags);

-- Website pagination + facets (server-side filtering)
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

create table if not exists public.users (
  id bigserial primary key,
  firebase_uid text not null unique,
  name text,
  email text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

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
  updated_at timestamptz not null default now()
);

create table if not exists public.analytics_events (
  id bigserial primary key,
  assignment_id bigint references public.assignments(id) on delete set null,
  user_id bigint references public.users(id) on delete set null,
  event_type text not null,
  event_time timestamptz not null default now(),
  meta jsonb
);

create index if not exists analytics_events_time_idx
  on public.analytics_events (event_time desc);

create table if not exists public.analytics_daily (
  id bigserial primary key,
  day date not null,
  assignment_id bigint references public.assignments(id) on delete set null,
  event_type text not null,
  count int not null default 0,
  created_at timestamptz not null default now()
);

create unique index if not exists analytics_daily_uq
  on public.analytics_daily (day, assignment_id, event_type);

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

create unique index if not exists ingestion_run_progress_uq
  on public.ingestion_run_progress (run_id, channel_link);

-- Click tracking tables (fresh installs)
create table if not exists public.assignment_clicks (
  external_id text primary key,
  original_url text not null,
  clicks integer not null default 0,
  last_click_at timestamptz
);

create table if not exists public.broadcast_messages (
  external_id text primary key references public.assignment_clicks(external_id) on delete cascade,
  original_url text not null,
  sent_chat_id bigint not null,
  sent_message_id bigint not null,
  message_html text not null,
  last_rendered_clicks integer,
  last_edited_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create unique index if not exists broadcast_messages_chat_msg_uidx
  on public.broadcast_messages(sent_chat_id, sent_message_id);

