# TutorDex Recovery Report - 2026-06-14

## Current Status

TutorDex is partially recovered. Local code/tests/tooling and the observability alert path are repaired, but production assignment loading is still blocked by runtime state outside the repo.

Working:

- Python test suite passes: `308 passed, 4 warnings`.
- Ruff passes.
- Website tests pass: `11 passing`.
- Website production build succeeds.
- npm audit is clean.
- pip-audit is clean for backend/aggregator requirements.
- Prod env validation passes.
- Prod Prometheus, Alertmanager, blackbox-exporter, node-exporter, cAdvisor, and Alertmanager Telegram bridge are running.
- Alertmanager Telegram bridge accepted a post-rebuild Telegram delivery smoke test.
- Public API outage is now monitored by `PublicApiDown` critical alerts.

Blocked:

- Public API `https://tutordex-api.duckdns.org` times out.
- Local port `8000` is occupied by a root-owned stray Uvicorn process that returns `404` for TutorDex health routes.
- The configured self-hosted Supabase runtime is absent from reachable Docker state: no `supabase-prod_default` network, no Supabase/Kong/PostgREST/Postgres containers, and no TutorDex DB volume or dump found in reachable WSL/Windows-mounted paths.
- BizServer filesystem/runtime state could not be inspected from this session because node-host shell execution is not exposed in the current tool lane.

## Root Causes Found

1. **Silent prod/runtime drift**

   The public API surface was not continuously verified. Firebase Hosting can stay up while the backend API is dead, so the website can appear deployed while assignments fail.

2. **Missing database runtime ownership**

   TutorDex prod env points to a local self-hosted Supabase stack at host `127.0.0.1:54321`, Docker `kong:8000`, network `supabase-prod_default`. That stack is not present in reachable Docker state, and no DB backup/dump was found.

3. **Wrong process on backend port**

   Port `8000` is bound by a root-owned Uvicorn process outside the compose prod stack. It is not serving TutorDex health routes and cannot be stopped by the current WSL user.

4. **Staging was not production-like**

   Staging env validation fails for missing Firebase admin, Supabase config, Telegram session/bot config, and alert config. This means staging could not catch production assignment-loading or Telegram pipeline regressions.

5. **Smoke/env checks were too shallow**

   Previous HTTP smoke checks only looked at HTTP status, so JSON bodies like `{"ok": false}` could pass. Env validation checked the root env but not the backend/aggregator component envs.

6. **Dependency and tooling rot**

   Frontend tooling had npm vulnerabilities and old Vite/Mocha dependency chains. Local Python tooling was not prepared, and Ruff was scanning generated `.venv` content.

7. **Recovery depended on external registry/DNS**

   Compose used `pull_policy: always` for observability images. During DNS/registry trouble, restarts and rebuilds became unnecessarily fragile.

## Fixes Applied

- Hardened HTTP smoke scripts to fail on JSON `ok: false`.
- Reworked `scripts/validate_env.sh` to validate backend and aggregator component envs safely without sourcing shell-unsafe dotenv files.
- Updated ops smoke script to load backend Supabase config for direct RPC checks.
- Fixed stale test expectations for default exception logging level.
- Fixed agency row-building regression so Telegram channel title and registry display name keep distinct semantics.
- Upgraded frontend tooling and added npm overrides to clear `npm audit`.
- Added `.venv` to Ruff excludes.
- Restored prod observability core and Telegram alert bridge.
- Removed `requests` from the alert bridge and switched to stdlib `urllib`.
- Redacted alert bridge transport exceptions so provider URLs/tokens are not written into response metadata.
- Added alert bridge `/health` and `/metrics` endpoints.
- Added public API blackbox probes and the critical `PublicApiDown` alert.
- Changed compose image `pull_policy` from `always` to `missing` for cache-first recovery.
- Reduced noisy host disk alerts by excluding WSL/Docker/snap pseudo filesystems.

## Recovery Still Needed

1. Stop the root-owned wrong Uvicorn process on port `8000`.
2. Locate or restore the Supabase prod stack and data volume/backup for `supabase-prod_default`.
3. After Supabase is healthy, start only the backend and verify:

   ```bash
   curl -i http://127.0.0.1:8000/health
   curl -i http://127.0.0.1:8000/health/dependencies
   curl -i https://tutordex-api.duckdns.org/health
   ```

4. Only after backend and DB are healthy, start collectors/workers with broadcast/DM side effects reviewed.
5. Make staging production-like enough to catch assignment loading, backend dependency, and alerting failures before prod.
6. Add a DB backup/restore runbook and scheduled backup verification.

