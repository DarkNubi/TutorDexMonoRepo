# SupabaseFailureSpike

Meaning: Supabase REST/RPC operations are failing at elevated rate.

What to check:
- Supabase gateway reachability (`/health/dependencies` probe).
- Worker logs for HTTP 401/403/500 and RPC missing errors.

Mitigation:
- Verify `SUPABASE_URL_*` and `SUPABASE_SERVICE_ROLE_KEY`.
- Ensure required SQL functions are applied.

