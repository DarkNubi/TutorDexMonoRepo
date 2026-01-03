# Automated Outage Recovery (Collector Catchup)

TutorDex uses `telegram_messages_raw` as an immutable raw log and `telegram_extractions` as a replayable queue keyed by `(raw_id, pipeline_version)`.

This repo now supports automated “gap healing” after outages.

## What runs in production

Docker Compose services:
- `collector-tail`: runs `python collector.py live`
- `aggregator-worker`: runs `python workers/extract_worker.py`

`collector.py live` does two things:
1) Runs `collector.py tail` (real-time new messages/edits/deletes).
2) Runs a **catchup backfill** after restart to heal gaps, in bounded chunks, **only when the extraction queue is drained/low**.

## How catchup works

- On startup, catchup initializes per-channel cursors from the latest persisted raw message timestamps in Supabase (best-effort).
- It sets a `target_iso = now - RECOVERY_CATCHUP_TARGET_LAG_MINUTES` and advances each channel’s cursor forward in `RECOVERY_CATCHUP_CHUNK_HOURS` slices.
- After each slice, it waits until `telegram_extractions` backlog (pending+processing) is below `RECOVERY_CATCHUP_QUEUE_LOW_WATERMARK` before doing the next slice.

State is persisted to `state/recovery_catchup_state.json` so it can resume if restarted mid-catchup.

## Environment variables

Recommended defaults (all optional):
- `RECOVERY_CATCHUP_ENABLED=1`
- `TG_SESSION_RECOVERY=tutordex_recovery.session` (separate Telethon session for catchup)
- `SESSION_STRING_RECOVERY=...` (optional; if unset, catchup reuses `SESSION_STRING` when available)
- `RECOVERY_CATCHUP_CHUNK_HOURS=6`
- `RECOVERY_CATCHUP_QUEUE_LOW_WATERMARK=0`
- `RECOVERY_CATCHUP_CHECK_INTERVAL_SECONDS=30`
- `RECOVERY_CATCHUP_TARGET_LAG_MINUTES=2`
- `RECOVERY_CATCHUP_OVERLAP_MINUTES=10`
- `RECOVERY_CATCHUP_STATE_FILE=state/recovery_catchup_state.json`

## Operational notes

- Catchup uses Telegram history reads. On very large gaps, you may still hit Telegram rate limits (FloodWait); catchup is designed to progress gradually.
- Catchup enqueues extraction work via the existing queue RPC (`enqueue_telegram_extractions`). If you disable enqueue (`EXTRACTION_QUEUE_ENABLED=0`), catchup will still backfill raw but won’t schedule extraction.
- If you need a manual one-off backfill/reparse, the `TutorDexAggregator/modes/` scripts still work.
