---
name: tutordex-health-smoke
description: TutorDex health checks and smoke tests (backend health, worker/collector health, dependencies, readiness probes, observability checks).
---

# TutorDex Health + Smoke

Use when asked "is prod healthy?", "did deploy succeed?", or before/after changes.

## Canonical checks

- `scripts/ops/smoke.sh --env staging|prod`

## Topology details

- Aggregator worker/collector health is exposed via backend routes:
  - `/health/worker`, `/health/dependencies`, `/health/collector`
