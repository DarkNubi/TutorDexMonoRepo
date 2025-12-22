-- Supabase schema (minimal) for TutorDexAggregator + TutorDexWebsite.
-- Apply in Supabase SQL Editor.

create table if not exists public.assignments (
  id bigserial primary key,
  agency_name text not null,
  agency_link text,
  external_id text not null,
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

  created_at timestamptz not null default now(),
  last_seen timestamptz not null default now(),
  bump_count int not null default 0,
  freshness_tier text not null default 'green',
  status text not null default 'open'
);

create unique index if not exists assignments_agency_external_id_uq
  on public.assignments (agency_name, external_id);

create index if not exists assignments_status_created_at_idx
  on public.assignments (status, created_at desc);

create index if not exists assignments_status_last_seen_idx
  on public.assignments (status, last_seen desc);

