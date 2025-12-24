# TutorDexAggregator

Reads Telegram tuition assignment posts, extracts structured fields using a local LLM HTTP API, enriches with postal code (optional), and broadcasts the result via Telegram Bot API (or saves to a local fallback file).

## Setup

1. Install Python deps:
   - `pip install -r requirements.txt`
2. Create `TutorDexAggregator/.env` (see `TutorDexAggregator/.env.example`).
3. Ensure your local LLM server is running (LM Studio, etc.).

## Environment variables

**Required (reader)**
- `TELEGRAM_API_ID`: Telegram API ID
- `TELEGRAM_API_HASH`: Telegram API hash
- `CHANNEL_LIST`: Channels to monitor (JSON array string or comma-separated). Example: `["t.me/TuitionAssignmentsSG","t.me/FTassignments"]`

**Auth/session (choose one)**
- `SESSION_STRING`: Telethon `StringSession` (recommended for headless)
- `TG_SESSION`: Session filename (defaults to `tutordex.session`) if you don't use `SESSION_STRING`

**LLM**
- `LLM_API_URL`: Base URL for your local OpenAI-compatible chat server (default: `http://localhost:1234`)
- `LLM_MODEL_NAME`: Model name override (defaults to `MODEL_NAME` inside `extract_key_info.py`)

**Broadcast (optional)**
- `GROUP_BOT_TOKEN`: Bot token used to send messages
- `AGGREGATOR_CHANNEL_ID`: Target chat id (often starts with `-100...`)
- `BOT_API_URL`: Optional override (if not set, built from `GROUP_BOT_TOKEN`)
- `BROADCAST_FALLBACK_FILE`: Where to write JSONL if bot config is missing (default: `TutorDexAggregator/outgoing_broadcasts.jsonl`)

**Bot 2 (DM) + matching backend (optional)**
- `DM_ENABLED`: `true/false` (default `false`)
- `DM_BOT_TOKEN`: Bot token used to DM tutors
- `DM_BOT_API_URL`: Optional override (if not set, built from `DM_BOT_TOKEN`)
- `TUTOR_MATCH_URL`: Match API endpoint (default `http://127.0.0.1:8000/match/payload`)
- `DM_MAX_RECIPIENTS`: Cap DMs per assignment (default `50`)
- `DM_FALLBACK_FILE`: Where to write JSONL if some DMs fail (default `TutorDexAggregator/outgoing_dm.jsonl`)

Matching service: run `uvicorn TutorDexBackend.app:app --host 0.0.0.0 --port 8000` (see `TutorDexBackend/README.md`).

Helper (discover chat ids after users message the DM bot):
- `python telegram_chat_id_helper.py --commit-offset`

**Supabase persistence (optional)**
- `SUPABASE_ENABLED`: `true/false` (default `false`)
- `SUPABASE_URL`: Supabase project URL (e.g. `https://<project-ref>.supabase.co`)
- `SUPABASE_SERVICE_ROLE_KEY`: Service role key for inserts/updates (server-side only)
- `SUPABASE_ASSIGNMENTS_TABLE`: Table name (default `assignments`)
- `SUPABASE_BUMP_MIN_SECONDS`: Minimum seconds between bump increments for duplicates (default `21600` = 6 hours)

**Raw Telegram persistence (optional, recommended for backfill)**
- Requires DB migration: `TutorDexAggregator/migrations/2025-12-18_add_telegram_raw_tables.sql`
- `SUPABASE_RAW_ENABLED`: `true/false` (defaults to `SUPABASE_ENABLED`)
- `RAW_FALLBACK_FILE`: optional JSONL file to write if raw persistence is disabled/unavailable

Schema files:
- Minimal single-table schema: `TutorDexAggregator/supabase_schema.sql`
- Full normalized schema: `TutorDexAggregator/supabase_schema_full.sql`
- RLS policy templates: `TutorDexAggregator/supabase_rls_policies.sql`
 - Subject taxonomy migration (adds derived arrays): `TutorDexAggregator/migrations/2025-12-17_add_subject_taxonomy.sql`
 - Raw Telegram tables: `TutorDexAggregator/migrations/2025-12-18_add_telegram_raw_tables.sql`

Supabase self-host migration runbook:
- `infra/supabase_selfhost/README.md`

**Skipped/Moderation forwarding (optional)**
- `SKIPPED_MESSAGES_CHAT_ID`: Chat id to forward skipped posts to
- `SKIPPED_MESSAGES_THREAD_ID`: Thread id (topic) inside that chat

## Logging

Logs are written to `TutorDexAggregator/logs/tutordex_aggregator.log` (rotating) and also printed to console by default.

Environment variables:
- `LOG_LEVEL`: `DEBUG`/`INFO`/`WARNING`/`ERROR` (default `INFO`)
- `LOG_DIR`: log directory (default `TutorDexAggregator/logs`)
- `LOG_FILE`: log filename (default `tutordex_aggregator.log`)
- `LOG_MAX_BYTES`: rotate after this size (default `5000000`)
- `LOG_BACKUP_COUNT`: number of rotated files (default `5`)
- `LOG_TO_CONSOLE`: `true/false` (default `true`)
- `LOG_TO_FILE`: `true/false` (default `true`)

## Message examples

Prompt examples live in `TutorDexAggregator/message_examples/`:
- `general.txt` is the default fallback
- Agency-specific files are selected by chat mapping in `TutorDexAggregator/extract_key_info.py`

## Run

From `TutorDexAggregator/`:

- Start the Telegram reader:
  - `python runner.py start`
- Quick extract test (no send):
- `python runner.py test --text "..." `
- Quick extract test (send via broadcaster):
  - `python runner.py test --text "..." --send`
- Process a saved payload JSON:
- `python runner.py process-file path\\to\\payload.json`
  - `python runner.py process-file path\\to\\payload.json --send`
- Raw delete handling:
  - If a Telegram message is deleted and the raw collector has recorded it, the queue worker will mark the corresponding assignment row as `closed` in Supabase (best-effort).

## Raw history collection (recommended)

The production pipeline (`read_assignments.py`) intentionally filters/skips some posts (forwards, compilation posts).
To build a reprocessable data moat, use the raw collector to persist a lossless message history to Supabase.

1) Apply the raw tables migration in Supabase:
   - `TutorDexAggregator/migrations/2025-12-18_add_telegram_raw_tables.sql`

2) Enable Supabase (and optionally raw enable flag) in `TutorDexAggregator/.env`:
   - `SUPABASE_ENABLED=true`
   - `SUPABASE_RAW_ENABLED=true` (optional; defaults to SUPABASE_ENABLED)

3) Backfill historical messages:
   - `python collector.py backfill --since 2025-01-01T00:00:00+00:00`
   - Optional cap for smoke runs: `python collector.py backfill --max-messages 200`

4) Tail new messages/edits/deletes:
  - `python collector.py tail`

Heartbeat:
- Default file: `TutorDexAggregator/monitoring/heartbeat_raw_collector.json` (override with `--heartbeat-file`)

Progress:
- Check the latest backfill/tail run progress:
  - `python collector.py status --run-type backfill`
  - `python collector.py status --run-type tail`

## Extraction queue + workers

- Requires applying the RPC helper: `TutorDexAggregator/supabase sqls/2025-12-22_extraction_queue_rpc.sql`
- The raw collector can enqueue extraction jobs into `telegram_extractions` (see `collector.py`)
- Workers (`workers/extract_worker.py`) claim jobs, run extraction/enrichment/persistence, and optionally broadcast/DM
- Worker heartbeat writes to `TutorDexAggregator/monitoring/heartbeat_queue_worker.json` (config via `EXTRACTION_QUEUE_HEARTBEAT_FILE`)
- Monitor alerts on stale worker heartbeat or high pending age; configure via `.env` (`ALERT_*`, `EXTRACTION_QUEUE_HEARTBEAT_*`)

### Docker split roles (ingest + worker + monitor)

- Recommended (root-level): `docker compose up --build` from repo root.
  - Services: `aggregator-ingest` (`runner.py start`), `aggregator-worker` (`workers/extract_worker.py`), `aggregator-monitor` (`monitoring/monitor.py`), `backend` (FastAPI).
  - Supabase (self-host) is expected to be running on the external Docker network `supabase_default` with Kong at `supabase-kong:8000` (HTTP). In `.env`, set `SUPABASE_URL=http://supabase-kong:8000`.
  - Host llama server: keep `LLM_API_URL=http://host.docker.internal:1234`.
  - DM/backend matching uses the internal service `backend:8000` (already set in `.env`).
  - Mounts `./logs` and `./monitoring` for persistence.
- Legacy per-folder compose (optional): `docker compose -f docker-compose.roles.yml up --build`
  - Same services as above; use only if you need to run the aggregator stack separately.
- Helpful env knobs:
  - `EXTRACTION_QUEUE_HEARTBEAT_FILE` to move the queue heartbeat path
  - `EXTRACTION_STALE_PROCESSING_SECONDS` / `EXTRACTION_MAX_ATTEMPTS` / backoff vars to tune worker retries
  - `ALERT_*` to target the alert bot/chat/thread

## Extraction

The live aggregator uses a single LLM call per message (see `extract_key_info.py`) and then broadcasts + optionally persists the result.

## Telegram edit/delete monitoring (optional)

Some agencies edit or delete assignment posts after publishing. You can run a lightweight monitor to collect:
- message first seen time (message date + first observed by the monitor)
- every edit time + content changes (hash/length, optional full text)
- deleted message IDs + delete time

From `TutorDexAggregator/`:
- `python monitor_message_edits.py`

By default it writes to `TutorDexAggregator/monitoring/telegram_message_edits.sqlite`.

## Scheduled jobs

- Close stale assignments (status=open, last_seen older than N days):
  - `python expire_assignments.py --days 7`
  - Dry run: `python expire_assignments.py --days 7 --dry-run`

- Update freshness tiers (recommended once per hour)
  - Requires DB migration: `TutorDexAggregator/migrations/2025-12-17_add_freshness_tier.sql`
  - Enable writes from aggregator: set `FRESHNESS_TIER_ENABLED=true` in `TutorDexAggregator/.env`
  - Tier update (7d -> red, no close): `python update_freshness_tiers.py --expire-action none --red-hours 168`
  - Auto-close after 14d: `python update_freshness_tiers.py --expire-action closed --red-hours 336`
  - Docker sidecar (profile `tiers`): `docker compose --profile tiers up -d freshness-tiers`
    - Interval env: `FRESHNESS_TIERS_INTERVAL_SECONDS` (default 3600)
    - Args env: `FRESHNESS_TIERS_ARGS` (default `--expire-action closed --red-hours 336`)



## Monitoring & alerting (recommended)

The aggregator writes a lightweight heartbeat file (default `TutorDexAggregator/monitoring/heartbeat.json`) and logs all pipeline events to `TutorDexAggregator/logs/tutordex_aggregator.log`.

You can run a simple Telegram alerting loop that:
- Alerts when the aggregator heartbeat/log stops updating (process stalled/down)
- Alerts on error spikes (Telegram rate limits, LLM failures, Supabase failures, DM/broadcast failures)
- Sends a daily “pipeline health summary” to an admin chat/thread

1) Configure (in `TutorDexAggregator/.env`):
- `ALERT_BOT_TOKEN`, `ALERT_CHAT_ID`, optional `ALERT_THREAD_ID`
- `MONITOR_BACKEND_HEALTH_URL` (recommended: backend `/health/full`)
- Recommended defaults (override in `.env`):
  - `ALERT_HEARTBEAT_STALE_SECONDS=900` (15 minutes)
  - `ALERT_LOG_STALE_SECONDS=900`
  - `ALERT_ERROR_BURST_LIMIT=6`
  - `HEARTBEAT_FILE=monitoring/heartbeat.json`
  - `EXTRACTION_QUEUE_HEARTBEAT_FILE=monitoring/heartbeat_queue_worker.json`

2) Run the monitor (from `TutorDexAggregator/`):
- `python monitoring/monitor.py`

Windows helper:
- `TutorDexAggregator/setup_service/start_monitor_loop.bat`

## Production notes (small checklist)

- Set `ADMIN_API_KEY` in `TutorDexBackend/.env` so admin endpoints are not publicly writable.
- Set `CORS_ALLOW_ORIGINS` to your real website domains (avoid `*` for public beta).
- Add basic automated checks (local or CI):
  - `python -m py_compile` for `TutorDexAggregator/*.py` and `TutorDexBackend/*.py`
  - (Optional) a smoke check for backend: `GET /health/full` and confirm `ok=true`
  - Ensure secrets are not tracked in git (`.env`, `secrets/*`, service account JSON).

## Notes

- `extract_key_info.py` can optionally call OpenStreetMap Nominatim to estimate postal codes; if network access is blocked/unavailable, it will silently return `None`.
- Keep secrets out of git: `.env` is ignored by `TutorDexAggregator/.gitignore`.
