# ADR: Isolated historical analysis replay

<!-- doc_lint:enforce -->
**Status:** accepted
**Date:** 2026-07-24
**Owners:** TutorDex Aggregator

## Decision

Run the one-time Telegram historical replay as a versioned extraction lane that does not materialize into the live `public.assignments` projection.

The raw backfill continues to use the existing raw identity `(channel_link, message_id)` and upsert behavior. Existing extraction results remain preserved because extraction rows are keyed by `(raw_id, pipeline_version)`. The replay uses a new `EXTRACTION_PIPELINE_VERSION` and the worker setting `EXTRACTION_MATERIALIZE_ASSIGNMENTS=0`.

Broadcast and DM side effects are disabled during the replay. The replay output is queried from `public.telegram_extractions` by pipeline version for downstream analysis.

## Why

Using the live pipeline version with force requeue would replace the canonical output for that version. Reusing the live `assignments` projection would also make a historical prompt/model experiment user-visible. A separate pipeline version plus analysis-only materialization preserves the old run and makes comparison and rollback straightforward.

## Operational boundaries

- Do not run the full backfill concurrently with the live Telethon collector using the same session.
- Run the backfill for the complete configured channel list and verify one successful `ingestion_runs` record per channel.
- Audit extraction statuses (`ok`, `failed`, `skipped`, `pending`) before analysis.
- Treat the analysis pipeline as incomplete until raw coverage and extraction coverage are reconciled per channel.

## Rollback

Stop or drain the analysis worker, then exclude the analysis `pipeline_version` from queries. Existing raw rows, prior extraction versions, and the live `assignments` projection remain available. No production deployment or database migration is required for the worker switch itself.
