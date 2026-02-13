-- Ops "agent gateway" RPCs: read-only analytics + safe redacted samples.
-- Goal: give automation a programmatic surface without granting arbitrary SQL access.
--
-- Apply via: python scripts/migrate.py (see scripts/MIGRATIONS_README.md)

begin;

-- -------------------------------
-- Helpers
-- -------------------------------

create or replace function public.ops_redact_text(p_text text)
returns text
language sql
immutable
as $$
  select
    regexp_replace(
      regexp_replace(coalesce(p_text, ''), '(?i)\\b\\+?65\\s*\\d{4}\\s*\\d{4}\\b', '[REDACTED_PHONE]', 'g'),
      '\\b\\d{7,}\\b',
      '[REDACTED_NUMBER]',
      'g'
    );
$$;

-- -------------------------------
-- Queue health
-- -------------------------------

create or replace function public.ops_queue_health()
returns jsonb
language sql
stable
as $$
  with base as (
    select
      count(*) filter (where status = 'pending') as pending,
      count(*) filter (where status = 'processing') as processing,
      count(*) filter (where status = 'ok') as ok,
      count(*) filter (where status = 'failed') as failed,
      max(created_at) as newest_created_at,
      min(created_at) filter (where status = 'pending') as oldest_pending_created_at,
      min(updated_at) filter (where status = 'processing') as oldest_processing_updated_at
    from public.telegram_extractions
  )
  select jsonb_build_object(
    'pending', pending,
    'processing', processing,
    'ok', ok,
    'failed', failed,
    'newest_created_at', newest_created_at,
    'oldest_pending_created_at', oldest_pending_created_at,
    'oldest_processing_updated_at', oldest_processing_updated_at
  )
  from base;
$$;

-- -------------------------------
-- Error summaries
-- -------------------------------

create or replace function public.ops_extractions_error_summary(p_days int default 7, p_limit int default 50)
returns table (
  status text,
  error_kind text,
  count bigint,
  last_seen timestamptz
)
language sql
stable
as $$
  select
    te.status,
    coalesce(te.error_json->>'error', 'unknown') as error_kind,
    count(*) as count,
    max(coalesce(te.updated_at, te.created_at)) as last_seen
  from public.telegram_extractions te
  where te.created_at >= now() - make_interval(days => greatest(p_days, 1))
    and te.status in ('failed', 'pending', 'processing', 'ok')
    and te.error_json is not null
  group by 1, 2
  order by count desc, last_seen desc
  limit greatest(p_limit, 1);
$$;

create or replace function public.ops_failures_by_channel(p_days int default 7, p_limit int default 50)
returns table (
  channel_link text,
  failures bigint,
  last_failure timestamptz
)
language sql
stable
as $$
  select
    coalesce(te.channel_link, 'unknown') as channel_link,
    count(*) as failures,
    max(coalesce(te.updated_at, te.created_at)) as last_failure
  from public.telegram_extractions te
  where te.created_at >= now() - make_interval(days => greatest(p_days, 1))
    and te.status = 'failed'
  group by 1
  order by failures desc, last_failure desc
  limit greatest(p_limit, 1);
$$;

create or replace function public.ops_validation_failures_by_reason(p_days int default 7)
returns table (
  reason text,
  count bigint,
  last_seen timestamptz
)
language sql
stable
as $$
  with errs as (
    select
      te.updated_at as ts,
      jsonb_array_elements_text(coalesce(te.error_json->'errors', '[]'::jsonb)) as reason
    from public.telegram_extractions te
    where te.created_at >= now() - make_interval(days => greatest(p_days, 1))
      and te.status = 'failed'
      and (te.error_json->>'error') = 'validation_failed'
  )
  select
    reason,
    count(*) as count,
    max(ts) as last_seen
  from errs
  group by 1
  order by count desc;
$$;

-- -------------------------------
-- Recent samples (redacted)
-- -------------------------------

create or replace function public.ops_recent_failed_samples(
  p_days int default 3,
  p_limit int default 20
)
returns table (
  extraction_id bigint,
  channel_link text,
  message_id text,
  message_date timestamptz,
  error_json jsonb,
  stage text,
  raw_preview text
)
language sql
stable
as $$
  select
    te.id as extraction_id,
    coalesce(te.channel_link, tmr.channel_link) as channel_link,
    coalesce(te.message_id, tmr.message_id) as message_id,
    coalesce(te.message_date, tmr.message_date) as message_date,
    te.error_json,
    coalesce(te.meta->>'stage', te.meta->'stage'->>0, null) as stage,
    left(public.ops_redact_text(coalesce(tmr.raw_text, '')), 240) as raw_preview
  from public.telegram_extractions te
  join public.telegram_messages_raw tmr on tmr.id = te.raw_id
  where te.created_at >= now() - make_interval(days => greatest(p_days, 1))
    and te.status = 'failed'
  order by coalesce(te.updated_at, te.created_at) desc
  limit greatest(p_limit, 1);
$$;

commit;

