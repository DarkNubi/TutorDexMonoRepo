# TutorDexAggregator - Agent Notes

This folder contains the Telegram ingestion + LLM extraction + broadcast pipeline for TutorDex.

Use this document as the "map" when making changes, debugging incidents, or adding new agencies.

## High-level flow

1. `read_assignments.py` connects to Telegram via Telethon and listens to channels in `CHANNEL_LIST`.
2. Each message is filtered (forwarded posts skipped; compilation-like posts skipped).
3. `extract_key_info.py` calls a local OpenAI-compatible chat API (LM Studio, etc.) to extract a structured JSON object.
4. The payload is enriched (postal code estimation via OSM Nominatim is best-effort).
5. `broadcast_assignments.py` formats and sends the result to a target channel via Telegram Bot API (or writes to a JSONL fallback file).

## Entry points

- `runner.py`
  - `python runner.py start`: starts `read_assignments.main()`
  - `python runner.py test --text "..." [--send]`: extract one message
  - `python runner.py process-file path\\to\\payload.json [--send]`: process a saved payload

## File map

- `read_assignments.py`
  - Long-running Telethon reader + filters.
  - Builds a `payload` dict with channel metadata, raw text, and parsed fields.
  - Calls `broadcast_assignments.send_broadcast(payload)`.
  - Keeps processed message ids in `processed_ids.json` (configurable).
- `extract_key_info.py`
  - Prompt/schema definitions.
  - Selects prompt examples based on source channel and files in `message_examples/`.
  - Calls the local LLM API (`LLM_API_URL`) and returns parsed JSON.
  - Adds best-effort `postal_code_estimated` when `postal_code` is missing.
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

`read_assignments.py` emits a payload with keys like:
- `channel_id`, `channel_username`, `channel_title`, `channel_link`
- `message_id`, `message_link`, `date`
- `raw_text`
- `parsed`: dict produced by `extract_key_info.extract_assignment_with_model(...)`

`broadcast_assignments.py` expects `payload['parsed']` to contain fields like:
`subjects`, `level`, `specific_student_level`, `address`, `postal_code` (or `postal_code_estimated`), `hourly_rate`,
`frequency`, `duration`, `time_slots`/`estimated_time_slots`, `additional_remarks`.

When changing the extraction schema, keep the broadcaster expectations in mind.

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
- OpenStreetMap Nominatim for postal estimation (best-effort; should fail safely).
- Local LLM HTTP API (required for extraction).

Any of these may be blocked/unavailable depending on the runtime environment; error handling should degrade gracefully.

## Coding conventions (keep diffs small)

- Prefer targeted fixes over broad refactors.
- Keep prompt/schema edits consistent with example files in `message_examples/`.
- Do not add new dependencies unless necessary.
- Prefer UTF-8 text files; avoid smart quotes in docs to keep Windows terminals happy.

