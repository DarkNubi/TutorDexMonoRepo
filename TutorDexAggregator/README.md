# TutorDexAggregator

Reads Telegram tuition assignment posts, extracts structured display fields using a local LLM HTTP API, adds deterministic hardening (normalization, time parsing, validation, matching signals), persists to Supabase, and optionally broadcasts/DMs.

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
- `AGGREGATOR_CHANNEL_ID`: Target chat id (single channel, starts with `-100...`)
- `AGGREGATOR_CHANNEL_IDS`: Target chat ids (multiple channels, JSON array: `["-1001234567890", "-1009876543210"]`)
- `BOT_API_URL`: Optional override (if not set, built from `GROUP_BOT_TOKEN`)
- `BROADCAST_FALLBACK_FILE`: Where to write JSONL if bot config is missing (default: `TutorDexAggregator/outgoing_broadcasts.jsonl`)
- `ENABLE_BROADCAST_TRACKING`: Enable message tracking for sync/reconciliation (default: `1`)

**Broadcast Channel Sync**

The `sync_broadcast_channel.py` script synchronizes broadcast channels with open assignments:
- Detects and deletes messages for expired/closed assignments
- Detects and posts missing messages for open assignments
- Supports multiple broadcast channels

Usage:
```bash
# Preview changes without making them
python sync_broadcast_channel.py --dry-run

# Execute full sync (delete orphaned + post missing)
python sync_broadcast_channel.py

# Only delete orphaned messages
python sync_broadcast_channel.py --delete-only

# Only post missing assignments
python sync_broadcast_channel.py --post-only

# Sync specific channel
python sync_broadcast_channel.py --chat-id -1001234567890
```

**Broadcast Channel Migration**

When changing to a new broadcast channel, use `migrate_broadcast_channel.py` to copy all open assignments:
```bash
# Preview migration
python migrate_broadcast_channel.py --old-chat -1001111111111 --new-chat -1002222222222 --dry-run

# Migrate (copy to new, keep old)
python migrate_broadcast_channel.py --old-chat -1001111111111 --new-chat -1002222222222

# Migrate and clean up old channel
python migrate_broadcast_channel.py --old-chat -1001111111111 --new-chat -1002222222222 --delete-old
```

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
- `SUPABASE_URL`: Supabase project URL fallback (e.g. `https://<project-ref>.supabase.co`)
- `SUPABASE_URL_DOCKER`: optional override when running inside Docker (e.g. `http://supabase-kong:8000`)
- `SUPABASE_URL_HOST`: optional override when running on the host (Windows/macOS/Linux)
- `SUPABASE_SERVICE_ROLE_KEY`: Service role key for inserts/updates (server-side only)
- `SUPABASE_ASSIGNMENTS_TABLE`: Table name (default `assignments`)
- `SUPABASE_BUMP_MIN_SECONDS`: Minimum seconds between bump increments for duplicates (default `21600` = 6 hours)

**Raw Telegram persistence (optional, recommended for backfill)**
- `SUPABASE_RAW_ENABLED`: `true/false` (defaults to `SUPABASE_ENABLED`)
- `RAW_FALLBACK_FILE`: optional JSONL file to write if raw persistence is disabled/unavailable

Schema files:
- Full normalized schema (recommended): `TutorDexAggregator/supabase sqls/supabase_schema_full.sql`
- Extraction queue RPCs: `TutorDexAggregator/supabase sqls/2025-12-22_extraction_queue_rpc.sql`

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

- Start the raw collector (tail live channels):
  - `python collector.py tail`
- Start the extraction queue worker:
  - `python workers/extract_worker.py`
- Local dry-run on a pasted post (no Supabase writes):
  - `python utilities/run_sample_pipeline.py --file utilities/sample_assignment_post.sample.txt --print-json`
- Raw delete handling:
  - If a Telegram message is deleted and the raw collector has recorded it, the queue worker will mark the corresponding assignment row as `closed` in Supabase (best-effort).

## Raw history collection (recommended)

To build a reprocessable data moat, use the raw collector to persist a lossless message history to Supabase.

1) Apply the normalized schema in Supabase:
   - `TutorDexAggregator/supabase sqls/supabase_schema_full.sql`

2) Enable Supabase (and optionally raw enable flag) in `TutorDexAggregator/.env`:
   - `SUPABASE_ENABLED=true`
   - `SUPABASE_RAW_ENABLED=true` (optional; defaults to SUPABASE_ENABLED)

3) Backfill historical messages:
   - `python collector.py backfill --since 2025-01-01T00:00:00+00:00`
   - Optional cap for smoke runs: `python collector.py backfill --max-messages 200`

4) Tail new messages/edits/deletes:
  - `python collector.py tail`

Progress:
- Check the latest backfill/tail run progress:
  - `python collector.py status --run-type backfill`
  - `python collector.py status --run-type tail`

## Extraction queue + workers

- Requires applying the RPC helper: `TutorDexAggregator/supabase sqls/2025-12-22_extraction_queue_rpc.sql`
- The raw collector can enqueue extraction jobs into `telegram_extractions` (see `collector.py`)
- Workers (`workers/extract_worker.py`) claim jobs, run extraction/enrichment/persistence, and optionally broadcast/DM

### Docker split roles (ingest + worker + monitor)

- Recommended (root-level): `docker compose up --build` from repo root.
  - Default services use the **raw collector + queue** pipeline:
    - `collector-tail` (`collector.py tail`) -> writes raw messages + enqueues extraction jobs
    - `aggregator-worker` (`workers/extract_worker.py`) -> drains the queue (LLM extract + persist + broadcast/DM)
    - `backend` (FastAPI)
  - Supabase (self-host) is expected to be running on the external Docker network `supabase_default` with Kong at `supabase-kong:8000` (HTTP).
    - In `.env`, prefer `SUPABASE_URL_DOCKER=http://supabase-kong:8000` (so Docker runs work).
    - If you also run scripts with Windows Python, set `SUPABASE_URL_HOST=...` to a host-reachable Supabase REST URL/port.
  - Host llama server: keep `LLM_API_URL=http://host.docker.internal:1234`.
  - DM/backend matching uses the internal service `backend:8000` (already set in `.env`).
  - Mounts `./logs` for persistence (optional; container logs are shipped via Loki when using `observability/`).
  - TutorCity API fetcher (no LLM): `tutorcity-fetch` polls `TUTORCITY_API_URL` on an interval and persists/broadcasts/DMs directly (source label is always `TutorCity`).
- Legacy per-folder compose (optional): `docker compose -f docker-compose.roles.yml up --build`
  - Same services as above; use only if you need to run the aggregator stack separately.
- Helpful env knobs:
  - `EXTRACTION_STALE_PROCESSING_SECONDS` / `EXTRACTION_MAX_ATTEMPTS` / backoff vars to tune worker retries
  - `ALERT_*` to target Alertmanager -> Telegram

## Extraction

The queue worker (`workers/extract_worker.py`) calls the LLM once per message (see `extract_key_info.py`), overwrites `time_availability` deterministically, hard-validates the output, persists to Supabase, and optionally broadcasts/DMs.

## Deterministic matching signals (recommended)

In addition to the LLM “display JSON” (stored in `telegram_extractions.canonical_json`), the queue worker can compute deterministic academic matching signals and store them under `telegram_extractions.meta.signals`.

- Docs: `docs/signals.md`
- Flags:
  - `ENABLE_DETERMINISTIC_SIGNALS=0/1` (default `1`)
  - `HARD_VALIDATE_MODE=off|report|enforce` (default `report`)
  - `USE_NORMALIZED_TEXT_FOR_LLM=0/1` (default `0`)
  - `USE_DETERMINISTIC_TIME=0/1` (default `1`; when `1`, overwrites `time_availability` deterministically)

For the current hardened pipeline version (`2026-01-02_det_time_v1`), the recommended `.env` settings are:
- `EXTRACTION_PIPELINE_VERSION=2026-01-02_det_time_v1`
- `USE_DETERMINISTIC_TIME=1`
- `HARD_VALIDATE_MODE=enforce`

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
  - Requires `assignments.freshness_tier` (included in `supabase_schema_full.sql`)
  - Enable writes from aggregator: set `FRESHNESS_TIER_ENABLED=true` in `TutorDexAggregator/.env`
  - Default tier thresholds: green `<24h`, yellow `<36h`, orange `<48h`, red `<72h`
  - Default expiry cutoff: `<168h` (7d) for `status=expired` + Telegram delete (optional)
  - Auto-expire + delete broadcast message after 7d: `python update_freshness_tiers.py --expire-action expired --expire-hours 168 --delete-expired-telegram`
  - Docker sidecar (profile `tiers`): `docker compose --profile tiers up -d freshness-tiers`
    - Interval env: `FRESHNESS_TIERS_INTERVAL_SECONDS` (default 3600)
    - Args env: `FRESHNESS_TIERS_ARGS` (default `--expire-action expired --green-hours 24 --yellow-hours 36 --orange-hours 48 --red-hours 72 --expire-hours 168 --delete-expired-telegram`)



## Monitoring & alerting (recommended)

Use `observability/` (Prometheus + Alertmanager + Grafana + Loki) for metrics, alerts, and logs.

## Production notes (small checklist)

- Set `ADMIN_API_KEY` in `TutorDexBackend/.env` so admin endpoints are not publicly writable.
- Set `CORS_ALLOW_ORIGINS` to your real website domains (avoid `*` for public beta).
- Add basic automated checks (local or CI):
  - `python -m py_compile` for `TutorDexAggregator/*.py` and `TutorDexBackend/*.py`
  - (Optional) a smoke check for backend: `GET /health/full` and confirm `ok=true`
  - Ensure secrets are not tracked in git (`.env`, `secrets/*`, service account JSON).

## Notes

- **Postal geocoding (lat/lon)**: Coordinates are calculated from postal codes using Nominatim geocoding service. The system first tries explicit postal codes, and if not available or geocoding fails, it falls back to estimated postal codes. When coordinates are derived from estimated postal codes, the `postal_coords_estimated` flag is set to `true`, which triggers "(estimated)" labels in the frontend distance displays.
- Keep secrets out of git: `.env` is ignored by `TutorDexAggregator/.gitignore`.
