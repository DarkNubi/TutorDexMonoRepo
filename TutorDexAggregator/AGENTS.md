# TutorDexAggregator - Agent Notes

This folder contains the Telegram ingestion + LLM extraction + broadcast pipeline for TutorDex.

Use this document as the "map" when making changes, debugging incidents, or adding new agencies.

## High-level flow (current queue pipeline)

1. `collector.py tail` connects to Telegram via Telethon and writes raw messages into `public.telegram_messages_raw`.
2. The collector enqueues extraction jobs into `public.telegram_extractions` via RPC (work queue by `(raw_id, pipeline_version)`).
3. `workers/extract_worker.py` claims jobs, loads raw text, applies filters (forwarded/deleted/compilation), then:
   - calls `extract_key_info.py` (LLM) for the v2 display fields
   - runs deterministic postal-code regex fill (no guessing)
   - runs deterministic time parsing (`extractors/time_availability.py`) and overwrites `canonical_json.time_availability`
   - runs hard validation (`hard_validator.py`) and canonicalization (null/drop invalid values)
   - runs deterministic signals (`signals_builder.py`) into `telegram_extractions.meta.signals`
4. `supabase_persist.py` materializes the latest extraction into `public.assignments` for the website/backend (including `signals_*` rollups).
5. `broadcast_assignments.py` and `dm_assignments.py` are optional side effects (best-effort).

## Entry points

- `collector.py`
  - `python collector.py tail`: tail live Telegram channels into `telegram_messages_raw`
  - `python collector.py enqueue`: enqueue a time window into `telegram_extractions`
- `workers/extract_worker.py`
  - `python workers/extract_worker.py`: run the queue worker loop
- `utilities/run_sample_pipeline.py`
  - Fast local dry-run against a single pasted post (no Supabase writes by default)

## File map (relevant)

- `extract_key_info.py`
  - Prompt/schema definitions.
  - Selects prompt examples based on source channel and files in `message_examples/`.
  - Calls the local LLM API (`LLM_API_URL`) and returns parsed JSON.
- `extractors/time_availability.py`
  - Deterministic parser that produces `canonical_json.time_availability`.
- `hard_validator.py`
  - Hard-null validator for the v2 `canonical_json` schema (never “fixes” by guessing).
- `signals_builder.py`
  - Deterministic academic/subject rollups for matching stored in `telegram_extractions.meta.signals`.
- `broadcast_assignments.py`
  - Builds Telegram HTML message text and enforces safe length limits.
  - Sends via Bot API when configured; otherwise appends to `outgoing_broadcasts.jsonl`.
- `logging_setup.py`
  - Shared logging config (console + rotating UTF-8 log file).
- `message_examples/`
  - Prompt examples stored as plain text for easy editing.
  - `general.txt` is the fallback; agency files are selected by `extract_key_info.build_prompt()`.
- `telesess.py`
  - Helper script to generate `SESSION_STRING` (reads `TELEGRAM_API_ID`/`TELEGRAM_API_HASH` from env).

## Payload shape (core contract)

The queue worker builds a payload with keys like:
- `channel_id`, `channel_username`, `channel_title`, `channel_link`
- `message_id`, `message_link`, `date`
- `raw_text`
- `parsed`: dict produced by `extract_key_info.extract_assignment_with_model(...)`

`payload['parsed']` is the v2 `canonical_json` display object:
- `assignment_code`, `academic_display_text`, `learning_mode`, `address[]`, `postal_code[]`, `nearest_mrt[]`
- `lesson_schedule[]`, `start_date`, `time_availability{explicit/estimated/note}`, `rate{min/max/raw_text}`, `additional_remarks`

Deterministic matching metadata lives in `payload['meta']['signals']` (and is also materialized into `public.assignments.signals_*`).

When changing the extraction schema, keep the worker, validator, persistence, and broadcaster expectations in mind.

## Adding a new agency (chat + examples)

1. Add an examples file: `message_examples/<agency>.txt`
2. Add an entry in `agency_registry.AGENCIES_BY_CHAT`:
   - `t.me/<ChannelUsername>` -> examples key + display name

Do not embed large examples directly in Python; keep them in files.

## Configuration (env vars)

See `README.md` and `.env.example` for the complete list.

Important:
- Do not commit secrets (`.env` is ignored).
- Avoid logging secrets (bot tokens, session strings). If you add logs, log identifiers and statuses, not credentials.

## Logging

Logging is configured via `logging_setup.setup_logging()`.

Defaults:
- Writes to `logs/tutordex_aggregator.log` (rotating).
- Also logs to console.

Useful env vars:
- `LOG_LEVEL`, `LOG_DIR`, `LOG_FILE`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`
- `LOG_TO_CONSOLE`, `LOG_TO_FILE`

When adding logs:
- Prefer `logger.info(...)` for lifecycle milestones (connect, watch channels, send success).
- Use `logger.warning(...)` for recoverable issues (validation failure, rate-limits, missing optional fields).
- Use `logger.exception(...)` inside `except` blocks for stack traces.
- Include `message_id` and `channel_link` when available.

## Network notes

This project may call:
- Telegram (Telethon) for reading messages.
- Telegram Bot API for broadcasting (optional).
- OpenStreetMap Nominatim for SG postal geocoding (lat/lon) (best-effort; should fail safely).
- Local LLM HTTP API (required for extraction).

Any of these may be blocked/unavailable depending on the runtime environment; error handling should degrade gracefully.

## Coding conventions (keep diffs small)

- Prefer targeted fixes over broad refactors.
- Keep prompt/schema edits consistent with example files in `message_examples/`.
- Do not add new dependencies unless necessary.
- Prefer UTF-8 text files; avoid smart quotes in docs to keep Windows terminals happy.

