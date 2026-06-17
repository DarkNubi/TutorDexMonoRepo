# TutorDex Change-To-Docs Policy

<!-- doc_lint:enforce -->
Doc type: Policy

**Docs metadata:**
**Status:** active
**Owner:** Mochi
**Last reviewed:** 2026-06-17
**Review trigger:** Update when repo areas, canonical docs, docs health checks, CI docs gates, or task verification rules change.

Use this policy before verification for any non-trivial TutorDex task. Documentation belongs in the same task as the behavior change, not in a separate follow-up pile.

## Routing Matrix

| Changed area | Required docs decision |
| --- | --- |
| `AGENTS.md`, child `AGENTS.md` | Update the relevant agent doorway and run `python3 scripts/docs_health.py`. |
| `TutorDexAggregator/**` extraction, worker, persistence, broadcast, DM, recovery | Check `docs/ARCHITECTURE.md`, `docs/KNOWN_INVARIANTS.md`, `docs/SYSTEM_INTERNAL.md`, component README, and `docs/TESTING.md`. Add an ADR if queue/data ownership changes. |
| `TutorDexBackend/**` API, auth, matching, Redis, analytics, Telegram routes | Check `docs/ARCHITECTURE.md`, `docs/SYSTEM_INTERNAL.md`, backend README, `docs/TESTING.md`, and `docs/DEPLOYMENT_TOPOLOGY.md` if runtime exposure changes. |
| `TutorDexWebsite/**` user-visible UI, Firebase Auth, API expectations | Check website README, `docs/SYSTEM_INTERNAL.md`, `docs/TESTING.md`, and `docs/DEPLOYMENT_RELEASE_FLOW.md` if deploy behavior changes. |
| `shared/**` contracts, taxonomy, config | Check all component docs that consume the contract plus `docs/KNOWN_INVARIANTS.md`. |
| `scripts/ops/**`, `docker-compose.yml`, `.github/workflows/**` | Update `docs/OPERATIONS.md`, `docs/DEPLOYMENT_TOPOLOGY.md`, `docs/TESTING.md`, and `docs/GENERATED_INVENTORY.md`; add ADR for durable deploy policy changes. |
| `observability/**` | Check `observability/README.md`, relevant runbook, `docs/OPERATIONS.md`, and runtime proof matrix. |
| `docs/**` | Update `docs/DOCS_CATALOG.md`, metadata, doorway pointers, and docs health checks as needed. |

If no docs update is needed, the verification artifact must say which docs were checked and why they remain authoritative.

## Local Guard

Run:

```bash
python3 scripts/docs_change_guard.py --base HEAD
```

The guard is advisory. It reports changed path groups and the docs that should be inspected. It does not read env files, secrets, logs, or production state.

Use `--changed-file <path>` for task evidence when checking a synthetic or staged path list.

