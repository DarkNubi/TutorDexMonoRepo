-- Durable per-window checkpoints for large Telegram historical replays.
-- Apply with the normal Supabase migration process before using the windowed runner.

create table if not exists public.ingestion_backfill_windows (
  id bigserial primary key,
  replay_key text not null,
  channel_link text not null,
  min_message_id bigint,
  max_message_id bigint,
  min_message_date timestamptz,
  max_message_date timestamptz,
  status text not null default 'pending'
    check (status in ('pending', 'running', 'complete', 'failed')),
  attempts integer not null default 0,
  lease_owner text,
  lease_expires_at timestamptz,
  last_message_id text,
  scanned_count bigint not null default 0,
  written_count bigint not null default 0,
  error_count bigint not null default 0,
  last_error text,
  metadata jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  completed_at timestamptz
);

create unique index if not exists ingestion_backfill_windows_key_uq
  on public.ingestion_backfill_windows
    (replay_key, channel_link, coalesce(min_message_id, 0), coalesce(max_message_id, 0));

create index if not exists ingestion_backfill_windows_claim_idx
  on public.ingestion_backfill_windows (status, lease_expires_at, channel_link);

create index if not exists ingestion_backfill_windows_replay_idx
  on public.ingestion_backfill_windows (replay_key, channel_link, min_message_id);

alter table public.ingestion_backfill_windows enable row level security;

drop policy if exists ingestion_backfill_windows_service_role_all
  on public.ingestion_backfill_windows;
create policy ingestion_backfill_windows_service_role_all
  on public.ingestion_backfill_windows
  for all to service_role
  using (true)
  with check (true);
