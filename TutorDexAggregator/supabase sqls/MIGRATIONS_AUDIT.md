# Supabase SQLs audit (migrations vs full schema)

This repo contains:
- `supabase_schema_full.sql`: a re-runnable **full schema snapshot** (tables, indexes, RPCs, helper functions, seed config rows).
- `supabase_rls_policies.sql`: **RLS lockdown** policies for a backend-only access model (deny `anon` + `authenticated`).
- Date-stamped `YYYY-MM-DD_*.sql` files: historical migrations + one-off maintenance/verification scripts.

## Current state

As of this audit, **all schema objects created by the date-stamped migrations are present in** `supabase_schema_full.sql`, including:
- Tables: `assignment_clicks`, `broadcast_messages`, `assignment_duplicate_groups`, `duplicate_detection_config`, `tutor_assignment_ratings`, etc.
- RPCs: `list_open_assignments`, `list_open_assignments_v2`, `open_assignment_facets`
- Helper functions: `get_duplicate_config`, `get_duplicate_group_members`, `update_duplicate_group_timestamp`, `calculate_tutor_rating_threshold`, `get_tutor_avg_rate`
- Seed rows: default `duplicate_detection_config` entries (`enabled`, `thresholds`, `weights`, etc.)

RLS policies in `supabase_rls_policies.sql` cover all tables defined in `supabase_schema_full.sql` (and lock them down for `anon` + `authenticated`).

## What you can delete (and the tradeoff)

If you only care about **new installs** (fresh database bootstrap) and you are OK losing:
- incremental upgrade path for existing DBs
- historical context/debuggability

…then you can delete **all** the date-stamped migration files and keep only:
- `supabase_schema_full.sql`
- `supabase_rls_policies.sql`

## Recommendation (safer cleanup)

Instead of deleting, prefer moving the date-stamped files into an `archive/` or `maintenance/` folder so you retain:
- one-off scripts (cleanup/verification) that aren’t part of the desired steady-state schema
- a path to upgrade/repair an existing Supabase project without reinitializing from scratch

