# TutorDex Known Invariants

<!-- doc_lint:enforce -->
Doc type: Reference

**Docs metadata:**
**Status:** active
**Owner:** Mochi
**Last reviewed:** 2026-06-17
**Review trigger:** Update when data, extraction, side-effect, runtime, security, or documentation invariants change.

Assumptions and rules that future changes must preserve unless a task explicitly changes them and updates the docs/tests.

## Data Invariants

- `public.telegram_messages_raw` is the lossless raw log for Telegram-derived posts.
- Raw message identity is `(channel_link, message_id)` and backfill overlaps should upsert rather than duplicate.
- `public.telegram_extractions` is replayable work keyed by raw message and `pipeline_version`.
- `public.assignments` is a materialized projection for API/website use, not the raw source of truth.
- `published_at` means source publish time; `last_seen` or `source_last_seen` means observed by TutorDex.
- TutorCity identity uses stable assignment codes rather than Telegram raw ids.

## Extraction Invariants

- Deterministic extractors should not guess. Invalid or unsupported values should be nulled/dropped rather than invented.
- Postal-code regex fill is deterministic; estimated postal coordinates must remain marked as estimated.
- Time availability is deterministic and owns `canonical_json.time_availability`.
- Tutor type and rate signals from deterministic extractors are preferred for matching/materialized signal fields.
- Compilation splitting must fail closed against hallucinated identifiers.
- `EXTRACTION_PIPELINE_VERSION` is the isolation lane for prompt/schema/model reprocessing.

## Side-Effect Invariants

- Broadcasts and DMs are optional side effects.
- Manual reprocessing/backfills should disable broadcast/DM side effects unless explicitly intended.
- Telegram callback buttons require webhook handling; without webhook proof, callback click tracking is not proven.
- Click tracking uses cooldown behavior to avoid rapid duplicate increments.

## Runtime And Surface Invariants

- A local WSL/Docker result is not BizServer/public production proof.
- Status reports must name the checked surface.
- Staging and prod compose projects/env files must not be conflated.
- Firebase Hosting staging auto-deploys from `main`; Firebase Hosting production is manual `workflow_dispatch`.
- Production-changing operations require rollback and verification evidence.

## Security Invariants

- Never commit or paste `.env` contents, tokens, cookies, auth headers, service account JSON, Telegram session strings, Supabase service role keys, or Firebase private keys.
- Health/orientation helpers may report env file presence, but must not print env contents.
- Logs may contain sensitive material; summarize and redact before sharing.

## Documentation Invariants

- `AGENTS.md` remains the short agent doorway.
- `docs/SYSTEM_MAP.md` owns navigation and debug entry points.
- `docs/ARCHITECTURE.md` owns design boundaries and failure modes.
- `docs/OPERATIONS.md` owns operator procedures.
- `docs/TESTING.md` owns proof gates.
- `docs/DEPLOYMENT_TOPOLOGY.md` owns runtime/deploy surfaces.
- `docs/SYSTEM_INTERNAL.md` owns detailed current behavior.
- `docs/DOCS_CHANGE_POLICY.md` owns docs-routing expectations by changed path.
- `docs/adr/README.md` owns the repo-local decision index.
- `scripts/docs_health.py` is the local docs-health smoke for canonical docs.

When changing one of these invariants, update the owning doc and verification evidence in the same task.
