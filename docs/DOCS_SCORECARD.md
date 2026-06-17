# TutorDex SOTA Docs Scorecard

<!-- doc_lint:enforce -->
Doc type: Verification summary

**Docs metadata:**
**Status:** active
**Owner:** Mochi
**Last reviewed:** 2026-06-17
**Review trigger:** Update at the end of each TutorDex docs-system rollout or when docs-health criteria change.

## Result

TutorDex is classified as a critical ops / active product repo. The documentation target is Level 4 self-defending for runtime, deploy, data, and agent workflows.

Current score: **pass with residual monitoring gaps**.

## Checklist

- Root doorway: pass, `AGENTS.md`.
- Agent workflow integration: pass, `AGENTS.md`, `TutorDexAggregator/AGENTS.md`, `docs/DOCS_CHANGE_POLICY.md`, and `scripts/docs_health.py`.
- Canonical spine: pass, `docs/SYSTEM_MAP.md`, `docs/ARCHITECTURE.md`, `docs/KNOWN_INVARIANTS.md`, `docs/DEPLOYMENT_TOPOLOGY.md`, `docs/OPERATIONS.md`, `docs/TESTING.md`.
- ADR lane: pass, `docs/adr/README.md`, `docs/adr/ADR_TEMPLATE.md`.
- Metadata/freshness: pass for canonical docs enforced by `scripts/docs_health.py`.
- Generated inventory: pass, `docs/GENERATED_INVENTORY.md` and `scripts/docs_inventory.py`.
- Change-to-docs guard: pass, `docs/DOCS_CHANGE_POLICY.md` and `scripts/docs_change_guard.py`.
- CI warning-first docs health: pass, `.github/workflows/docs-health.yml`.
- Runtime proof matrix: pass, `docs/OPERATIONS.md` and `docs/DEPLOYMENT_TOPOLOGY.md`.
- Testing proof matrix: pass, `docs/TESTING.md`.
- Historical docs classification: pass, `docs/DOCS_CATALOG.md`.

## Residual Gaps

- Live BizServer, public ingress, Supabase, Firebase, and Telegram runtime checks are intentionally not proven by docs-only verification. They require explicit prod/staging ops tasks.
- Docs inventory is deterministic but intentionally compact; it is not a full dependency graph.
- Mermaid diagrams are source diagrams only; rendering is delegated to Markdown viewers.

## Final Recommendation

Use `python3 scripts/docs_health.py` as the required local docs smoke for TutorDex docs and ops changes. Use `python3 scripts/docs_change_guard.py --base HEAD` during task verification when changed paths might imply docs updates.
