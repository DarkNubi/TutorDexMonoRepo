# Execution Plan: Postal Code + Lat/Lon (Tutor + Assignments)

Goal: Add tutor postal code preference in TutorDexWebsite, and store postal code + geocoded lat/lon for both tutors and assignments using Nominatim (best-effort).

## 0) Current Architecture (relevant pieces)

- Website (static + Vite):
  - Profile page saves tutor preferences via TutorDexBackend:
    - `TutorDexWebsite/src/page-profile.js` → `upsertTutor()` → `PUT /me/tutor`
  - Assignments page reads assignments via Supabase REST (anon key):
    - `TutorDexWebsite/src/supabase.js` → `GET /rest/v1/assignments?...`

- Backend (FastAPI):
  - Stores tutor prefs in Redis (`TutorDexBackend/redis_store.py`) and optionally persists to Supabase `user_preferences`:
    - `TutorDexBackend/app.py` (`GET/PUT /me/tutor`)
    - `TutorDexBackend/supabase_store.py` (`upsert_preferences`, `get_preferences`)

- Aggregator (Telethon → LLM → Supabase):
  - Writes assignments to Supabase via `TutorDexAggregator/supabase_persist.py`.
  - Has Nominatim call today, but only for “estimate postal from address” in `TutorDexAggregator/extract_key_info.py`.

## 1) Database changes (Supabase)

Add columns:

### 1.1 `assignments`
- `postal_code` already exists (text).
- Add:
  - `postal_lat` double precision null
  - `postal_lon` double precision null
  - (optional) `postal_geocoded_at` timestamptz null
  - (optional) `postal_geocode_source` text null (e.g. `"nominatim"`)

### 1.2 `user_preferences`
- Add:
  - `postal_code` text null
  - `postal_lat` double precision null
  - `postal_lon` double precision null
  - (optional) `postal_geocoded_at` timestamptz null

Notes:
- Keep RLS on `user_preferences` strict (tutor postal should not be public).
- `assignments` lat/lon can remain public if assignments are public, but decide if you want to expose coordinates via anon key.

Deliverable: a single SQL migration you apply to your Supabase instance.

## 2) Nominatim geocoding approach (postal → lat/lon)

Requirements:
- Best-effort (must not break pipeline if Nominatim is down or rate-limited).
- Cache results (postal codes repeat a lot).
- Use a clear User-Agent, and add throttling/backoff if needed.

Implementation details:
- Input: Singapore postal code `^\d{6}$`.
- Query options:
  - Prefer `search?postalcode=<code>&countrycodes=sg&format=jsonv2&limit=1`
  - Fallback: `search?q=<code>%20Singapore&countrycodes=sg&format=jsonv2&limit=1`
- Output: `lat`, `lon` from first result (float).

Caching options (choose one):
1) In-memory LRU cache (good enough for aggregator long-running process; won’t persist across restarts).
2) Local JSON cache file in the app folder (persists across restarts; add file lock on Windows).
3) Supabase table `postal_geocodes` (best long-term; requires another table + RLS).

## 3) Website changes (TutorDexWebsite)

### 3.1 Add a postal code field to profile UI
- File: `TutorDexWebsite/profile.html`
- Add an input (recommended section: “Where do you teach?” or “Contact Details”):
  - `id="tutor-postal-code"` (6 digits)
  - helper text: “Used to compute distance-based matching (optional).”

### 3.2 Send postal code to backend
- File: `TutorDexWebsite/src/page-profile.js`
  - In `saveProfile()` include `postal_code` in payload.
  - In `loadProfile()` set the input from returned tutor profile.
  - Add simple client-side validation (6 digits) but treat as optional.

No client-side geocoding: keep it server-side so you don’t leak rate-limits or do duplicate calls.

## 4) Backend changes (TutorDexBackend)

### 4.1 Extend API schema
- File: `TutorDexBackend/app.py`
  - Add `postal_code: Optional[str]` to `TutorUpsert`
  - Ensure `/me/tutor` returns `postal_code` (+ optionally `postal_lat`, `postal_lon`)

### 4.2 Geocode on upsert
- Add a small module, e.g. `TutorDexBackend/geocoding.py`:
  - `geocode_sg_postal(postal_code) -> (lat, lon) | None`
  - best-effort, timeout, caching

### 4.3 Persist tutor postal + coords
- Redis store: include `postal_code`, `postal_lat`, `postal_lon` in the tutor record.
- Supabase: update:
  - `TutorDexBackend/supabase_store.py` `upsert_preferences()` payload includes these fields.
  - `get_preferences()` select list includes these fields (so `GET /me/tutor` can load them).
  - `TutorDexBackend/app.py` merges them into `tutor` response.

## 5) Aggregator changes (TutorDexAggregator)

### 5.1 Decide which postal code to geocode
- Use `parsed.postal_code` if present; else use `parsed.postal_code_estimated`.
- If multiple postal codes exist, use the first one (or geocode all later if needed).

### 5.2 Add geocoding and persist into assignments
- Add best-effort geocode call (postal → lat/lon).
- Where to place:
  - Option A (recommended): inside `TutorDexAggregator/supabase_persist.py` when building the `assignments` row.
  - Option B: inside `TutorDexAggregator/extract_key_info.process_parsed_payload()` (enrichment stage) and have `supabase_persist.py` just write fields.
- Add fields to the upserted assignment row: `postal_lat`, `postal_lon`.

## 6) Backfill plan (existing data)

Optional, but recommended if you want coordinates for existing rows:
- One-time script (could live in `infra/` or `tools/`) that:
  - Queries assignments missing `postal_lat/postal_lon` but with `postal_code`
  - Geocodes in batches with throttling
  - Patches rows

If you want to avoid keeping “one-off” scripts in the repo, run it once locally and then delete it after completing the backfill.

## 7) Rollout / verification checklist

1) Apply DB migration (add columns).
2) Deploy backend:
   - Verify `PUT /me/tutor` accepts `postal_code` and returns it.
   - Verify `postal_lat/postal_lon` appear after save (when postal is valid).
3) Deploy website:
   - Verify profile form loads/saves postal code.
4) Deploy aggregator:
   - Verify new assignments rows get `postal_lat/postal_lon` populated when postal is present.
5) Monitoring:
   - Ensure Nominatim failures only log warnings and do not break the pipeline.

## 8) Follow-ups (optional)

- Distance-based matching: compute distance between tutor coords and assignment coords (km), add “radius_km” preference.
- Replace Nominatim with a more reliable SG geocoder (if you hit usage limits).

