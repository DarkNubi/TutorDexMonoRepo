# AGENTS.md - TutorDex Agent Entry

<!-- doc_lint:enforce -->
Doc type: Agent doorway

**Docs metadata:**
**Status:** active
**Owner:** Mochi
**Last reviewed:** 2026-07-01
**Review trigger:** Update when TutorDex agent startup, docs routing, runtime proof, safety, or verification expectations change.

This repo runs a tuition assignment aggregator: Telegram collection, LLM/deterministic extraction, Supabase persistence, matching, notifications, website, and observability.

## Start Here

Use these docs in this order:

1. `AGENTS.md` - short agent rules and map.
2. `docs/SYSTEM_MAP.md` - skimmable repo navigation and debug entry points.
3. `docs/ARCHITECTURE.md` - design boundaries, invariants, and failure modes.
4. `docs/KNOWN_INVARIANTS.md` - rules that must not break.
5. `docs/DEPLOYMENT_TOPOLOGY.md` - runtime/deploy surfaces and proof boundaries.
6. `docs/TESTING.md` - proof gates and smoke checks.
7. `docs/OPERATIONS.md` - current operational runbook and proof expectations.
8. `docs/DOCS_CHANGE_POLICY.md` - change-to-docs routing and local guard.
9. `docs/adr/README.md` - repo-local decision lane.
10. `docs/SYSTEM_INTERNAL.md` - detailed authoritative system behavior.
11. Component docs only after that:
   - `TutorDexAggregator/AGENTS.md`
   - `TutorDexAggregator/README.md`
   - `TutorDexBackend/README.md`
   - `TutorDexWebsite/README.md`
   - `observability/README.md`

Historical reports under `docs/archive/` and dated audit/refactor docs are useful context, not the current source of truth.

## Strawberry HQ Documentation Model

TutorDex follows the Strawberry HQ docs architecture:

- Short repo-wide agent rules live here.
- Skimmable repo navigation lives in `docs/SYSTEM_MAP.md`.
- Architecture boundaries and invariants live in `docs/ARCHITECTURE.md`.
- Must-not-break assumptions live in `docs/KNOWN_INVARIANTS.md`.
- Runtime/deploy surfaces live in `docs/DEPLOYMENT_TOPOLOGY.md`.
- Test and proof gates live in `docs/TESTING.md`.
- Current operator procedures live in `docs/OPERATIONS.md`.
- Detailed architecture behavior and data-flow contracts live in `docs/SYSTEM_INTERNAL.md`.
- Component-specific behavior lives beside the component.
- Repo-local ADRs live in `docs/adr/`; use Strawberry HQ `memory/decisions/` only for global policy.
- Change-to-docs routing lives in `docs/DOCS_CHANGE_POLICY.md`.
- Temporary plans, proof, audits, and verification notes belong in Strawberry HQ `workspace/state_saves/**`, not as new repo policy.

When changing behavior, update the narrowest correct doc in the same task. Do not dump long procedures into this file.

## Execution Surfaces

Always state which surface you checked before claiming health:

- WSL/local shell
- BizServer Windows node
- Docker Desktop context
- in-container command
- public ingress/API URL
- Supabase/PostgREST/RPC surface

Do not treat WSL `localhost`, local Docker, or an old compose project as production proof. If the request is about live TutorDex, verify the BizServer/public path or clearly say that you only checked local state.

Before making any TutorDex runtime, deployment, prod-health, outage, or recovery claim, re-enter through the `Start Here` docs above and the proof matrices in `docs/TESTING.md`, `docs/OPERATIONS.md`, and `docs/DEPLOYMENT_TOPOLOGY.md`. Name the doorway docs and exact surfaces checked in the final assertion; if you only continued from a narrow investigation thread, say the claim is partial until that doorway/proof pass is complete.

## Safe First Commands

Read-only orientation:

```bash
python3 scripts/docs_health.py
python3 scripts/docs_change_guard.py --base HEAD
./scripts/tutordex_healthcheck.sh
./scripts/tutordex_healthcheck.sh --env prod
./scripts/ops/status.sh --env staging
./scripts/ops/status.sh --env prod
```

Smoke checks:

```bash
./scripts/ops/smoke.sh --env staging
./scripts/ops/smoke.sh --env prod
```

Prod-changing commands require the repo runbooks and explicit confirmation flags. Prefer `scripts/ops/*` over ad-hoc Docker commands.

## Safety Rules

- Never print secrets, `.env` contents, tokens, cookies, session strings, or auth headers.
- Do not edit env files, restart prod services, run migrations, or trigger backfills unless the task explicitly calls for it.
- Do not deploy TutorDex from a local machine or by direct/manual server push. Use the GitHub Actions paths triggered by branch/`main` pushes and manual workflow dispatch; if they fail, fix or rerun the workflow.
- Prefer staging unless the user explicitly asks about prod or the incident is already known to be prod.
- For prod changes, include rollback path and verification evidence.
- Keep collector, worker, queue, and website/API evidence separate.

## Common Areas

- `TutorDexAggregator/` - Telegram collector, extraction queue worker, LLM parser, deterministic hardening, broadcast/DM side effects.
- `TutorDexBackend/` - FastAPI matching engine and API.
- `TutorDexWebsite/` - React/Vite/Firebase website.
- `shared/` - shared contracts and taxonomy.
- `scripts/ops/` - canonical deploy, status, logs, restart, rollback, smoke, and Supabase ops helpers.
- `observability/` - Prometheus, Grafana, Alertmanager, Tempo/OTEL docs and config.

## Verification Expectations

For non-trivial work, report:

- files changed
- invariant at risk
- proving check
- pass/fail result
- rollback path

Run `python3 scripts/docs_health.py` for docs or ops changes. Run `python3 scripts/docs_change_guard.py --base HEAD` when changed paths may imply documentation updates.

If you did not run a check, say so. If a check only covers local/WSL state, do not present it as BizServer or public production proof.
