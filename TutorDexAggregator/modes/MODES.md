# TutorDex Aggregator — Operational Modes

This folder contains “click-run” wrappers for **manual** operational modes.

Design goals:
- Do not duplicate pipeline logic (wrappers only import and call the real modules).
- Keep the “source of truth” in `TutorDexAggregator/collector.py` and `TutorDexAggregator/workers/extract_worker.py`.
- Use `telegram_messages_raw` as the immutable raw event log; reprocessing is done by re-enqueuing work in `telegram_extractions`.

## Mode 1 — Live (Docker, long-running)

**Purpose:** 24/7 ingestion + extraction.

**What runs:**
- `collector.py tail` (live raw ingest of new messages/edits/deletes into `telegram_messages_raw`)
- `workers/extract_worker.py` (claims `telegram_extractions` and performs extraction + downstream writes; may broadcast/DM depending on env)

**Notes:**
- Live mode is the only one intended to run continuously.
- If you run a backfill that connects to Telegram, avoid running it concurrently with live mode using the same Telethon session.

## Mode 2 — Backfill missing raw data (Manual)

**Purpose:** Fill gaps in `telegram_messages_raw` caused by downtime (Telegram → raw store recovery).

**How it works (high level):**
- Reads historical messages from Telegram for a time window / channel list
- Upserts into `telegram_messages_raw`
- Optionally enqueues extraction jobs for the inserted message ids (default is not “force reparse”)

**Runner:** `TutorDexAggregator/modes/mode2_backfill_missing_raw.py`

**Use when:**
- Server was down and you want to re-capture the missed raw messages.

## Mode 3 — Re-parse / re-enqueue from raw (Manual)

**Purpose:** Re-run extraction after changing prompt/schema/model *without* re-reading Telegram.

**How it works (high level):**
- Scans existing `telegram_messages_raw` rows (optionally for a time window)
- Enqueues work into `telegram_extractions`
- For “reparse” you usually either:
  - bump `EXTRACTION_PIPELINE_VERSION` (creates a new `(raw_id, pipeline_version)` job), or
  - keep the same version but run with `force=True` (reprocess non-`ok` or reset `ok` back to `pending`)

**Runner:** `TutorDexAggregator/modes/mode3_reparse_enqueue_from_raw.py`

**Use when:**
- You updated system prompt/schema/logic and want to regenerate canonical output for historical raw messages.

### Bumping `EXTRACTION_PIPELINE_VERSION` (recommended)

This is how you “version” extraction outputs and safely reprocess from raw:

- **Permanent (live Mode 1):** set `EXTRACTION_PIPELINE_VERSION` in `TutorDexAggregator/.env`, then restart the docker stack.
  - Example: `EXTRACTION_PIPELINE_VERSION=2025-12-31_v3`
- **One-off (Mode 3 runner):** set `PIPELINE_VERSION_OVERRIDE` inside `TutorDexAggregator/modes/mode3_reparse_enqueue_from_raw.py`.
  - Example: `PIPELINE_VERSION_OVERRIDE = "2025-12-31_v3"`

When you bump the version, the queue keys by `(raw_id, pipeline_version)`, so you get a clean new set of jobs without mutating the old run history.

## Mode 4 — Process queue without side effects (Manual)

**Purpose:** Drain/execute extraction jobs safely (no broadcast, no tutor DMs).

**How it works (high level):**
- Runs the extraction worker with:
  - `EXTRACTION_WORKER_BROADCAST=0`
  - `EXTRACTION_WORKER_DMS=0`
  - `EXTRACTION_WORKER_ONESHOT=1` (exit once queue is empty)
  - optional `EXTRACTION_WORKER_MAX_JOBS=N` (stop after N jobs)

**Runner:** `TutorDexAggregator/modes/mode4_drain_queue_no_side_effects.py`

**Use when:**
- You want to validate a reparse/re-enqueue on production data without spamming the Telegram channel / users.

## Recommended workflow (common scenarios)

### Common prerequisites (all modes)

- **DB schema + RPC installed:** ensure your DB has `telegram_messages_raw`, `telegram_extractions`, and the queue RPC helpers from `TutorDexAggregator/supabase sqls/2025-12-22_extraction_queue_rpc.sql`.
- **Supabase access (service role):** set:
  - `SUPABASE_URL=https://...` (no trailing slash)
  - `SUPABASE_SERVICE_ROLE_KEY=...`
  - `SUPABASE_ENABLED=1` (required by the extraction worker)
  - `SUPABASE_RAW_ENABLED=1` (required by the raw collector + enqueue-from-raw)
- **Enable/disable the extraction queue:**
  - `EXTRACTION_QUEUE_ENABLED=1` to enqueue jobs into `telegram_extractions`
  - `EXTRACTION_QUEUE_ENABLED=0` if you want to collect raw only (no enqueue)
- **Channel list format:** `CHANNEL_LIST` can be either:
  - comma-separated: `CHANNEL_LIST=t.me/SomeChannel,t.me/OtherChannel`
  - JSON array: `CHANNEL_LIST=["t.me/SomeChannel","t.me/OtherChannel"]`
- **Time window format (recommended):** ISO 8601 with timezone (prefer UTC), e.g.
  - `2025-12-29T00:00:00+00:00`
  - `2025-12-30T00:00:00+00:00`
  Notes:
  - `since` is treated as inclusive (`>=`)
  - `until` is treated as exclusive-ish (`<`)
  - When recovering from downtime, add a small buffer (e.g. start 5–10 minutes earlier than the actual downtime start).

### Scenario: Downtime recovery (raw missing → then extract)

Goal: “I missed Telegram messages while Mode 1 was down; recover them and extract them safely.”

1) **Prep**
   - Ensure `.env` has Telegram creds for Mode 2 (collector backfill):
     - `TELEGRAM_API_ID=...`
     - `TELEGRAM_API_HASH=...`
     - optional: `SESSION_STRING=...` (otherwise uses `TG_SESSION=tutordex.session`)
   - Ensure `.env` has Supabase raw enabled:
     - `SUPABASE_RAW_ENABLED=1`
   - Decide if you want automatic enqueue during backfill:
     - recommended: `EXTRACTION_QUEUE_ENABLED=1`

2) **Mode 2: Backfill raw**
   - Edit `TutorDexAggregator/modes/mode2_backfill_missing_raw.py` values:
     - `SINCE_ISO = "2025-12-29T02:00:00+00:00"`
     - `UNTIL_ISO = "2025-12-29T06:00:00+00:00"`
     - optional: `CHANNELS = "t.me/SomeChannel,t.me/OtherChannel"` (defaults to `CHANNEL_LIST`)
     - optional smoke run: `MAX_MESSAGES_PER_CHANNEL = 50`
   - Run the file in VS Code.

3) **Mode 4: Drain queue safely**
   - Edit `TutorDexAggregator/modes/mode4_drain_queue_no_side_effects.py` values:
     - `ONESHOT = True` (recommended)
     - optional smoke run: `MAX_JOBS = 50`
     - optional: `PIPELINE_VERSION_OVERRIDE = "..."` (only if you intentionally want a non-default version)
   - Run the file in VS Code.
   - If results look correct, run the real worker normally (Mode 1) to resume side effects.

### Scenario: Prompt/schema/model change reparse (no Telegram reads)

Goal: “I changed extraction logic; regenerate outputs for historical raw messages.”

1) **Pick a new pipeline version (recommended)**
   - Use a monotonic, human-readable string, e.g.
     - `2025-12-31_schema_v3`
     - `2025-12-31_prompt_v4`
   - Either set in `TutorDexAggregator/.env` (permanent), or use the Mode 3 runner override.

2) **Mode 3: Enqueue from raw**
   - Ensure:
     - `SUPABASE_RAW_ENABLED=1`
     - `EXTRACTION_QUEUE_ENABLED=1`
   - Edit `TutorDexAggregator/modes/mode3_reparse_enqueue_from_raw.py` values:
     - `PIPELINE_VERSION_OVERRIDE = "2025-12-31_schema_v3"` (recommended)
     - `SINCE_ISO = "2025-12-01T00:00:00+00:00"` (optional)
     - `UNTIL_ISO = "2026-01-01T00:00:00+00:00"` (optional)
     - optional smoke run: `MAX_MESSAGES_PER_CHANNEL = 200`
     - keep `FORCE = True` if you want to re-enqueue even if rows already exist for the same version.
       - If you bump the version, `FORCE` usually doesn’t matter (it’s a new key).
   - Run the file in VS Code.

3) **Mode 4: Drain queue safely**
   - Set `PIPELINE_VERSION_OVERRIDE` to match the reparse version (if you used one).
   - Run Mode 4; start with `MAX_JOBS = 50` if you want a quick sanity run.

### Scenario: “Raw is correct, but worker was down” (enqueue-only recovery)

Goal: “Raw collector (Mode 1) was running, but extraction worker wasn’t; enqueue the missing window without Telegram calls.”

1) Ensure:
   - `SUPABASE_RAW_ENABLED=1`
   - `EXTRACTION_QUEUE_ENABLED=1`

2) Run **Mode 3** with the downtime window (keep the current pipeline version).

3) Run **Mode 4** to drain safely.

### Scenario: Add a new channel/agency

Goal: “Start collecting a new channel, then optionally backfill history.”

1) Add the channel to `CHANNEL_LIST` (format above).
2) Restart Mode 1 (so `collector tail` starts tracking it).
3) If you want history, run **Mode 2** with a wider `SINCE_ISO/UNTIL_ISO` window for that specific channel.

### Scenario: Safe smoke test after deployment

Goal: “I deployed code changes and want to validate extraction without spamming Telegram.”

1) Set `EXTRACTION_PIPELINE_VERSION` to a new value (or choose a narrow time window).
2) Run **Mode 3** with `MAX_MESSAGES_PER_CHANNEL = 50`.
3) Run **Mode 4** with `MAX_JOBS = 50` and confirm results.
4) Switch back to Mode 1 with side effects enabled.

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
   - Set `PIPELINE_VERSION_OVERRIDE = "..."` in `TutorDexAggregator/modes/mode3_reparse_enqueue_from_raw.py` (one-off).
2) Run **Mode 3** (enqueue from raw, bounded window first).
3) Run **Mode 4** (drain without side effects).
4) Promote to live by switching Mode 1 to the new version and re-enabling side effects.

### Keeping prod lean (optional)

- Don’t delete raw during experimentation; it’s what enables fast replays.
- If you need to reclaim space, prune **old `telegram_extractions`** for obsolete pipeline versions once you no longer need them.

## A/B testing prompts/models (practical setup)

You can A/B both **models** and **system prompts** by doing two runs against the same raw inputs:

1) Choose two run ids:
   - `EXTRACTION_PIPELINE_VERSION=ab_2025-12-31_promptA_modelA`
   - `EXTRACTION_PIPELINE_VERSION=ab_2025-12-31_promptB_modelB`
2) Configure the model per run:
   - `LLM_API_URL=...`
   - `LLM_MODEL_NAME=...`
3) Configure the system prompt per run (new):
   - `LLM_SYSTEM_PROMPT_FILE=relative/or/absolute/path/to/prompt.txt`, or
   - `LLM_SYSTEM_PROMPT_VARIANT=foo` (loads `TutorDexAggregator/prompts/system_prompt_foo.txt` if it exists), or
   - `LLM_SYSTEM_PROMPT_TEXT=...` (inline; convenient but harder to audit)
4) For each run:
   - Run Mode 3 for a fixed time window.
   - Run Mode 4 with `PIPELINE_VERSION_OVERRIDE` set to that run id.

The extraction worker persists the prompt fingerprint into `telegram_extractions.meta.prompt` so you can trace and compare runs reliably.

## Analytics + comparisons

For automated A/B stats + per-field side-by-side output, see:
- `TutorDexAggregator/utilities/AB_TESTING.md`
- `TutorDexAggregator/utilities/ab_experiment.py`
