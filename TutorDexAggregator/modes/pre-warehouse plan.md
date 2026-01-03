## No-warehouse-yet plan (frequent reparses)

This is a concrete approach when you expect to iterate often on prompt/schema/model and you do **not** have a separate warehouse yet.

### Core idea

- Keep `telegram_messages_raw` in prod indefinitely as your append-mostly source log.
- Treat `telegram_extractions` as a versioned, replayable work/output table keyed by `(raw_id, pipeline_version)`.

### Versioning rule (use `EXTRACTION_PIPELINE_VERSION`)

- Bump `EXTRACTION_PIPELINE_VERSION` whenever changes would alter extraction output (prompt/schema/model/LORA).
- Recommended format: `YYYY-MM-DD__schemaX__promptY__loraZ` (any unique string works).

### Repeatable reparse workflow (safe)

1) Pick a new pipeline version:
   - Either set `EXTRACTION_PIPELINE_VERSION=...` in `TutorDexAggregator/.env` (permanent), or
   - Set `EXTRACTION_PIPELINE_VERSION=...` in your shell for a one-off run.
2) Run **Mode 3** (enqueue from raw, bounded window first):
   - Start with a narrow window (e.g. last 7–14 days) and/or `MAX_MESSAGES_PER_CHANNEL` to iterate quickly.
3) Run **Mode 4** (drain without side effects):
   - Start with `MAX_JOBS = 50` as a smoke test.
   - Then remove the cap to drain fully.
4) Promote to live:
   - Keep Mode 1 on a stable version while experimenting.
   - Once satisfied, switch Mode 1 to the new `EXTRACTION_PIPELINE_VERSION` and re-enable side effects (broadcast/DMs).

### Keeping prod lean (optional)

- Don’t delete raw during experimentation; it’s what enables fast replays.
- If you need to reclaim space, prune **old `telegram_extractions`** for obsolete pipeline versions once you no longer need them (keep “current live” + last stable + any active experiment versions).
