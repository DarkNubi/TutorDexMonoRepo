# TutorDex Deployment Release Flow

## Current deploy surfaces

TutorDex has two production-facing deploy paths:

- `deploy.yml`: runs automatically on pushes to `main`; connects to the Windows server through Tailscale SSH, pulls the latest code under `D:/TutorDex`, then runs `docker compose up -d --build --pull=never`.
- `firebase-hosting.yml`: runs automatically on pushes to `main` for Firebase Hosting target `staging`; deploys Firebase Hosting target `prod` only when manually started with `workflow_dispatch`.

## Release policy

Keep Firebase Hosting production as a deliberate manual promotion. The website is public-facing, so staging should receive the automatic deploy first and production should follow only after a smoke check.

Do not describe Firebase Hosting production as auto-deployed from `main`. Only Firebase Hosting staging is automatic.

## Normal release checklist

1. Merge or push the intended changes to `main`.
2. Confirm `.github/workflows/deploy.yml` completed successfully.
3. Confirm `.github/workflows/firebase-hosting.yml` completed its automatic `deploy_staging` job successfully.
4. Smoke test Firebase staging against the deployed backend.
5. If staging is healthy, manually run `.github/workflows/firebase-hosting.yml` from GitHub Actions.
6. Confirm the manual `deploy_prod` job completed successfully.
7. Smoke test Firebase production.

## Recommended guardrails

- Keep the GitHub `production` environment protected so `deploy_prod` is a conscious approval step.
- Prefer staging smoke evidence before running the production workflow.
- If auto deploy fails, fix or rerun the workflow instead of deploying Firebase Hosting from a local machine.
- Longer term, prefer building one frontend artifact and promoting that exact artifact from staging to production.

## Source of truth

The workflow files are the operational source of truth:

- `.github/workflows/deploy.yml`
- `.github/workflows/firebase-hosting.yml`

Keep this document, `docs/SYSTEM_INTERNAL.md`, `docs/codex-instructions.md`, and `.github/copilot-instructions.md` aligned whenever deploy behavior changes.
