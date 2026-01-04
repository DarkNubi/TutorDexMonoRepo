-- TutorDex: TutorCity external_id cleanup (composite -> assignment_code)
-- Apply in Supabase SQL Editor (public schema).
--
-- Background:
-- Older versions of TutorDex used a composite TutorCity external_id:
--   external_id = "<assignment_code>:<subjects...>"
-- This produced duplicates on the website when TutorCity was actually sending updates.
--
-- New behavior:
-- TutorCity rows are keyed by assignment_code (external_id == assignment_code) and updates overwrite.
--
-- This script is safe to run after the new code has been deployed and TutorCity has been fetched at least once,
-- so that canonical rows (external_id == assignment_code) exist.

-- 1) Merge click counts from composite ids into canonical ids (best-effort).
insert into public.assignment_clicks(external_id, original_url, clicks, last_click_at)
select
  a.assignment_code as external_id,
  max(c.original_url) as original_url,
  sum(coalesce(c.clicks, 0))::bigint as clicks,
  max(c.last_click_at) as last_click_at
from public.assignments a
join public.assignment_clicks c
  on (
    c.external_id = a.assignment_code
    or c.external_id like (a.assignment_code || ':%')
  )
where a.agency_name = 'TutorCity'
  and a.assignment_code is not null
  and btrim(a.assignment_code) <> ''
group by a.assignment_code
on conflict (external_id) do update
set
  clicks = excluded.clicks,
  last_click_at = greatest(public.assignment_clicks.last_click_at, excluded.last_click_at),
  original_url = coalesce(public.assignment_clicks.original_url, excluded.original_url);

-- 2) Delete old TutorCity assignment rows that used composite ids, but only when the canonical row exists.
delete from public.assignments old
where old.agency_name = 'TutorCity'
  and old.assignment_code is not null
  and btrim(old.assignment_code) <> ''
  and position(':' in old.external_id) > 0
  and exists (
    select 1
    from public.assignments canon
    where canon.agency_name = 'TutorCity'
      and canon.assignment_code = old.assignment_code
      and canon.external_id = canon.assignment_code
  );

-- 3) Optionally delete composite click rows after merge (keeps table tidy).
delete from public.assignment_clicks c
where position(':' in c.external_id) > 0
  and exists (
    select 1
    from public.assignments canon
    where canon.agency_name = 'TutorCity'
      and canon.external_id = canon.assignment_code
      and c.external_id like (canon.assignment_code || ':%')
  );
