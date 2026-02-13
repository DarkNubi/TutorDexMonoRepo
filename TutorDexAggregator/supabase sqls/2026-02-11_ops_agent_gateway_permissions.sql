-- Harden the ops agent gateway:
-- - Create a dedicated DB role `ops_agent` (NOLOGIN) for PostgREST JWT role mapping.
-- - Make ops_* functions SECURITY DEFINER and lock search_path.
-- - Revoke EXECUTE from PUBLIC; grant EXECUTE only to ops_agent and service_role.
--
-- This enables least-privilege PostgREST/RPC access using a JWT with role=ops_agent.

begin;

do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'ops_agent') then
    create role ops_agent nologin;
  end if;
exception when others then
  -- Ignore if role creation isn't permitted in some environments.
  null;
end $$;

-- Allow PostgREST's authenticator to switch into ops_agent based on JWT role claim.
do $$
begin
  if exists (select 1 from pg_roles where rolname = 'authenticator')
     and exists (select 1 from pg_roles where rolname = 'ops_agent') then
    grant ops_agent to authenticator;
  end if;
exception when others then
  null;
end $$;

-- Redaction helper.
create or replace function public.ops_redact_text(p_text text)
returns text
language sql
immutable
security definer
set search_path = public
as $$
  select
    regexp_replace(
      regexp_replace(coalesce(p_text, ''), '(?i)\\b\\+?65\\s*\\d{4}\\s*\\d{4}\\b', '[REDACTED_PHONE]', 'g'),
      '\\b\\d{7,}\\b',
      '[REDACTED_NUMBER]',
      'g'
    );
$$;

-- Queue health.
create or replace function public.ops_queue_health()
returns jsonb
language sql
stable
security definer
set search_path = public
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

-- Error summaries.
create or replace function public.ops_extractions_error_summary(p_days int default 7, p_limit int default 50)
returns table (
  status text,
  error_kind text,
  count bigint,
  last_seen timestamptz
)
language sql
stable
security definer
set search_path = public
as $$
  select
    te.status,
    coalesce(te.error_json->>'error', 'unknown') as error_kind,
    count(*) as count,
    max(coalesce(te.updated_at, te.created_at)) as last_seen
  from public.telegram_extractions te
  where te.created_at >= now() - make_interval(days => greatest(p_days, 1))
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
security definer
set search_path = public
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
security definer
set search_path = public
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
security definer
set search_path = public
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

-- Safe, bounded write ops.
create or replace function public.ops_requeue_extraction(p_extraction_id bigint, p_max_age_days int default 30)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_updated_at timestamptz;
  v_status text;
begin
  select updated_at, status into v_updated_at, v_status
  from public.telegram_extractions
  where id = p_extraction_id;

  if v_status is null then
    return jsonb_build_object('ok', false, 'reason', 'not_found');
  end if;

  if v_updated_at < now() - make_interval(days => greatest(p_max_age_days, 1)) then
    return jsonb_build_object('ok', false, 'reason', 'too_old', 'status', v_status, 'updated_at', v_updated_at);
  end if;

  update public.telegram_extractions
     set status = 'pending',
         error_json = null,
         updated_at = now(),
         meta = coalesce(meta, '{}'::jsonb) || jsonb_build_object('ops', jsonb_build_object('action','requeue','ts', now()))
   where id = p_extraction_id;

  return jsonb_build_object('ok', true, 'status', 'pending');
end $$;

create or replace function public.ops_mark_extraction_skipped(p_extraction_id bigint, p_reason text, p_max_age_days int default 30)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_updated_at timestamptz;
  v_status text;
  v_reason text;
begin
  v_reason := btrim(coalesce(p_reason, ''));
  if v_reason = '' then
    return jsonb_build_object('ok', false, 'reason', 'missing_reason');
  end if;
  if length(v_reason) > 200 then
    return jsonb_build_object('ok', false, 'reason', 'reason_too_long');
  end if;

  select updated_at, status into v_updated_at, v_status
  from public.telegram_extractions
  where id = p_extraction_id;

  if v_status is null then
    return jsonb_build_object('ok', false, 'reason', 'not_found');
  end if;

  if v_updated_at < now() - make_interval(days => greatest(p_max_age_days, 1)) then
    return jsonb_build_object('ok', false, 'reason', 'too_old', 'status', v_status, 'updated_at', v_updated_at);
  end if;

  update public.telegram_extractions
     set status = 'skipped',
         updated_at = now(),
         meta = coalesce(meta, '{}'::jsonb) || jsonb_build_object('ops', jsonb_build_object('action','skip','ts', now(), 'reason', v_reason))
   where id = p_extraction_id;

  return jsonb_build_object('ok', true, 'status', 'skipped');
end $$;

-- Lock down execute privileges.
revoke all on function public.ops_redact_text(text) from public;
revoke all on function public.ops_queue_health() from public;
revoke all on function public.ops_extractions_error_summary(int,int) from public;
revoke all on function public.ops_failures_by_channel(int,int) from public;
revoke all on function public.ops_validation_failures_by_reason(int) from public;
revoke all on function public.ops_recent_failed_samples(int,int) from public;
revoke all on function public.ops_requeue_extraction(bigint,int) from public;
revoke all on function public.ops_mark_extraction_skipped(bigint,text,int) from public;

grant execute on function public.ops_queue_health() to ops_agent;
grant execute on function public.ops_extractions_error_summary(int,int) to ops_agent;
grant execute on function public.ops_failures_by_channel(int,int) to ops_agent;
grant execute on function public.ops_validation_failures_by_reason(int) to ops_agent;
grant execute on function public.ops_recent_failed_samples(int,int) to ops_agent;
grant execute on function public.ops_requeue_extraction(bigint,int) to ops_agent;
grant execute on function public.ops_mark_extraction_skipped(bigint,text,int) to ops_agent;

commit;

