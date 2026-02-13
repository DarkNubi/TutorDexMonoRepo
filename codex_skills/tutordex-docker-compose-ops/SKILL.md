---
name: tutordex-docker-compose-ops
description: TutorDex DevOps via docker compose (deploy, restart, rollback, status, ps, logs, services, containers) for staging/prod.
---

# TutorDex Docker Compose Ops

Use when asked to deploy/restart/check status or logs for TutorDex.

## Preferred commands (runbooks)

- `scripts/ops/status.sh --env staging|prod`
- `scripts/ops/logs.sh --env staging|prod [service] [--since=10m]`
- `scripts/ops/restart.sh --env staging|prod --service=<service> [--yes]`
- `scripts/ops/deploy.sh --env staging|prod [--yes]`
- `scripts/ops/rollback.sh --env staging|prod --to=<git-ref> [--yes]`
