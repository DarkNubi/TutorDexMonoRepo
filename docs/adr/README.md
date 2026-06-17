# TutorDex ADR Index

<!-- doc_lint:enforce -->
Doc type: Decision index

**Docs metadata:**
**Status:** active
**Owner:** Mochi
**Last reviewed:** 2026-06-17
**Review trigger:** Update when TutorDex architectural decisions, runtime ownership, deployment policy, data contracts, or documentation-routing rules change.

This directory is the repo-local home for TutorDex architecture decision records. Use it for decisions that belong to TutorDex itself. Keep Strawberry HQ-wide agent policy in `memory/decisions/` instead.

## When To Add An ADR

Add or update an ADR when a change affects:

- data ownership, queue semantics, extraction pipeline versioning, or persistence contracts
- deploy/release topology, production rollback, or public ingress ownership
- security boundaries, secret-handling rules, or side-effect policy
- cross-component API contracts between aggregator, backend, website, shared code, or observability
- docs architecture rules that future TutorDex agents must follow

Do not add an ADR for routine bug fixes unless the fix changes a durable rule.

## Current Decisions

- [ADR-0001: Supabase client consolidation](../ADR-0001-SUPABASE-CLIENT-CONSOLIDATION.md) - historical repo decision kept in `docs/` for compatibility; future ADRs should live in this directory.

## New ADR Workflow

1. Copy [ADR_TEMPLATE.md](ADR_TEMPLATE.md) to `ADR-000N-short-title.md`.
2. Fill the metadata block, decision, consequences, rollback, and verification sections.
3. Link the ADR from this index.
4. Update `docs/SYSTEM_MAP.md`, `docs/ARCHITECTURE.md`, `docs/KNOWN_INVARIANTS.md`, or `docs/OPERATIONS.md` if the decision changes active behavior.
5. Run `python3 scripts/docs_health.py` before verification.

