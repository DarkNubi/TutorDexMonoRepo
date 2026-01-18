-- TutorDex assignments edit/bump tracking verification
-- Checks columns + indexes for published_at/source_last_seen and validates freshness tier inputs.

-- 1) Columns on public.assignments
select
  'assignments_columns' as check,
  c.column_name,
  c.data_type,
  c.is_nullable,
  c.column_default
from information_schema.columns c
where c.table_schema = 'public'
  and c.table_name = 'assignments'
  and c.column_name in (
    'published_at',
    'source_last_seen',
    'last_seen',
    'freshness_tier',
    'status'
  )
order by c.column_name;

-- 2) Indexes for sorting + tier updates
select
  'assignments_indexes' as check,
  i.indexname,
  i.indexdef
from pg_indexes i
where i.schemaname = 'public'
  and i.tablename = 'assignments'
  and i.indexname in (
    'assignments_source_last_seen_idx',
    'assignments_published_at_idx',
    'assignments_open_published_at_idx'
  )
order by i.indexname;

-- 3) RPC return columns include `source_last_seen`? (important for website timestamps)
select
  'rpc_returns' as check,
  p.proname,
  unnest(p.proallargnames) as out_name
from pg_proc p
join pg_namespace n on n.oid = p.pronamespace
where n.nspname = 'public'
  and p.proname in ('list_open_assignments', 'list_open_assignments_v2')
  and p.proallargnames is not null
order by p.proname, out_name;

-- 4) Sample of "age" signals to sanity-check tiering inputs (latest 50 open)
select
  id,
  external_id,
  agency_display_name,
  agency_telegram_channel_name,
  status,
  published_at,
  source_last_seen,
  last_seen,
  freshness_tier
from public.assignments
where status = 'open'
order by coalesce(source_last_seen, published_at, created_at, last_seen) desc, id desc
limit 50;

-- 5) Quick OK/FAIL summary (empty result = missing)
with cols as (
  select column_name
  from information_schema.columns
  where table_schema='public' and table_name='assignments'
),
idx as (
  select indexname
  from pg_indexes
  where schemaname='public' and tablename='assignments'
)
select 'has_published_at_col' as check, exists(select 1 from cols where column_name='published_at') as ok
union all select 'has_source_last_seen_col', exists(select 1 from cols where column_name='source_last_seen')
union all select 'has_assignments_source_last_seen_idx', exists(select 1 from idx where indexname='assignments_source_last_seen_idx')
union all select 'has_assignments_published_at_idx', exists(select 1 from idx where indexname='assignments_published_at_idx')
union all select 'has_assignments_open_published_at_idx', exists(select 1 from idx where indexname='assignments_open_published_at_idx');
