# TutorDexAggregator Utilities

This folder contains **manual / occasional** scripts (repair, backfill, reprocessing).

Keep **production entrypoints** in the repo root:
- `runner.py` (starts the main ingestion pipeline via `read_assignments.py`)
- `read_assignments.py` (long-running Telegram reader → extract → persist → broadcast)
 - Queue-based pipeline (recommended for LLM outage resilience):
   - `collector.py tail` (writes `telegram_messages_raw` + enqueues `telegram_extractions`)
   - `workers/extract_worker.py` (claims jobs → LLM extract → persist → broadcast/DM)

Guidelines:
- Prefer reading from `telegram_messages_raw` for reprocessing (lossless input).
- Default to **no broadcast** and **no DMs** in repair scripts to avoid accidental spam.
- Keep scripts runnable via VS Code “Run” (no required CLI args).

## Checks

- `python utilities/check_recent_counts.py --minutes 60`
  - Compares `telegram_messages_raw` vs `assignments` counts for the recent window (default 60 minutes).
  - Requires `SUPABASE_URL` + `SUPABASE_SERVICE_ROLE_KEY` in the environment.
- `python utilities/check_compilations.py --file compilations_sample.txt`
  - Runs `compilation_detection.is_compilation` against sample messages (defaults to `compilations.jsonl` if not provided).
- `python utilities/smoke_extract.py --text "..."` (or `--file sample.txt`)
  - Calls LLM extract → enrichment → schema validation (no broadcast, no Supabase).
