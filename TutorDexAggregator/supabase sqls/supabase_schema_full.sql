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

create index if not exists assignments_subjects_canonical_gin
  on public.assignments using gin (subjects_canonical);

create index if not exists assignments_subjects_general_gin
  on public.assignments using gin (subjects_general);

create index if not exists assignments_tags_gin
  on public.assignments using gin (tags);

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
  model_a text,
  model_b text,
  status text not null,
  channel_link text,
  message_id text,
  message_date timestamptz,
  stage_a_json jsonb,
  stage_a_errors jsonb,
  canonical_json jsonb,
  stage_b_errors jsonb,
  compilation_assignment_ids text[],
  meta jsonb,
  created_at timestamptz not null default now(),
  bump_applied_at timestamptz,
  bump_applied_count int not null default 0,
  bump_applied_errors int not null default 0
);

create unique index if not exists telegram_extractions_raw_version_uq
  on public.telegram_extractions (raw_id, pipeline_version);

create index if not exists telegram_extractions_status_idx
  on public.telegram_extractions (status);

create index if not exists telegram_extractions_pipeline_version_idx
  on public.telegram_extractions (pipeline_version);

create index if not exists telegram_extractions_channel_date_idx
  on public.telegram_extractions (channel_link, message_date desc);

create index if not exists telegram_extractions_bump_applied_at_idx
  on public.telegram_extractions (bump_applied_at);

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

