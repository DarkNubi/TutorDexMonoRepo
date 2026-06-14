---
name: tutordex-platform-ops
description: TutorDex umbrella skill for anything in this repo (coding, debugging, deploy, prod/staging, docker compose, logs, smoke tests, monitoring, Supabase/PostgREST/RPC, Grafana/Prometheus/Alertmanager, migrations, incidents).
---

# TutorDex Platform Ops

Use this skill when asked to deploy, monitor, debug incidents, or operate TutorDex environments.

## Safety rules (default)

- Prefer **staging** unless explicitly told **prod**.
- For prod changes, require a runbook + rollback path.
- Never print secrets; do not echo env files.
- Use the repo runbooks in `scripts/ops/*` instead of ad-hoc docker commands.
- Before reporting service/container health, state the execution surface you actually checked:
  host or shell (`WSL`, `BizServer Windows node`, `Docker Desktop`, container), docker context/endpoint, compose project/env, and public ingress path if claiming user-facing availability.
- Keep WSL-local, Windows-node, Docker-context, in-container, and public-ingress evidence separate. Do not treat `localhost` from one surface as proof for another.
- For BizServer/Docker Desktop ambiguity, verify with the active OpenClaw node status plus the Docker context used by the command before making status claims.

## Environment selection

- Use `--env staging` or `--env prod` for all ops scripts.
- Prod scripts require `--yes` (or `TD_YES=yes`).

## Canonical runbooks

- Status: `scripts/ops/status.sh --env staging|prod`
- Deploy: `scripts/ops/deploy.sh --env staging|prod [--yes]`
- Rollback: `scripts/ops/rollback.sh --env staging|prod --to=<git-ref> [--yes]`
- Restart service: `scripts/ops/restart.sh --env staging|prod --service=<name> [--yes]`
- Logs: `scripts/ops/logs.sh --env staging|prod [service] [--since=...]`
- Smoke tests: `scripts/ops/smoke.sh --env staging|prod`

## Data access standard (Supabase)

- Do **not** attempt to drive Supabase Studio UI.
- Prefer whitelisted RPCs (agent gateway) over arbitrary SQL.
