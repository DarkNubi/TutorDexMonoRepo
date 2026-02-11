# TutorDex Ops Autonomy Policy (Default)

This policy defines what an automated agent may do without human approval.

## Environments

- **staging**: default environment for automated changes and tests.
- **prod**: production; stricter gating.

## Tier A — Allowed automatically

- Read-only diagnostics (logs, metrics, health checks).
- Local/staging changes: code edits, formatting, unit tests, smoke tests.
- Staging deployment and restarts.
- Creating PRs (if your workflow uses them) and writing incident notes.

## Tier B — Allowed automatically with rollback plan

- Production deploys and restarts **only via runbook scripts** and only after smoke checks pass.
- Bounded reprocessing/backfills (must have hard limits on time window / row counts).
- Creating temporary Alertmanager silences with a short TTL.

## Tier C — Human-gated

- Schema migrations in production.
- Arbitrary SQL execution in production.
- Bulk destructive operations (deletes, mass updates).
- Any changes to secrets, keys, or auth configuration.

## Always

- Prefer read-only steps first.
- Never print secrets to logs/output.
- Every action should produce an audit trail (command + env + timestamps).

