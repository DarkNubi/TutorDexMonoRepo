# TutorDex – System Documentation

## 1. Project Overview

TutorDex is a three-part system that ingests Telegram tuition-assignment posts, extracts structured data using a locally hosted LLM, stores results in Supabase, and delivers them to users via:
- A static website that lists “open” assignments from Supabase
- Optional Telegram broadcast and DM flows for distributing assignments to tutors
- A small backend service that stores tutor preferences (Redis) and performs matching for DM delivery

### Components and how they interact

- **TutorDexAggregator** (Python):
  - Reads Telegram channels (Telethon) or backfills from Supabase raw tables
  - Detects/filters compilation posts and other non-target content
  - Calls a local OpenAI-compatible LLM API (typically LM Studio) to extract fields
  - Optionally persists assignments + raw messages + parsing artifacts to Supabase
  - Optionally broadcasts to a Telegram channel and/or DMs matched tutors

- **TutorDexBackend** (Python, FastAPI):
  - Stores tutor preferences (Redis)
  - Exposes matching endpoint used by Aggregator to find tutor chat IDs for DMs
  - Supports tutor self-service endpoints authenticated via Firebase ID tokens (from the Website)
  - Optionally mirrors preferences and analytics events into Supabase

- **TutorDexWebsite** (Vite + static HTML/JS):
  - Lists assignments by calling Supabase PostgREST using an **anon** key
  - Provides “Profile” UI to save tutor preferences via TutorDexBackend
  - Generates Telegram “link codes” (via TutorDexBackend) so tutors can link their Telegram chat_id for DMs
  - Uses Firebase Auth for login

### High-level architecture (conceptual)

- **Ingestion + Extraction**: Telegram → Aggregator → (LLM) → Canonical JSON → Supabase + Telegram output
- **Read path**: Website → Supabase REST (anon key + RLS) → “open” assignments
- **DM path (optional)**: Aggregator → Backend match API → chat_ids → Telegram Bot API DM send
- **Tutor linking**: Website → Backend generates link code → user messages DM bot `/link <code>` → poller claims → Backend stores chat_id

---

## 2. Folder Breakdown

## TutorDexWebsite

### Purpose
A static multi-page site (Firebase Hosting + Vite) for:
- Viewing open tuition assignments
- Managing tutor preferences and enabling DMs (via the backend)
- Authenticating users via Firebase Auth

### Responsibilities
- **Auth**: Firebase Auth (email/password and Google sign-in)
- **Assignments list**: Fetch from Supabase PostgREST using the anon key; relies on Supabase RLS to expose only safe data (typically `status='open'`)
- **Profile**: Read/write tutor profile to TutorDexBackend; generate Telegram link codes

### Key files
- `TutorDexWebsite/README.md`
  - Hosting, deploy, and env var guidance
- `TutorDexWebsite/src/supabase.js`
  - Supabase REST client (`/rest/v1/...`)
  - `listOpenAssignments()` maps DB rows into UI-friendly cards
- `TutorDexWebsite/src/backend.js`
  - Backend REST client (Bearer Firebase token)
  - `getTutor()`, `upsertTutor()`, `createTelegramLinkCode()`, `trackEvent()`
- `TutorDexWebsite/auth.js`
  - Firebase Auth initialization and UI wiring
  - Exposes `getIdToken()` used by `src/backend.js`
- `TutorDexWebsite/src/page-assignments.js`
  - Renders assignment cards and filtering UX
- `TutorDexWebsite/src/page-profile.js`
  - Profile preferences UI
  - Generates `/link <code>` command to connect Telegram chat id

### Communication patterns
- **Supabase**: `VITE_SUPABASE_URL` + `VITE_SUPABASE_ANON_KEY` → GET `/rest/v1/assignments?...`
- **Backend**: `VITE_BACKEND_URL` → authenticated requests using Firebase ID token (`Authorization: Bearer <token>`)

---

## TutorDexAggregator

### Purpose
Ingests Telegram posts, extracts structured information using a local LLM, and distributes/persists results.

There are effectively two “modes” in this repo:
1) **Production reader pipeline**: Telethon live reader + single-stage extraction (`read_assignments.py` + `extract_key_info.py`)
2) **Two-stage parsing pipeline (“revamp”)**: Stage A evidence extraction + Stage B canonicalization (`parsing_pipeline.py` + `run_parsing_pipeline.py`), persisted to `telegram_extractions`

### Responsibilities
- **Telegram ingestion**:
  - Live: `read_assignments.py` (Telethon event loop)
  - Raw history persistence/backfill: `collector.py` + `supabase_raw_persist.py` + `backfill_pipeline.py`
- **Filtering**:
  - Forward filtering, compilation detection, basic skip reasons
  - Compilation heuristic: `compilation_detection.py` and `read_assignments.is_compilation()`
- **LLM extraction**:
  - Legacy: `extract_key_info.py` (monolithic prompt/schema; examples by agency)
  - Revamp: `stage_a.py`, `stage_b.py`, `validators.py`, `parsing_pipeline.py`
  - Shared LLM client: `llm_client.py` (OpenAI-style `/v1/chat/completions`)
- **Output**:
  - Broadcast: `broadcast_assignments.py` (Telegram Bot API HTML message; fallback JSONL)
  - DMs: `dm_assignments.py` (calls backend match API, sends via DM bot)
- **Supabase persistence**:
  - Normalized assignments store: `supabase_persist.py`
  - Raw Telegram store: `supabase_raw_persist.py`
  - Parsing artifacts store: `supabase_extraction_persist.py`
- **Maintenance jobs**:
  - Expire/close: `expire_assignments.py`
  - Freshness tiers: `update_freshness_tiers.py`
  - Subject taxonomy: `taxonomy/*` + `backfill_subject_taxonomy.py`
  - Compilation bumps: `apply_compilation_bumps.py`
  - Monitoring: `monitoring/monitor.py` + heartbeat file in `monitoring/heartbeat.json`
  - Edit/delete monitor: `monitor_message_edits.py`

### Key entry points
- `TutorDexAggregator/runner.py`
  - `python runner.py start`: run `read_assignments.main()` (Telethon reader)
  - `python runner.py test --text "...":` quick extraction test
  - `python runner.py process-file <payload.json>`: process saved payload
- `TutorDexAggregator/read_assignments.py`
  - Long-running Telethon reader and filtering
  - Calls `extract_key_info.extract_assignment_with_model()`
  - Enriches via `extract_key_info.process_parsed_payload()`
  - Outputs via `broadcast_assignments.send_broadcast()`
  - Optional persistence (`supabase_persist.persist_assignment_to_supabase`) and DMs (`dm_assignments.send_dms`)
- `TutorDexAggregator/run_parsing_pipeline.py`
  - Batch processes raw rows into `telegram_extractions` using `parsing_pipeline.process_raw_message()`

### How agency-specific behavior works
- `agency_registry.py` maps `t.me/<channel>` to:
  - `examples_key` (selects examples file under `message_examples/`)
  - `display_name` (used in broadcast formatting)

---

## TutorDexBackend

### Purpose
A minimal FastAPI service that:
- Stores tutor preferences (Redis)
- Matches incoming assignment payloads to tutors
- Supports tutor self-service endpoints authenticated by Firebase ID tokens
- Supports admin/bot endpoints protected by an API key (optional but recommended)
- Optionally writes user/preferences/events into Supabase

### Responsibilities
- **HTTP API**: `TutorDexBackend/app.py` (FastAPI)
- **Tutor profile storage**: `TutorDexBackend/redis_store.py`
- **Matching**: `TutorDexBackend/matching.py`
- **Supabase integration (optional)**: `TutorDexBackend/supabase_store.py`
- **Firebase token verification (optional)**: `TutorDexBackend/firebase_auth.py`
- **Telegram chat-id linking poller**: `TutorDexBackend/telegram_link_bot.py`

### Key endpoints (high level)
- Health:
  - `GET /health`, `GET /health/redis`, `GET /health/supabase`, `GET /health/full`
- Admin/bot endpoints (protected by `ADMIN_API_KEY` if set):
  - `PUT /tutors/{tutor_id}`, `GET /tutors/{tutor_id}`, `DELETE /tutors/{tutor_id}`
  - `POST /match/payload` (used by Aggregator DM flow)
  - `POST /telegram/link-code`, `POST /telegram/claim` (used by link bot)
- Tutor self-service endpoints (Bearer Firebase token via Website):
  - `GET /me`, `GET/PUT /me/tutor`, `POST /me/telegram/link-code`
  - `POST /analytics/event` (optional Supabase analytics)

### Matching behavior
`matching.py` scores tutors using simple set overlap:
- Subject match (+3)
- Level match (+2)
- Assignment type match (+1; “private” vs “tuition centre”)
- Learning mode (+1)
- Tutor type (+1)
Minimum score via `MATCH_MIN_SCORE` (default 3).

---

## 3. Data Flow & Interactions

### A. Live ingestion → broadcast → persistence (Aggregator)
1. `runner.py start` runs `read_assignments.main()` (Telethon).
2. For each incoming Telegram message:
   - Filters (forwarded, compilation-like, validation failures, etc.)
   - Calls local LLM: `extract_key_info.extract_assignment_with_model(raw_text, chat=channel_link)`
   - Enriches payload (postal estimation and normalization): `extract_key_info.process_parsed_payload(payload)`
3. Outputs:
   - Broadcasts to Telegram via `broadcast_assignments.send_broadcast(payload)` or writes fallback JSONL
   - Optional: persists to Supabase `assignments` via `supabase_persist.persist_assignment_to_supabase(payload)`
   - Optional: sends DMs via `dm_assignments.send_dms(payload)`

### B. Website assignments page → Supabase
1. Website loads `assignments.html`.
2. `src/supabase.js:listOpenAssignments()` calls:
   - `GET {VITE_SUPABASE_URL}/rest/v1/assignments?...status=eq.open...`
   - Uses `apikey` + `authorization: Bearer <anon key>`
3. RLS in Supabase is expected to restrict anon reads to “safe” rows/columns (commonly open assignments only).

### C. Tutor preferences + Telegram link code (Website + Backend)
1. Tutor signs in via Firebase Auth.
2. Website calls backend with `Authorization: Bearer <firebase id token>`:
   - `GET /me/tutor` to load preferences
   - `PUT /me/tutor` to save preferences (writes Redis; optionally mirrors to Supabase)
   - `POST /me/telegram/link-code` to generate a short-lived code
3. Tutor messages your DM bot: `/link <code>`.
4. `TutorDexBackend/telegram_link_bot.py` polls Telegram `getUpdates`, calls backend `POST /telegram/claim` to store `chat_id` in Redis.
5. Aggregator can now DM this tutor.

### D. DM delivery (Aggregator + Backend + Telegram Bot API)
1. Aggregator builds a broadcast-formatted message text (`broadcast_assignments.build_message_text()`).
2. Aggregator calls backend matching:
   - `POST {TUTOR_MATCH_URL}` with `{ payload: <aggregator payload> }`
3. Backend returns `chat_ids`.
4. Aggregator sends Telegram Bot API `sendMessage` requests to those chat IDs (rate-limited handling + fallback JSONL on partial failures).

---

## 4. Setup & Running the Project

### Versions / runtime
- **TutorDexAggregator**: Python 3.10+ recommended (uses modern typing; also works with 3.8+ in most cases)
- **TutorDexBackend**: Python 3.10+ recommended (FastAPI + Pydantic v2)
- **TutorDexWebsite**: Node.js (Vite 6), Firebase CLI for hosting deploy/emulator

### TutorDexAggregator setup
1. Install deps:
   - `pip install -r TutorDexAggregator/requirements.txt`
2. Create `TutorDexAggregator/.env` from `TutorDexAggregator/.env.example`
3. Run local LLM server (LM Studio) with OpenAI-compatible endpoint:
   - defaults to `LLM_API_URL=http://localhost:1234`
4. Run:
   - `python TutorDexAggregator/runner.py start`

Optional (Supabase):
- Apply schema/migrations (`TutorDexAggregator/supabase_schema_full.sql` and `TutorDexAggregator/migrations/*`)
- Apply RLS templates (`TutorDexAggregator/supabase_rls_policies.sql`)
- Set:
  - `SUPABASE_ENABLED=true`
  - `SUPABASE_URL_HOST=...` (host Python) and/or `SUPABASE_URL_DOCKER=...` (Docker), or `SUPABASE_URL=...` (fallback)
  - `SUPABASE_SERVICE_ROLE_KEY=...`

### TutorDexBackend setup
1. Start Redis and set `REDIS_URL`
2. Install deps:
   - `pip install -r TutorDexBackend/requirements.txt`
3. Configure `TutorDexBackend/.env` from `TutorDexBackend/.env.example`
4. Run:
   - `uvicorn TutorDexBackend.app:app --host 0.0.0.0 --port 8000`

Optional Firebase enforcement:
- Provide service account JSON and enable `FIREBASE_ADMIN_ENABLED=true`
- Set `AUTH_REQUIRED=true` to require valid Firebase tokens

Recommended security:
- Set `ADMIN_API_KEY` to protect admin/bot endpoints.

### TutorDexWebsite setup
1. In `TutorDexWebsite/.env` (build-time):
   - `VITE_SUPABASE_URL`
   - `VITE_SUPABASE_ANON_KEY`
   - `VITE_BACKEND_URL` (optional)
2. Local preview (auth flows require Hosting emulator):
   - `cd TutorDexWebsite`
   - `npm i`
   - `npm run serve:firebase`
3. Deploy:
   - `firebase deploy --only hosting`

---

## 5. Extending & Maintaining the System

### Adding a new agency/channel (Aggregator)
1. Add an examples file: `TutorDexAggregator/message_examples/<agency>.txt`
2. Add mapping: `TutorDexAggregator/agency_registry.py` (`AGENCIES_BY_CHAT`)
3. If broadcast display name differs, update display name in the same mapping
4. Consider adding/adjusting compilation heuristics if the agency posts compilations frequently

### Evolving extraction schema
- Legacy extractor: `extract_key_info.py` prompt/schema is embedded and uses example files.
- Two-stage pipeline: update:
  - `TutorDexAggregator/prompts/stage_a_prompt.txt`
  - `TutorDexAggregator/prompts/stage_b_prompt.txt`
  - `TutorDexAggregator/schema/canon_enums.txt`
  - `TutorDexAggregator/schema/canon_schema.txt`
  - Validation logic: `TutorDexAggregator/validators.py`

Be mindful of downstream expectations:
- Broadcaster formatting: `broadcast_assignments.py` expects certain canonical fields
- Website mapping: `TutorDexWebsite/src/supabase.js` expects fields like `subject`, `rate_min`, `status`, `last_seen`, etc.

### Common pitfalls
- **RLS misconfiguration**: if the website uses anon key, you must enforce read restrictions via RLS (`status='open'` etc.). Otherwise Supabase linter will flag exposed tables.
- **LM Studio service**: LM Studio can run as a background service (`--run-as-service`) and will keep serving on `localhost:1234` even if you stop Docker.
- **Compilation detection false positives**: URL-heavy formats may be incorrectly flagged; tune heuristics per agency if needed.
- **Partial profile updates**: backend store intentionally avoids overwriting omitted fields; ensure website sends fields you intend to update.

### Best practices for contributors
- Keep extraction changes versioned: use `PARSING_PIPELINE_VERSION` tags for staged rollouts.
- Prefer “lossless raw” ingestion to allow reprocessing after prompt/schema changes.
- Avoid putting secrets in repo: `.env` and secret JSON files should remain uncommitted.
- When self-hosting Supabase publicly: treat `SUPABASE_URL` + anon key as public; rely on RLS and narrow CORS.

---

## 6. Glossary

- **Assignment**: A single tuition job post (private or tuition centre), normalized into canonical fields.
- **Compilation post**: A Telegram message containing many assignments; often skipped or handled separately.
- **Stage A / Stage B**:
  - Stage A: evidence-backed extraction from raw text
  - Stage B: canonicalization + enum/schema validation
- **Supabase PostgREST**: REST interface to Postgres (`/rest/v1/...`) used by both website (anon key) and server-side components (service role).
- **Service role key**: Supabase key with elevated privileges; must never be shipped to the website.
- **Anon key**: Supabase public key used client-side; must be constrained by RLS.
- **Link code**: Short-lived token generated by backend so a user can link Telegram `chat_id` by sending `/link <code>` to a bot.
