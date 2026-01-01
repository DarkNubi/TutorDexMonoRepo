# TutorDex Backend (Redis matching)

Minimal FastAPI service that stores tutor preferences in Redis and returns matching tutor chat IDs for an assignment payload.

## Setup

1. Start Redis (local or managed) and set `REDIS_URL`.
2. Install deps:
   - `pip install -r TutorDexBackend/requirements.txt`
3. Run:
   - `uvicorn TutorDexBackend.app:app --host 0.0.0.0 --port 8000`

## Docker (recommended for Windows home server)

1. Install Docker Desktop (Linux containers).
2. Create `TutorDexBackend/.env` (copy from `TutorDexBackend/.env.example`).
3. (Optional, if using Firebase token verification) Download the Firebase Admin service account JSON to:
   - `TutorDexBackend/secrets/firebase-admin-service-account.json`
4. From repo root:
   - `docker compose up -d --build` (uses root `docker-compose.yml` to run backend + aggregator). Supabase self-host must be on the external network `supabase_default`; set `SUPABASE_URL_DOCKER=http://supabase-kong:8000` (or keep using `SUPABASE_URL=http://supabase-kong:8000`).

## Environment variables

- `REDIS_URL`: e.g. `redis://localhost:6379/0`
- `REDIS_PREFIX`: key prefix (default `tutordex`)
- `MATCH_MIN_SCORE`: minimum score to include (default `3`)
- `CORS_ALLOW_ORIGINS`: `*` or comma-separated origins (default `*`)
- `ADMIN_API_KEY`: if set, requires `x-api-key` on bot/admin endpoints

## Logging

Defaults:
- Logs to console and `TutorDexBackend/logs/tutordex_backend.log` (rotating).

Env vars:
- `LOG_LEVEL`, `LOG_TO_CONSOLE`, `LOG_TO_FILE`, `LOG_JSON`, `LOG_DIR`, `LOG_FILE`, `LOG_MAX_BYTES`, `LOG_BACKUP_COUNT`

## API

- `PUT /tutors/{tutor_id}`: upsert preferences
- `GET /tutors/{tutor_id}`
- `DELETE /tutors/{tutor_id}`
- `POST /match/payload`: match using the TutorDexAggregator payload shape
- `POST /telegram/link-code`: create a short-lived link code for a tutor id
- `POST /telegram/claim`: claim a code and set `chat_id`
- `GET /health/full`: base + Redis + Supabase connectivity (recommended for monitoring)

## Quick test

1. Upsert a tutor:
   - `curl -X PUT http://127.0.0.1:8000/tutors/alice -H "content-type: application/json" -d "{\"chat_id\":\"123\",\"subjects\":[\"Maths\"],\"levels\":[\"Primary\"],\"types\":[\"Private\"]}"`
2. Match a payload:
   - `curl -X POST http://127.0.0.1:8000/match/payload -H "content-type: application/json" -d "{\"payload\":{\"parsed\":{\"subjects\":[\"Maths\"],\"level\":\"Primary\",\"type\":\"Private\"}}}"`

## Telegram linking (recommended)

To DM tutors, the backend needs their Telegram `chat_id`. A simple flow is:

1. User generates a link code on the website (Profile page).
2. User messages the DM bot: `/link <code>`
3. Run the poller to claim link codes and store chat ids:
   - `python TutorDexBackend/telegram_link_bot.py`
