-- Supabase schema (normalized) for TutorDex.
-- Apply in Supabase SQL Editor.
-- Notes:
-- - This file creates: agencies, assignments, users, user_preferences, analytics_events, analytics_daily.
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

