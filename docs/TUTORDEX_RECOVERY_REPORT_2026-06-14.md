# TutorDex Recovery Report - 2026-06-14

## Current Status

TutorDex is mostly recovered on the host: backend, Supabase, collector, worker, local assignment loading, and observability are running again. Public Firebase assignment loading is still blocked by public ingress to `https://tutordex-api.duckdns.org`, which is timing out before it reaches the Windows/Docker host.

Working:

- Python test suite passes: `312 passed, 4 warnings`.
- Ruff passes.
- Website tests pass: `11 passing`.
- Website production build succeeds.
- Website and Remotion production npm audits are clean.
- Prod env validation passes.
- Prod Prometheus, Alertmanager, blackbox-exporter, node-exporter, cAdvisor, and Alertmanager Telegram bridge are running.
- Alertmanager Telegram bridge accepted a post-rebuild Telegram delivery smoke test.
- Public API outage is now monitored by `PublicApiDown` critical alerts.
- Supabase prod stack is running again and schema/grants are working.
- Backend `/health/dependencies` is green for backend + Redis + Supabase.
- Local assignments API is loading rows from Supabase.
- Local assignments page smoke loads live assignments through the backend.
- Collector and worker are running; recovery queue is draining.
- LLM extraction path is using the local Hermes/Qwen endpoint successfully.
- Prometheus app scrapes for backend, collector, and worker are green after config reload.
- Broadcast and DM side effects remain disabled during recovery.

Blocked:

- Public API `https://tutordex-api.duckdns.org` times out.
- WAN `115.66.211.92:80` and `115.66.211.92:443` time out from outside, while Caddy answers locally on `127.0.0.1` and over LAN at `192.168.1.31`.
- Router/NAT forwarding is still needed: external TCP `80` and `443` to Windows host `192.168.1.31`, same ports.
- Recovery backlog is still draining, so `QueueOldestPendingTooOld` may fire until catchup finishes.

## Root Causes Found

1. **Silent prod/runtime drift**

   The public API surface was not continuously verified. Firebase Hosting can stay up while the backend API is dead, so the website can appear deployed while assignments fail.

2. **Missing database runtime ownership**

   TutorDex prod env points to a local self-hosted Supabase stack at host `127.0.0.1:54321`, Docker `kong:8000`, network `supabase-prod_default`. During recovery that runtime was absent from the initial app stack and had to be recreated. No older prod data dump/backup was found in the reachable workspace, so the current DB is a fresh recovered runtime that is being repopulated from raw Telegram messages.

3. **Wrong process on backend port**

   Port `8000` was bound by a non-TutorDex Uvicorn process from another stack. That made backend health probes hit the wrong app until the process conflict was cleared and the TutorDex backend was started through compose.

4. **Staging was not production-like**

   Staging env validation fails for missing Firebase admin, Supabase config, Telegram session/bot config, and alert config. This means staging could not catch production assignment-loading or Telegram pipeline regressions.

5. **Smoke/env checks were too shallow**

   Previous HTTP smoke checks only looked at HTTP status, so JSON bodies like `{"ok": false}` could pass. Env validation checked the root env but not the backend/aggregator component envs.

6. **Dependency and tooling rot**

   Frontend tooling had npm vulnerabilities and old Vite/Mocha dependency chains. Local Python tooling was not prepared, and Ruff was scanning generated `.venv` content.

7. **Recovery depended on external registry/DNS**

   Compose used `pull_policy: always` for observability images. During DNS/registry trouble, restarts and rebuilds became unnecessarily fragile.

8. **Public ingress depended on router state**

   Docker/Caddy/backend are healthy locally, DuckDNS resolves to the observed WAN IP, and Windows Docker owns ports `80`/`443`, but public curls time out before reaching the host. The remaining public outage is upstream router/NAT/CGNAT state, not the TutorDex app stack.

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
- Added the Caddy API ingress proxy and verified local/LAN Caddy responses.
- Recreated the Supabase prod runtime and applied the schema/grants.
- Restored backend, collector, and worker containers.
- Fixed the worker LLM endpoint path to the local Hermes/Qwen service.
- Fixed frontend assignment loading so public assignment fetches are not blocked by slow/missing Firebase auth token initialization.
- Reset seven real assignment rows that had been incorrectly stranded at `max_attempts` during the unhealthy LLM period.
- Reworked Prometheus app scraping to direct backend/collector/worker `/metrics` targets and verified all app targets are green.
- Scoped worker queue metrics to the active pipeline version so backlog alerts do not mix historical pipeline rows.
- Added recovery-safe side-effect gates so TutorCity fetch respects broadcast/DM toggles, and freshness Telegram edits/deletes require explicit `FRESHNESS_PROPAGATE_TELEGRAM_ENABLED` / `FRESHNESS_DELETE_EXPIRED_TELEGRAM_ENABLED` opt-ins.
- Added `scripts/ops/supabase_backup.sh` and `docs/SUPABASE_BACKUP_RESTORE.md`.
- Created a verified local Supabase dump at `/home/insanepc/backups/tutordex/supabase/tutordex-prod-supabase-postgres-20260614T052909Z.dump` with mode `0600`; `pg_restore --list` succeeds inside the Supabase Postgres container.
- Added `scripts/ops/supabase_backup_check.sh`; live check verifies latest dump age, size, and `pg_restore --list` readability.
- Added a staging/prod parity gate: smoke now checks real backend assignment routes, staging validation fails on non-staging Supabase network or enabled Telegram side effects, and `docs/STAGING_PROD_PARITY_CHECKLIST.md` documents the release gate.

## Recovery Still Needed

1. Fix public ingress on the router/modem path:

   - Forward external TCP `80` to `192.168.1.31:80`.
   - Forward external TCP `443` to `192.168.1.31:443`.
   - Ensure router remote management is not claiming `80`/`443`.
   - Ensure those ports are not forwarded to another device.
   - If the router WAN address is not `115.66.211.92`, resolve upstream double-NAT/CGNAT with bridge mode, upstream forwarding, or a public IP.

2. After router/NAT is fixed, verify:

   ```bash
   curl -i http://127.0.0.1:8000/health
   curl -i http://127.0.0.1:8000/health/dependencies
   curl -i https://tutordex-api.duckdns.org/health
   ```

3. Let recovery catchup drain and confirm the queue returns below alert thresholds.
4. Review and re-enable broadcast/DM side effects only after queue recovery is stable.
5. Fill the remaining staging config blockers documented in `docs/STAGING_PROD_PARITY_CHECKLIST.md`.
6. Wire `scripts/ops/supabase_backup.sh` and `scripts/ops/supabase_backup_check.sh` into host scheduling, then alert if the latest verified artifact is too old.

## Side-Effect Re-Enable Checklist

- Keep these off until queue recovery is fully quiet: `ENABLE_BROADCAST=0`, `ENABLE_DMS=0`, `DM_ENABLED=0`, `BROADCAST_SYNC_ON_STARTUP=0`, `FRESHNESS_PROPAGATE_TELEGRAM_ENABLED=0`, `FRESHNESS_DELETE_EXPIRED_TELEGRAM_ENABLED=0`.
- Confirm `pending=0`, `processing=0`, and no fresh failure spike before re-enabling.
- Re-enable broadcast before DMs, with a single worker replica and duplicate tracking enabled.
- Do not enable broadcast startup sync until `sync_broadcast_channel.py --dry-run` is reviewed.
- Re-enable DMs last, with low `DM_MAX_RECIPIENTS` and duplicate filtering enabled.
- Treat Telegram freshness edits/deletes as high-risk and leave delete disabled until a dry run is reviewed.

## Public Ingress Alternatives

If router access is unavailable, ranked fallback options are:

1. **Tailscale Funnel temporary restore**

   Fastest no-router workaround if Funnel is enabled for the tailnet. It would expose either the backend directly or Caddy through the Windows host's Tailscale hostname. This changes the public API URL, so Firebase Hosting must be rebuilt with a new `VITE_BACKEND_URL` and backend CORS must allow the Firebase Hosting origins.

   Example shape, not yet applied:

   ```bash
   tailscale funnel --bg --https=443 http://127.0.0.1:8000
   ```

   Rollback is to turn the funnel off, restore `VITE_BACKEND_URL=https://tutordex-api.duckdns.org`, and redeploy Firebase.

2. **Cloudflare Tunnel durable restore**

   Better long-term no-router path if a Cloudflare-managed domain is available. A tunnel can map a public hostname to `http://127.0.0.1:8000` or to the local Caddy ingress. This also requires changing `VITE_BACKEND_URL` and redeploying Firebase.

3. **Keep DuckDNS + Caddy**

   Lowest app-change path once router access is available. Current Caddy config is valid for `tutordex-api.duckdns.org`; the missing piece is WAN reachability to host ports `80`/`443`.
