-- Requeue stale extraction jobs that were left in `processing` due to worker crashes/restarts.
-- This RPC is called by `TutorDexAggregator/workers/job_manager.py`.

create or replace function public.requeue_stale_extractions(
  p_older_than_seconds integer
)
returns jsonb
language plpgsql
security definer
as $$
declare
  v_count integer;
begin
  update public.telegram_extractions
     set
       status = 'pending',
       updated_at = now(),
       meta = coalesce(meta, '{}'::jsonb)
             || jsonb_build_object('requeued_at', now(), 'requeue_reason', 'stale_processing')
   where status = 'processing'
     and updated_at < now() - make_interval(secs => greatest(0, p_older_than_seconds));

  get diagnostics v_count = row_count;
  return jsonb_build_object('count', v_count);
end;
$$;

alter function public.requeue_stale_extractions(integer)
  set search_path = public, extensions;

