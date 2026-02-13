---
name: tutordex-supabase-ops
description: TutorDex Supabase operations (PostgREST, RPC, REST, Kong, anon key, JWT secret, ops_agent role) for analytics, debugging, queue triage, and safe ops actions.
---

# TutorDex Supabase Ops

Use for data questions, diagnostics, and safe operational actions.

## Whitelisted RPCs

- `ops_queue_health()`
- `ops_extractions_error_summary(p_days, p_limit)`
- `ops_failures_by_channel(p_days, p_limit)`
- `ops_validation_failures_by_reason(p_days)`
- `ops_recent_failed_samples(p_days, p_limit)` (redacted previews)
- `ops_requeue_extraction(p_extraction_id, p_max_age_days)`
- `ops_mark_extraction_skipped(p_extraction_id, p_reason, p_max_age_days)`

## How to call

- Use `scripts/ops/supabase_rpc.sh --env staging|prod --fn=<rpc> --json='<json>'`
- Requires:
  - `SUPABASE_API_KEY` (recommended: Supabase anon key, to satisfy Kong key-auth)
  - and either `SUPABASE_OPS_AGENT_JWT` or `SUPABASE_JWT_SECRET` (to mint a short-lived `role=ops_agent` JWT).
