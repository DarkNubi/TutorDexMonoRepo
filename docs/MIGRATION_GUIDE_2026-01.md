# Migration Guide (2026-01)

This guide summarizes the operational changes made during the January 2026 refactor/audit cycle and how to deploy safely.

## What Changed

- **Supabase client**: unified under `shared/supabase_client.py` (see `docs/ADR-0001-SUPABASE-CLIENT-CONSOLIDATION.md`).
- **Backend initialization**: `TutorDexBackend/app_context.py` introduced; `TutorDexBackend/runtime.py` is deprecated.
- **Legacy cleanup**: removed legacy Aggregator files (see `docs/REMOVED_FILES.md`).
- **Import boundaries**: import-linter config added (`.import-linter.ini`) and CI check (`.github/workflows/import-lint.yml`).
- **Website build**: `TutorDexWebsite` build fixed (default export import alignment).

## Pre-Deploy Checklist

- Ensure `.env` files exist and are correct:
  - `TutorDexAggregator/.env`
  - `TutorDexBackend/.env`
  - `TutorDexWebsite/.env`
- Apply Supabase SQL migrations that your deployment depends on (see `TutorDexAggregator/supabase sqls/`).
- Ensure the LLM endpoint configured by `LLM_API_URL` is reachable (Aggregator worker).

## Deploy Steps (Docker Compose)

1. Build and start services: `docker compose up -d --build`
2. Run smoke tests:
   - `scripts/smoke_test_backend.bat`
   - `scripts/smoke_test_aggregator.bat`
   - `scripts/smoke_test_observability.bat`
   - `scripts/smoke_test_all.bat`
3. Monitor dashboards/logs:
   - Grafana / Prometheus / Alertmanager
   - Backend `/health/full`
   - Aggregator via backend health: `/health/worker` and `/health/collector` (worker port `9002` is not published by default in `docker-compose.yml`)

## Rollback

- Revert to the last known-good image/tag (or git revision) and redeploy with `docker compose up -d --build`.
- If a Supabase migration introduced a breaking schema change, roll it back using your normal DB rollback procedure (or restore from backup).
