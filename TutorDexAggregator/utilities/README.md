# TutorDexAggregator Utilities

This folder contains **manual / occasional** scripts (repair, backfill, reprocessing).

Keep **production entrypoints** in the repo root:
- Queue-based pipeline:
  - `collector.py tail` (writes `telegram_messages_raw` + enqueues `telegram_extractions`)
  - `workers/extract_worker.py` (claims jobs → LLM extract → persist → broadcast/DM)

Guidelines:
- Prefer reading from `telegram_messages_raw` for reprocessing (lossless input).
- Default to **no broadcast** and **no DMs** in repair scripts to avoid accidental spam.
- Keep scripts runnable via VS Code “Run” (no required CLI args).

## Checks

- `python utilities/check_recent_counts.py --minutes 60`
  - Compares `telegram_messages_raw` vs `assignments` counts for the recent window (default 60 minutes).
  - Requires `SUPABASE_SERVICE_ROLE_KEY` and one of `SUPABASE_URL_HOST` / `SUPABASE_URL_DOCKER` / `SUPABASE_URL` in the environment.
- `python utilities/check_compilations.py --file compilations_sample.txt`
  - Runs `compilation_detection.is_compilation` against sample messages (defaults to `compilations.jsonl` if not provided).
- `python utilities/run_sample_pipeline.py --file utilities/sample_assignment_post.sample.txt --print-json`
  - Local pipeline for a single sample post (no Supabase): normalize → LLM (or mock) → deterministic time → hard-validate → signals.
- `python utilities/tutorcity_fetch.py --limit 50`
- `python utilities/backfill_assignment_latlon.py --limit 500` (fill `postal_lat/postal_lon` for existing rows with `postal_code`)
  - Fetches TutorCity API (no LLM) and persists/broadcasts/DMs directly. Uses `TUTORCITY_API_URL`, `TUTORCITY_LIMIT` envs (source label is always `TutorCity`).
