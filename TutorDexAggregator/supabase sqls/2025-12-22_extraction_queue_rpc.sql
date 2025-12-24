-- Queue RPC helpers for the "raw collector + extraction worker" pipeline.
-- Apply in Supabase SQL Editor (or psql) on your existing DB.
--
-- This uses `public.telegram_extractions` as a work queue keyed by (raw_id, pipeline_version).
-- The worker claims jobs via `FOR UPDATE SKIP LOCKED` to avoid double-processing.

create or replace function public.enqueue_telegram_extractions(
  p_pipeline_version text,
  p_channel_link text,
  p_message_ids text[],
  p_force boolean default false
)
returns integer
language sql
as $$
  with src as (
    select id as raw_id, channel_link, message_id, message_date
    from public.telegram_messages_raw
    where channel_link = p_channel_link
      and message_id = any(p_message_ids)
      and deleted_at is null
  ),
  upserted as (
    insert into public.telegram_extractions (
      raw_id,
      pipeline_version,
      status,
      channel_link,
      message_id,
      message_date,
      created_at,
      updated_at
    )
    select
      s.raw_id,
      p_pipeline_version,
      'pending',
      s.channel_link,
      s.message_id,
      s.message_date,
      now(),
      now()
    from src s
    on conflict (raw_id, pipeline_version) do update
      set
        status = case
          when public.telegram_extractions.status = 'ok' and not p_force then public.telegram_extractions.status
          else 'pending'
        end,
        channel_link = excluded.channel_link,
        message_id = excluded.message_id,
        message_date = excluded.message_date,
        updated_at = now()
      where p_force or public.telegram_extractions.status <> 'ok'
    returning 1
  )
  select count(*)::int from upserted;
$$;


create or replace function public.claim_telegram_extractions(
  p_pipeline_version text,
  p_limit integer default 20
)
returns setof public.telegram_extractions
language plpgsql
as $$
begin
  return query
    with cte as (
      select te.id
      from public.telegram_extractions te
      where te.pipeline_version = p_pipeline_version
        and te.status = 'pending'
      order by te.created_at asc, te.id asc
      for update skip locked
      limit greatest(1, p_limit)
    )
    update public.telegram_extractions te
      set
        status = 'processing',
        updated_at = now(),
        meta = coalesce(te.meta, '{}'::jsonb)
              || jsonb_build_object(
                'processing_started_at', now(),
                'attempt', coalesce(nullif((te.meta->>'attempt'), '')::int, 0) + 1
              )
    from cte
    where te.id = cte.id
    returning te.*;
end;
$$;

alter function public.enqueue_telegram_extractions(text, text, text[], boolean)
  set search_path = public, extensions;

alter function public.claim_telegram_extractions(text, integer)
  set search_path = public, extensions;
