# TutorDex Backend (Redis matching)

Minimal FastAPI service that stores tutor preferences in Redis and returns matching tutor chat IDs for an assignment payload.

## Setup

1. Start Redis (this repo’s root `docker compose` includes a local Redis service), and set `REDIS_URL` only if you are not using Docker.
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

- `REDIS_URL`: `redis://redis:6379/0` (docker compose) or `redis://localhost:6379/0` (host)
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
   - `curl -X PUT http://127.0.0.1:8000/tutors/alice -H "content-type: application/json" -d "{\"chat_id\":\"123\",\"subjects\":[\"Maths\"],\"levels\":[\"Primary\"],\"assignment_types\":[\"Private\"]}"`
2. Match a payload:
   - `curl -X POST http://127.0.0.1:8000/match/payload -H "content-type: application/json" -d "{\"payload\":{\"parsed\":{\"learning_mode\":{\"mode\":\"Face-to-Face\",\"raw_text\":\"Face-to-Face\"}},\"meta\":{\"signals\":{\"ok\":true,\"signals\":{\"subjects\":[\"Maths\"],\"levels\":[\"Primary\"]}}}}}"`

## Telegram linking (recommended)

To DM tutors, the backend needs their Telegram `chat_id`. A simple flow is:

1. User generates a link code on the website (Profile page).
2. User messages the DM bot: `/link <code>`
3. Run the poller to claim link codes and store chat ids:
   - `python TutorDexBackend/telegram_link_bot.py`

## Telegram webhook setup (for inline buttons)

Inline buttons in broadcast messages (e.g., "Open original post") require a webhook to be configured with Telegram. Without a webhook, callback queries won't be received when users click these buttons.

### Prerequisites
- Backend must be publicly accessible via HTTPS
- `GROUP_BOT_TOKEN` must be set (the bot that posts broadcasts)
- (Optional) `WEBHOOK_SECRET_TOKEN` for request verification

### Setup steps

1. **Configure environment variables** in `TutorDexBackend/.env`:
   ```bash
   GROUP_BOT_TOKEN=your_bot_token
   WEBHOOK_SECRET_TOKEN=your_random_secret  # Recommended for security
   ```

2. **Set the webhook** (replace with your public domain):
   ```bash
   python TutorDexBackend/telegram_webhook_setup.py set --url https://yourdomain.com/telegram/callback
   ```

3. **Verify webhook is set**:
   ```bash
   python TutorDexBackend/telegram_webhook_setup.py info
   ```

4. **Test the inline button** by:
   - Broadcasting a message with an inline button
   - Clicking the button in Telegram
   - Checking that the callback is received and processed

### Webhook management

```bash
# Get current webhook status
python TutorDexBackend/telegram_webhook_setup.py info

# Delete webhook (reverts to long polling)
python TutorDexBackend/telegram_webhook_setup.py delete

# Set webhook with custom secret
python TutorDexBackend/telegram_webhook_setup.py set \
  --url https://yourdomain.com/telegram/callback \
  --secret my-custom-secret
```

### Important notes

- **HTTPS required**: Telegram only accepts HTTPS webhook URLs (not HTTP)
- **Public accessibility**: Your backend must be accessible from the internet
- **Port requirements**: Use standard ports (443 for HTTPS, or 80/88/8443)
- **Secret token**: Highly recommended to prevent unauthorized webhook calls
- **Endpoint**: The webhook endpoint is `/telegram/callback` (handles callback queries)
- **Update types**: Webhook is configured to receive only `callback_query` updates

### Troubleshooting

1. **Check webhook status**: Use `telegram_webhook_setup.py info` to see errors
2. **Test webhook URL**: Ensure your backend is reachable at the webhook URL
3. **Check logs**: Backend logs will show incoming webhook requests
4. **Verify secret**: If using `WEBHOOK_SECRET_TOKEN`, ensure it matches in both places
5. **Firewall/proxy**: Ensure Telegram IPs can reach your backend
