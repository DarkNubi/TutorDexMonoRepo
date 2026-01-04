-- Assignments: add `source_last_seen` for bump-based freshness without reprocess pollution.
-- Apply in Supabase SQL Editor (public schema).
--
-- Semantics:
-- - `published_at`: original post time / first-seen (used for "newest" sorting)
-- - `source_last_seen`: last upstream bump/edit/repost time (used for freshness tiers)
-- - `last_seen`: last time TutorDex processed/observed the row (operational)

alter table public.assignments
  add column if not exists source_last_seen timestamptz;

-- Indexes to support:
-- - `update_freshness_tiers.py` filtering by `source_last_seen` / fallbacks
-- - "newest" sorting by `published_at` (when combined with status)
create index if not exists assignments_source_last_seen_idx
  on public.assignments (source_last_seen desc);

create index if not exists assignments_published_at_idx
  on public.assignments (published_at desc);

-- Partial index for the common website feed query (`status='open'`).
create index if not exists assignments_open_published_at_idx
  on public.assignments (published_at desc, id desc)
  where status = 'open';

-- Backfill best-effort: assume last upstream bump == published_at (fallback created_at/last_seen).
update public.assignments
  set source_last_seen = coalesce(source_last_seen, published_at, created_at, last_seen)
  where source_last_seen is null;
