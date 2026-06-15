-- Prioritize fresh Telegram posts when draining the extraction queue.
--
-- During large recovery backlogs, oldest-first claiming can leave today's
-- assignments hidden behind weeks of pending historical jobs. Freshness matters
-- more for the public assignment feed, so claim newest message_date first while
-- preserving deterministic id ordering within the same timestamp.

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
      order by te.message_date desc nulls last, te.created_at desc, te.id desc
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
