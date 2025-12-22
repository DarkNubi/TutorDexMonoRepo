# TutorDexAggregator Utilities

This folder contains **manual / occasional** scripts (repair, backfill, reprocessing).

Keep **production entrypoints** in the repo root:
- `runner.py` (starts the main ingestion pipeline via `read_assignments.py`)
- `read_assignments.py` (long-running Telegram reader → extract → persist → broadcast)

Guidelines:
- Prefer reading from `telegram_messages_raw` for reprocessing (lossless input).
- Default to **no broadcast** and **no DMs** in repair scripts to avoid accidental spam.
- Keep scripts runnable via VS Code “Run” (no required CLI args).

