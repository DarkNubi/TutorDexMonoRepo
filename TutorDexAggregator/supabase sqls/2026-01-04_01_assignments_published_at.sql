-- Assignments: add `published_at` to support "newest" sorting by source publish time.
-- Apply in Supabase SQL Editor (public schema).

alter table public.assignments
  add column if not exists published_at timestamptz;

-- Backfill for existing rows (best-effort).
update public.assignments
  set published_at = coalesce(published_at, created_at, last_seen)
  where published_at is null;

