-- Simplify `public.telegram_extractions` to a single-pass extract+canonicalize pipeline.
--
-- This removes the legacy stage A/B columns and replaces them with:
-- - llm_model (text)
-- - error_json (jsonb)
--
-- Safe to run once on an existing DB. Review before applying in production.

do $$
begin
  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'telegram_extractions'
      and column_name = 'stage_b_errors'
  ) and not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'telegram_extractions'
      and column_name = 'error_json'
  ) then
    alter table public.telegram_extractions rename column stage_b_errors to error_json;
  end if;

  if exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'telegram_extractions'
      and column_name = 'model_a'
  ) and not exists (
    select 1
    from information_schema.columns
    where table_schema = 'public'
      and table_name = 'telegram_extractions'
      and column_name = 'llm_model'
  ) then
    alter table public.telegram_extractions rename column model_a to llm_model;
  end if;
end $$;

alter table public.telegram_extractions
  add column if not exists llm_model text,
  add column if not exists error_json jsonb,
  add column if not exists updated_at timestamptz not null default now();

alter table public.telegram_extractions
  drop column if exists model_b,
  drop column if exists stage_a_json,
  drop column if exists stage_a_errors,
  drop column if exists compilation_assignment_ids,
  drop column if exists bump_applied_at,
  drop column if exists bump_applied_count,
  drop column if exists bump_applied_errors;

drop index if exists public.telegram_extractions_bump_applied_at_idx;

create index if not exists telegram_extractions_created_at_idx
  on public.telegram_extractions (created_at desc);
