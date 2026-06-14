# Staging/Prod Parity Checklist

Use this before promoting Firebase Hosting production or trusting staging as a release gate. Do not paste env files, tokens, service-role keys, Firebase admin JSON, or Telegram session strings into chat or logs.

## Why Staging Missed the Recovery Regressions

- Backend deploy is production-only in `.github/workflows/deploy.yml`; Firebase Hosting staging auto-deploys from `main`, but the backend stack is not automatically deployed to a staging backend first.
- Staging env validation currently fails for production-like dependencies: Firebase admin JSON, backend Supabase enablement/URLs/key, aggregator Supabase raw ingest, Telegram collector credentials, DM bot token, and alert destination/token.
- Previous smoke expectations were mostly health/RPC checks. They did not directly fail if the backend `/assignments` or `/assignments/facets` routes were broken while Supabase RPCs existed.
- Public API outage was only visible after adding blackbox probes for `https://tutordex-api.duckdns.org`; Firebase Hosting can still serve static pages while assignment loading fails.
- Alerting parity requires a configured staging alert route. Without a staging alert bot/chat or explicit no-send verification route, staging cannot prove Alertmanager delivery.

## Required Staging Shape

- Root env: `.env.staging` has `APP_ENV=staging`, staging ports, and a staging-specific `SUPABASE_NETWORK`.
- Backend env: `SUPABASE_ENABLED=true`, `SUPABASE_URL_DOCKER`, `SUPABASE_URL_HOST`, `SUPABASE_SERVICE_ROLE_KEY`, `REDIS_URL`, and `ADMIN_API_KEY` are configured for staging resources.
- Aggregator env: `SUPABASE_ENABLED=true`, `SUPABASE_RAW_ENABLED=true`, `SUPABASE_URL_DOCKER`, `SUPABASE_URL_HOST`, `SUPABASE_SERVICE_ROLE_KEY`, `CHANNEL_LIST`, Telegram API/session credentials, `EXTRACTION_PIPELINE_VERSION`, and `SCHEMA_VERSION` are configured for staging.
- Staging side effects stay disabled unless an explicit test window is approved: `ENABLE_BROADCAST=0`, `ENABLE_DMS=0`, `DM_ENABLED=0`, `BROADCAST_SYNC_ON_STARTUP=0`, `FRESHNESS_PROPAGATE_TELEGRAM_ENABLED=0`, `FRESHNESS_DELETE_EXPIRED_TELEGRAM_ENABLED=0`.
- Alerting has a staging-safe destination or a documented no-send test route; do not point staging at production tutor/broadcast channels.
- Firebase staging build uses a staging `VITE_BACKEND_URL` that reaches the staging backend. Production Firebase uses the production backend URL only after staging smoke passes.

## Safe Validation Commands

These checks are read-only except for normal audit logging by ops scripts:

```bash
./scripts/validate_env.sh .env.staging
./scripts/ops/smoke.sh --env staging
./scripts/validate_env.sh .env.prod
./scripts/ops/smoke.sh --env prod
```

The smoke path now checks backend health, Redis/Supabase health, backend `/assignments`, backend `/assignments/facets`, direct Supabase assignment RPCs, worker/collector health, and observability readiness.

## Release Gate

1. Validate staging env.
2. Deploy or update the staging backend stack only, with broadcast/DM/freshness Telegram side effects disabled.
3. Run staging smoke.
4. Confirm Firebase Hosting staging was built with the staging backend URL.
5. Load Firebase staging assignments from a browser or browser automation and confirm assignments render.
6. Only then manually promote Firebase Hosting production.
7. Run prod smoke against the local backend and the public API once router/NAT ingress is fixed.

## Remaining Automation Gap

CI does not yet enforce a staging backend deploy plus browser-level Firebase staging assignment smoke. Until that exists, staging parity depends on the manual checklist above.
