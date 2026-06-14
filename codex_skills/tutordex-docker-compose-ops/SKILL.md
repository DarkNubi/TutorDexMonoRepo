---
name: tutordex-docker-compose-ops
description: TutorDex DevOps via docker compose (deploy, restart, rollback, status, ps, logs, services, containers) for staging/prod.
---

# TutorDex Docker Compose Ops

Use when asked to deploy/restart/check status or logs for TutorDex.

## Execution surface preflight

Before reporting service or container health, identify the active surface:
- host/shell: WSL local shell, BizServer Windows node, Docker Desktop, or inside a container
- docker context/endpoint used by the command
- compose project/env (`tutordex-staging` or `tutordex-prod`)
- public ingress path when claiming user-facing availability

Keep evidence surface-specific. A green WSL `localhost` check only proves the WSL route; it is not proof that the Windows node, Docker Desktop context, container network, or public ingress path is healthy. If BizServer is involved, verify the OpenClaw node connection and the Docker context before making health claims.

## Preferred commands (runbooks)

- `scripts/ops/status.sh --env staging|prod`
- `scripts/ops/logs.sh --env staging|prod [service] [--since=10m]`
- `scripts/ops/restart.sh --env staging|prod --service=<service> [--yes]`
- `scripts/ops/deploy.sh --env staging|prod [--yes]`
- `scripts/ops/rollback.sh --env staging|prod --to=<git-ref> [--yes]`
