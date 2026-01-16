# TutorDex Monorepo — Internal System Documentation (Authoritative)

> Audience: senior engineers / founder returning after time away.
>
> Goal: document how the system **actually** works today.
>
> Scope: this monorepo is one system composed of three main codebases:
> - `TutorDexAggregator` (ingest + extract + persist + broadcast/DM)
> - `TutorDexBackend` (API, tutor profile store, matching, analytics + click tracking)
> - `TutorDexWebsite` (static Firebase-hosted website; assignments page is public, profile is authenticated; uses backend)

---

## 1. Executive Summary (1–2 pages)

### What TutorDex is
TutorDex is an automated pipeline that turns **unstructured tuition assignment posts** (primarily from Telegram agency channels, plus at least one external “TutorCity API” source) into a **structured, searchable assignment feed**. It also supports a second distribution mode: pushing assignments back out via Telegram (broadcast channel posts) and optionally sending assignment DMs to matched tutors.

There are three user-facing “surfaces”:
1. A **Telegram broadcast channel** (optional): formatted posts with a link to the original agency message.
2. A **Tutor website** (static Firebase-hosted pages): tutors can browse assignments as a guest; sign-in unlocks saved preferences, Telegram DM linking, and “Nearest” sorting.
3. A **Telegram DM bot** (optional): tutors link their chat to receive DMs; the system pushes matched assignments.

### What problem it solves
Agencies post assignments as messy, inconsistent free text. TutorDex:
- Collects raw messages reliably (including edits/deletes).
- Runs LLM-assisted extraction to a canonical JSON schema.
- Applies deterministic normalization/validation and “signals” (matching metadata).
- Persists a denormalized `assignments` table for the website/backend.
- Optionally rebroadcasts + tracks engagement.

### Who the users are
Documented from behavior in code and pages:
- **Tutors:** sign in on the website; set levels/subjects/locations; optionally link Telegram for DMs.
- **Parents/Students:** not directly represented as users in code; they appear implicitly as “assignment demand”.
- **Admins/Operators:** run Docker stack, configure env/secrets, monitor metrics/logs, handle failures.
- **Agencies:** not authenticated users; they are upstream content publishers (Telegram channels / TutorCity API).

### High-level architecture diagram (described in text)
Think of the system as a pipeline with two optional “sinks”:

1) **Ingestion + Queue (Aggregator)**
- Telegram channels → `TutorDexAggregator/collector.py` → Supabase tables:
  - `public.telegram_messages_raw` (lossless raw history)
  - `public.telegram_extractions` (work queue rows per raw message + pipeline version)

2) **Extraction + Persistence (Aggregator worker)**
- `TutorDexAggregator/workers/extract_worker.py` claims jobs via RPC `public.claim_telegram_extractions` → loads raw → LLM extraction → deterministic hardening → persists to:
  - `public.assignments` (query-friendly projection)
  - and updates `public.telegram_extractions` metadata/status

3) **Consumption (Backend + Website)**
- `TutorDexWebsite` (Firebase Auth) → calls `TutorDexBackend` HTTP endpoints.
- Backend reads from Supabase (`assignments`, `user_preferences`, `analytics_events`, etc.) and from Redis (`tutor profiles`, `link codes`, click cooldown).

4) **Optional: Telegram distribution + click tracking**
- Aggregator can broadcast formatted messages via Telegram Bot API (`TutorDexAggregator/broadcast_assignments.py`).
- Backend tracks website click beacons (`POST /track`) and can edit broadcast messages to reflect click counts (requires bot token + Supabase mapping rows).
- Optional DMs: Aggregator calls backend matching endpoint to determine recipient chat_ids and sends DMs (`TutorDexAggregator/dm_assignments.py`).

5) **Observability (optional, but wired in compose)**
- Prometheus + Grafana + Alertmanager run via root `docker-compose.yml` (see `observability/`).
- Note: Loki (logs), Tempo (traces) and the OTEL Collector have been removed from the default local stack; add them back if you need centralized logs or tracing.

**Recent Code Changes (2026-01)**

**2026-01-10:**
- **Deterministic academic requests extraction**: New extractor (`TutorDexAggregator/extractors/academic_requests.py`) parses subjects, levels, specific levels, streams, and per-request academic breakdowns using regex tokenization. Integrates with taxonomy v2 for canonical subject codes.
- **Deterministic tutor types and rate breakdown**: New extractor (`TutorDexAggregator/extractors/tutor_types.py`) identifies tutor types (PT/FT/MOE/Ex-MOE) and associated rate ranges using pattern matching and agency-specific aliasing. Outputs deterministic signals that are preferred over LLM outputs at persist time.
- **Compilation ingestion hardening**: Suspected multi-assignment posts now use an LLM-based identifier extractor with deterministic verbatim verification; confirmed compilations are split and ingested per assignment, and the pipeline fails closed against hallucinated identifiers.
- **Tutor types and rate breakdown in list RPC**: Migration `2026-01-10_add_tutor_types_rate_breakdown_to_list_v2.sql` adds these fields to `list_open_assignments_v2` output for frontend display and filtering.

**2026-01-09:**
- **Assignment rating system**: Complete adaptive threshold system for personalized assignment distribution. Includes rating calculation (`TutorDexBackend/assignment_rating.py`), adaptive threshold RPC, DM integration with historical rate tracking, and `tutor_assignment_ratings` table. See docs/assignment_rating_system.md.
- **Duplicate detection**: Cross-agency duplicate detection system with similarity scoring, primary assignment selection, and UI/broadcaster integration. Configurable thresholds via `duplicate_detection_config` table. Components: `DuplicateBadge.jsx`, `DuplicateModal.jsx`, backend `/assignments/{id}/duplicates` endpoint.

**2026-01-07:**
- **Postal code estimation fallback**: Support distance calculations from estimated postal codes when explicit postal code is unavailable. New `postal_coords_estimated` flag and frontend "(estimated)" indicator.
- **List RPC v2 updates**: Returns `postal_coords_estimated`, `tutor_types`, `rate_breakdown`, and other new fields.

**2026-01-04:**
- **Published timestamp tracking**: New `published_at` column captures source publish time (distinct from `last_seen` poll time). Used for "sort=newest" to prevent polled APIs from floating indefinitely.
- **Source last seen tracking**: New `source_last_seen` column tracks "last observed by pipeline" distinct from creation time, drives bump/freshness indicators.
- **TutorCity composite ID cleanup**: Migration to clean up old composite external IDs from TutorCity (transition to using assignment_code as stable identifier).

**2026-01-03:**
- **Subjects taxonomy v2**: Complete migration to stable subject codes with general categories, canonical subjects, and level-specific variants. Database support tables, filter integration, and frontend dropdown generation.

**2026-01-05 and earlier:**
- **Backfill retries and resilience**: The recovery/catchup flow (`TutorDexAggregator/recovery/catchup.py`) now wraps per-channel backfill calls with a configurable retry loop and exponential backoff. Environment variables `RECOVERY_BACKFILL_MAX_ATTEMPTS` and `RECOVERY_BACKFILL_BASE_BACKOFF_SECONDS` control attempts and base wait. This makes automated backfills more tolerant of transient Telethon/network errors.

- **Raw message idempotency confirmed**: The raw ingest path (`TutorDexAggregator/supabase_raw_persist.py`) uses PostgREST `on_conflict=channel_link,message_id` with `resolution=merge-duplicates` and the DB enforces a unique index on `(channel_link, message_id)`. Backfill overlaps are therefore safe (rows are upserted, not duplicated).

- **Preserve latest message pointer**: The assignment persistence merge logic (`TutorDexAggregator/supabase_persist.py`) was changed to avoid older original posts from clobbering the stored `message_id` / `message_link`. These pointer fields are now only updated when the incoming record's source timestamp (`source_last_seen` or `published_at`) is at least as new as the stored timestamps, or when the existing pointer is absent. The rest of the conservative merge semantics (parse-quality gating, signal unioning, bump handling) remain unchanged.

- **Broadcast click tracking using callback buttons**: The broadcaster (`TutorDexAggregator/broadcast_assignments.py`) now prefers inline callback buttons with `callback_data` of the form `open:<external_id>` so Telegram clients open the original URL natively while the bot receives a callback to record the click. When the `callback_data` would be too long or an external id is unavailable, the code falls back to a direct URL button. The backend already implements `/telegram/callback` and resolves the original URL and increments click counters; this change enables native UX + reliable click tracking without redirects. **Important**: Inline buttons with `callback_data` require a webhook to be configured with Telegram (see `docs/TELEGRAM_WEBHOOK_SETUP.md` and `TutorDexBackend/telegram_webhook_setup.py`). Without a webhook, callback queries won't be received when users click these buttons.

- **Frontend compact card tweaks**: The website compact assignment card (`TutorDexWebsite/src/page-assignments.js`) was adjusted to reduce clutter: level/subject/posted/bumped meta items were removed from the compact meta row and replaced with more actionable compact metadata — postal/postal-estimated, distance (when available), and time-availability notes. This improves at-a-glance usefulness in compact mode.

- **Click tracking endpoints and cooldown**: The backend `/track` endpoint and the Telegram callback handler both use a shared cooldown helper (`_should_increment_click`) backed by Redis (with an in-memory fallback) to prevent high-frequency duplicate increments per IP. This logic is used when processing both website beacon clicks and Telegram callback clicks.

- **Small resilience and observability improvements**: Minor retries, structured logs, and atomic state writes were added around recovery state updates and backfill runs to make resumable catchup more robust and observable.

Note on docs upkeep: `docs/SYSTEM_INTERNAL.md` is intended to be the authoritative, up-to-date description of system behaviour. Update this file whenever you change extraction, persistence, or distribution logic (including prompt/schema changes, deterministic signal rollups, or DB persistence heuristics).

---

## 2. Monorepo Overview

### Top-level folders/files (reality)
- `TutorDexAggregator/`: ingestion, extraction, persistence, Telegram broadcast/DM, and most "business logic".
- `TutorDexBackend/`: FastAPI service providing website APIs, matching, click tracking, assignment rating, and Supabase-facing user/event persistence. **Refactored 2026-01-12**: now uses modular service architecture with `utils/` and `services/` subdirectories (see Backend Architecture section below).
- `TutorDexWebsite/`: static multi-page site built with Vite; Firebase Hosting + Firebase Auth.
- `observability/`: Full observability stack configuration and runbooks.
- `docs/`: internal docs; some are used by pipeline logic (e.g., time availability doc references).
- `tests/`: Python tests, primarily around normalization/validation/signals.
- `shared/`: Shared Python modules for contracts (assignment_row schema) and taxonomy (subjects v2, tutor types).
- Root `docker-compose.yml`: runs the entire system and observability stack.

### Docker compose services (complete list)
**Core application services:**
- `collector-tail`: Telegram message collector with automated catchup (`python collector.py live`)
- `aggregator-worker`: Extraction queue worker (`python workers/extract_worker.py`)
- `backend`: FastAPI backend API server (`uvicorn app:app`)
- `telegram-link-bot`: Telegram link bot poller (`python telegram_link_bot.py`)
- `redis`: Redis 7 (Alpine) with persistence (60s snapshots + AOF)
- `tutorcity-fetch`: TutorCity API poller (scheduled loop)
- `freshness-tiers`: Assignment freshness tier updater (scheduled loop)

**Observability services:**
- `prometheus`: Prometheus v2.50.1 (metrics collection + alerting evaluation)
- `alertmanager`: Alertmanager v0.27.0 (alert routing + deduplication)
- `alertmanager-telegram`: Custom Telegram alert webhook receiver
- `grafana`: Grafana v12.3.1 (dashboards + visualization)
- `cadvisor`: cAdvisor v0.51.0 (container resource metrics)
- `node-exporter`: Node Exporter v1.8.1 (host system metrics)
- `blackbox-exporter`: Blackbox Exporter v0.25.0 (endpoint probing + uptime)

**Note on observability:**
- Loki (logs), Tempo (traces), Promtail, and OTEL Collector are NOT included in default local stack
- OTEL instrumentation is wired in code but only active when `OTEL_ENABLED=1`
- To add centralized logs/traces, see `observability/README.md` and restore from git history
- Default setup focuses on metrics + dashboards + alerts (lighter resource footprint)

### How the three projects relate
- Aggregator produces the data. The Backend and Website do not ingest from Telegram.
- Backend is an API layer + storage glue:
  - Redis: “live” tutor preferences and Telegram link codes.
  - Supabase: durable storage for assignments, user preferences, analytics events, click tracking.
- Website is a thin authenticated frontend:
  - Firebase Auth manages identity.
  - The website calls Backend endpoints; it does not call Supabase directly.

### Entry points you actually run
- Aggregator collector: `TutorDexAggregator/collector.py tail` (run in Docker as service `collector-tail`).
- Aggregator extraction worker: `TutorDexAggregator/workers/extract_worker.py` (service `aggregator-worker`).
- Backend API: `uvicorn TutorDexBackend.app:app` (service `backend`).
- Telegram link bot poller: `TutorDexBackend/telegram_link_bot.py` (service `telegram-link-bot`).
- Website: deployed to Firebase Hosting; locally run via Firebase Hosting emulator (see `TutorDexWebsite/README.md`).

---

## 3. End-to-End Data Flow (CRITICAL)

This traces one “tuition assignment” from Telegram post → website listing → user click tracking.

### 3.1 Source ingestion (Telegram / agencies / raw text)

#### Telegram collection
- Code: `TutorDexAggregator/collector.py`.
- Main behavior:
  - For each configured channel (`CHANNEL_LIST`), it writes raw rows to Supabase via `SupabaseRawStore` and `build_raw_row` (`TutorDexAggregator/supabase_raw_persist.py`).
  - It then enqueues extraction jobs by calling `_enqueue_extraction_jobs` which POSTs to Supabase RPC endpoint `rpc/enqueue_telegram_extractions`.

Production mode (what `docker-compose.yml` runs):
- `python collector.py live`
  - Runs real-time tailing (`tail`) **and** a bounded “catchup” backfill after restart to heal gaps.
  - Catchup throttles itself based on the extraction queue backlog.
  - State is persisted to `TutorDexAggregator/state/recovery_catchup_state.json`.

See also: `docs/recovery_catchup.md`.

Key functions to know:
- `collector._parse_channels_from_env()` → parses `CHANNEL_LIST`.
- `collector._pipeline_version()` → uses `EXTRACTION_PIPELINE_VERSION` (default `2026-01-02_det_time_v1`).
- `collector._enqueue_extraction_jobs(...)` → requires RPC from `TutorDexAggregator/supabase sqls/2025-12-22_extraction_queue_rpc.sql`.

Supabase queue tables involved:
- `public.telegram_messages_raw`: lossless raw messages (including edits/deletes).
- `public.telegram_extractions`: work items keyed by `(raw_id, pipeline_version)`.

Edits/deletes:
- `collector.py live` handles `MessageEdited` by upserting the raw row and force-enqueueing extraction for that message id.
- For “collector downtime” recovery (raw has edits but no reprocess), use `TutorDexAggregator/utilities/enqueue_edited_raws.py` to enqueue edited raws by `telegram_messages_raw.edit_date` without Telegram calls.

Status tracking (explicit, opt-in):
- Some agencies explicitly update posts to indicate `OPEN`/`CLOSED` (either by editing the original message or posting a “closed” notice with the same assignment code).
- TutorDex applies deterministic status detection only for an allowlist of reliable channels:
  - `t.me/elitetutorsg`
  - `t.me/TutorAnywhr`
  - `t.me/eduaidtuition`
- Implementation: `TutorDexAggregator/extractors/status_detector.py` (writes `assignments.status` when an explicit marker is present, and stores debug info in `assignments.meta.status_detection`).

#### Non-Telegram source: TutorCity API (polled)
- Root compose runs `tutorcity-fetch` which executes `TutorDexAggregator/utilities/tutorcity_fetch.py` on an interval (see root `docker-compose.yml`).
- This path bypasses Telegram raw tables.
- It still uses the same persistence + broadcasting/DM paths.
- Important timestamp semantics:
  - `assignments.last_seen` is “last observed by our pipeline” and may update on every poll.
  - `assignments.published_at` is “source publish time / first-seen” and is used for “sort=newest” so polled API rows don’t float to the top indefinitely.
 - TutorCity update semantics:
   - TutorCity may return multiple rows with the same `assignment_code` across polls (and sometimes within the same response). These represent updates.
   - TutorDex treats `assignment_code` as the stable identity for TutorCity (`external_id == assignment_code`), and overwrites the stored row when content changes.
   - To avoid poll noise, `source_last_seen` is only advanced when the upstream payload fingerprint changes (not on every poll).
   - If you have old composite TutorCity ids (`external_id` like `D2388:...`), use `TutorDexAggregator/supabase sqls/2026-01-04_05_tutorcity_cleanup_composite_external_ids.sql` after deploying the new code.

### 3.2 Extraction (LLM / parsing / validation)

#### Queue claim and raw load
- Code: `TutorDexAggregator/workers/extract_worker.py`.
- The worker claims jobs by calling `_rpc(..., fn="claim_telegram_extractions", ...)` which hits `POST {SUPABASE_URL}/rest/v1/rpc/claim_telegram_extractions`.
- The RPC uses `FOR UPDATE SKIP LOCKED` (defined in `TutorDexAggregator/supabase sqls/2025-12-22_extraction_queue_rpc.sql`) to avoid double-processing.
- Worker configuration via env vars:
  - `EXTRACTION_WORKER_BATCH`: claim batch size (default: 10)
  - `EXTRACTION_MAX_ATTEMPTS`: max retry attempts per job (default: 3)
  - `EXTRACTION_BACKOFF_BASE_S`, `EXTRACTION_BACKOFF_MAX_S`: exponential backoff configuration
  - `EXTRACTION_STALE_PROCESSING_SECONDS`: timeout for stale "processing" jobs (default: 900s / 15min)
  - `EXTRACTION_WORKER_ONESHOT`: if true, worker processes one batch and exits (useful for reprocessing/validation)

#### Filtering (skips)
Before invoking the LLM, the worker filters raw content in this order:
1. **Deleted messages**: the worker can mark corresponding assignments closed via `supabase_persist.mark_assignment_closed` (see imports in `extract_worker.py`).
2. **Forwarded messages**: messages that are forwards from other channels are skipped.
3. **Empty messages**: messages with no text content are skipped.
4. **Compilation posts** (updated 2026-01-12): suspected multi-assignment posts are detected via `compilation_detection.is_compilation` and then handled via `TutorDexAggregator/compilation_message_handler.py`:
   - The worker calls the LLM using ONLY `TutorDexAggregator/prompts/assignment_code_extractor_live.txt` to extract verbatim assignment identifiers from the raw message.
   - LLM output is treated as untrusted: every returned identifier is deterministically verified as a verbatim substring of the raw message (hallucinations are dropped).
   - If fewer than 2 identifiers survive verification, the message is **not** treated as a compilation and is downgraded to the normal non-compilation path (single-assignment extraction or non-assignment skip).
   - If 2+ identifiers survive verification, the message is confirmed as a compilation: it is split into per-assignment segments and each segment runs the normal extraction+persist pipeline.
   - The persisted `assignment_code` is forced to the verified identifier (with deterministic post-verification normalization) so hallucinated IDs cannot enter downstream processing.
5. **Non-assignment messages** (added 2026-01-10): messages that are clearly not assignments are filtered via `extractors/non_assignment_detector.is_non_assignment`:
   - **Status-only messages**: Simple status updates like "ASSIGNMENT CLOSED", "TAKEN", "FILLED", "EXPIRED"
   - **Redirect messages**: References like "Assignment X has been reposted below" or "See above"
   - **Administrative/promotional messages**: Announcements and job list compilations like "Calling All Tutors! There are many job opportunities..."
   - These are detected using conservative heuristics (regex patterns + content markers) to avoid false positives.
   - Detection happens AFTER compilation check but BEFORE LLM call to save costs on non-assignment content.
   - Detected messages are logged with detailed metadata and optionally reported to the triage channel.
   - Triage routing (topics):
     - `SKIPPED_MESSAGES_THREAD_ID_EXTRACTION_ERRORS`: extraction/validation/persist failures
     - `SKIPPED_MESSAGES_THREAD_ID_NON_ASSIGNMENT`: non-assignment skips
     - `SKIPPED_MESSAGES_THREAD_ID_COMPILATIONS`: compilation skips (includes extracted assignment codes)
     - `SKIPPED_MESSAGES_THREAD_ID` remains a legacy fallback if the per-kind topic ids are not set.

This matters operationally: if an agency posts "10 assignments in one message", TutorDex can ingest all assignments safely (and will not proceed as a compilation unless 2+ identifiers are verified verbatim). Simple status updates are skipped without wasting LLM API calls.
#### LLM extraction call
- Code: `TutorDexAggregator/extract_key_info.py` (worker calls `extract_assignment_with_model`).
- Transport: OpenAI-compatible HTTP API configured by `LLM_API_URL` (default in `.env.example`: `http://host.docker.internal:1234`).
- The model name is set by `LLM_MODEL_NAME` / `MODEL_NAME`.

Inferred contract:
- The LLM produces a “display JSON” used by downstream formatting and persistence.
- The schema is validated after the call.

### 3.3 Normalization & schema enforcement
After the LLM output, the worker hardens the extracted data:

1) **Schema validation**
- Code: `TutorDexAggregator/schema_validation.py`.
- Function: `validate_parsed_assignment(parsed)`.
- This is a structural check: required fields, expected types, etc.
- **Important** (updated 2026-01-10): Online-only assignments (learning_mode starting with "Online") do not require address/postal_code/nearest_mrt fields. This supports "Online Tuition", "Online Lesson", etc.

2) **Hard validation (stricter rules)**
- Code: `TutorDexAggregator/hard_validator.py`.
- Function: `hard_validate(parsed, mode=...)`.
- Controlled by env `HARD_VALIDATE_MODE` with values: `off | report | enforce`.

3) **Normalization of raw input (optional for LLM prompt)**
- Code: `TutorDexAggregator/normalize.py`.
- Function: `normalize_text(raw_text)`.
- Toggle: `USE_NORMALIZED_TEXT_FOR_LLM`.

4) **Deterministic “signals” for matching**
- Code: `TutorDexAggregator/signals_builder.py`.
- Function: `build_signals(parsed)`.
- Toggle: `ENABLE_DETERMINISTIC_SIGNALS`.
- Documentation: `docs/signals.md`.

5) **Deterministic time availability override (important)**
- Code: `TutorDexAggregator/extractors/time_availability.py`.
- Function: `extract_time_availability(raw_text, ...)`.
- Toggle: `USE_DETERMINISTIC_TIME=1`.

Reality: the worker imports `extract_time_availability` and (when enabled) overwrites the LLM's time availability with deterministic parsing.

See doc: `docs/time_availability.md`.

6) **Estimated postal code extraction**
- Code: `TutorDexAggregator/extractors/postal_code_estimated.py`.
- Function: `estimate_postal_codes(raw_text)`.
- Toggle: `ENABLE_POSTAL_CODE_ESTIMATED`.

7) **Deterministic academic requests extraction (NEW 2026-01-10)**
- Code: `TutorDexAggregator/extractors/academic_requests.py`.
- Function: `parse_academic_requests(text=...)`.
- Purpose: Deterministically parses academic information from text:
  - Subjects (using `SubjectMatch` from `subjects_matcher.py`)
  - Levels (Primary, Secondary, JC, IB, IGCSE, etc.)
  - Specific student levels (Primary 1-6, Secondary 1-5, JC 1-2, IB Year 1-12, IGCSE Grade 1-12, etc.)
  - Streams (Express, NA, NT, IP, HL/SL, etc.)
  - Academic requests (per-slot breakdown of level/specific/stream/subjects without guessing)
- Integration: taxonomy v2 canonicalization to stable subject codes for filtering
- Tokenization uses regex patterns to identify:
  - Specific levels: "P1", "Sec 3", "JC 2", "IB Year 10", "IGCSE Grade 9"
  - General levels: "Primary", "Secondary", "JC", "IB", "IGCSE", "Poly"
  - Streams: "Express", "NA", "NT", "IP", "HL", "SL", "G1-G3", "H1-H3"
- Overlap resolution prefers longer, more specific tokens
- Output includes:
  - `subjects[]`: rollup of all subject mentions
  - `subjects_canonical[]`: taxonomy v2 canonical codes
  - `subjects_general[]`: taxonomy v2 general category codes
  - `levels[]`: rollup of all level mentions
  - `specific_student_levels[]`: rollup of specific levels
  - `streams[]`: rollup of stream mentions
  - `academic_requests[]`: structured per-request breakdown (only populated when unambiguous)
  - `evidence`: source snippets and token spans
  - `confidence_flags`: signals for ambiguous mappings

8) **Deterministic tutor types and rate breakdown extraction (NEW 2026-01-10)**
- Code: `TutorDexAggregator/extractors/tutor_types.py`.
- Function: `extract_tutor_types(text=..., parsed=..., agency=...)`.
- Purpose: Deterministically extracts tutor types and associated rates from text:
  - Part-timer (PT), Full-timer (FT), MOE/Ex-MOE, Fresh Grad, etc.
  - Rate ranges per tutor type with currency and unit detection
- Uses `shared/taxonomy/tutor_types.py::normalize_label` for agency-specific aliasing
- Rate parsing via regex: `$40-55/hr`, `25-30`, etc.
- Output:
  - `tutor_types[]`: list of normalized tutor type objects with canonical name, original text, agency, confidence
  - `rate_breakdown{}`: dict keyed by canonical tutor type, containing min/max/currency/unit/original_text/confidence
- Integration: Worker places these outputs in `meta.signals` during extraction; persistence layer (`supabase_persist`) prefers these deterministic signals for `assignments.tutor_types` and `assignments.rate_breakdown` fields
- Importance: These deterministic signals provide stable, non-LLM-dependent metadata for matching and filtering

### 3.4 Duplicate assignment detection (cross-agency)

This repo now implements cross-agency duplicate assignment detection to group assignments that are the same upstream posting appearing from multiple agency channels. Key points:

- Purpose: detect the same assignment posted by different agencies, surface a primary/representative assignment, and allow UI/backend/broadcast rules to prefer the primary and avoid duplicate broadcasts.
- Schema & migration: SQL migration `TutorDexAggregator/supabase sqls/2026-01-09_duplicate_detection.sql` adds `assignment_duplicate_groups` table and assignment columns: `duplicate_group_id`, `is_primary_in_group`, `duplicate_confidence_score` and related indices. Ensure this migration is applied before enabling detection.
- Config / toggles:
  - `DUPLICATE_DETECTION_ENABLED` (env) — master switch used by `supabase_persist` to run detection asynchronously.
  - `BROADCAST_DUPLICATE_MODE` (env) — controls broadcaster behavior: `all` (default), `primary_only`, `primary_with_note`.
- Detection flow:
  - After successful insert/update in `persist_assignment_to_supabase`, the code calls an async helper that invokes `duplicate_detector.detect_duplicates_for_assignment(...)` when `DUPLICATE_DETECTION_ENABLED=true`.
  - The detector computes similarity/score, creates/updates `assignment_duplicate_groups`, sets `duplicate_group_id`, `is_primary_in_group`, and `duplicate_confidence_score` on `public.assignments`.
  - Thresholds are configurable via the DB `duplicate_detection_config` table (migration seeds sensible thresholds: high=90, medium=70, low=55).
- API & UI integration:
  - Backend RPCs and API endpoints support duplicate-aware listing (see `TutorDexBackend/supabase_store.py` parameter `show_duplicates` / `p_show_duplicates`).
  - Website shows duplicate badges and a Duplicate modal (components: `TutorDexWebsite/src/components/ui/DuplicateBadge.jsx`, `DuplicateModal.jsx`) and calls `/assignments/{id}/duplicates` via `backend.js`.
  - Broadcaster respects `BROADCAST_DUPLICATE_MODE` and will skip non-primary duplicates when configured.
- Operator notes:
  - Apply DB migrations in `TutorDexAggregator/supabase sqls/` before enabling `DUPLICATE_DETECTION_ENABLED=true`.
  - Use `DUPLICATE_DETECTION_ENABLED=true` in staging first, monitor `duplicate_confidence_score` distributions (Prometheus metrics/logs) and adjust `duplicate_detection_config` values before flipping to production.
  - When changing duplicate config thresholds, re-run detection for historical assignments using the provided admin utilities in `TutorDexAggregator/duplicate_detector.py` (see docs/DUPLICATE_DETECTION_*.md).

- Code: `TutorDexAggregator/extractors/time_availability.py`.
- Function: `extract_time_availability(raw_text, ...)`.
- Toggle: `USE_DETERMINISTIC_TIME=1`.

Reality: the worker imports `extract_time_availability` and (when enabled) overwrites the LLM’s time availability with deterministic parsing.

See doc: `docs/time_availability.md`.

6) **Estimated postal code extraction**
- Code: `TutorDexAggregator/extractors/postal_code_estimated.py`.
- Function: `estimate_postal_codes(raw_text)`.
- Toggle: `ENABLE_POSTAL_CODE_ESTIMATED`.

### 3.5 Geo-enrichment and distance calculation

TutorDex includes a comprehensive geo-enrichment system for Singapore assignments.

#### Postal code coordinate resolution
- Code: `TutorDexAggregator/geo_enrichment.py`.
- Functions: `enrich_from_coords(lat, lon)` and coordinate resolution in `supabase_persist.py`.
- Data sources (in `TutorDexAggregator/data/`):
  - `mrt_data.json`: MRT station coordinates and line information
  - `2019_region_boundary.geojson`: Singapore planning region boundaries
- Coordinate priority (in `supabase_persist.py`):
  1. Explicit postal code: geocode via Nominatim (if not disabled)
  2. Estimated postal code: fallback if explicit geocoding fails
  3. No coordinates: if both fail
- Toggle: `DISABLE_NOMINATIM` (set to disable Nominatim geocoding)
- Toggle: `GEO_ENRICHMENT_ENABLED` (default: true)

#### Enrichment outputs
When coordinates are available, geo-enrichment adds:
- `nearest_mrt_computed_name`: name of nearest MRT station
- `nearest_mrt_computed_distance_km`: distance to nearest MRT (km)
- `planning_area_computed`: Singapore planning area name
- `region_computed`: Singapore region (e.g., "Central", "West", "North", "East", "North-East")

#### Postal code estimation and distance fallback (NEW 2026-01-07)
- Migration: `TutorDexAggregator/supabase sqls/2026-01-07_postal_coords_estimated.sql`.
- New column: `assignments.postal_coords_estimated` (boolean)
- Purpose: Support distance calculations when only estimated postal codes are available
- Behavior:
  - When explicit `postal_code` is absent or geocoding fails, try first `postal_code_estimated`
  - Set `postal_coords_estimated=true` to signal fallback was used
  - Frontend displays "(estimated)" indicator for distances derived from estimated coordinates
- Documentation: `docs/MIGRATION_2026-01-07_estimated_postal_distance.md`

#### Distance sorting
- Migration: `TutorDexAggregator/supabase sqls/2025-12-29_assignments_distance_sort.sql`.
- Backend RPC: `list_open_assignments_v2` supports distance-based pagination
- Requires tutor profile with `postal_lat` and `postal_lon`
- Website enables "Nearest" sort when tutor coordinates are available

### 3.6 Storage (DB, cache, files)

#### Supabase (system DB)
Supabase is the persistence layer for assignments and analytics.

Supabase HTTP access is centralized in `shared/supabase_client.py` (single client implementation). Avoid introducing new Supabase REST wrappers in service code; extend the shared client if new capabilities are needed.

Core schema file:
- `TutorDexAggregator/supabase sqls/supabase_schema_full.sql`

Key tables (from schema):
- `public.agencies`: agency registry.
- `public.telegram_channels`: ingestion metadata.
- `public.telegram_messages_raw`: lossless raw messages.
- `public.telegram_extractions`: queue state + canonical JSON + meta diagnostics.
- `public.assignments`: denormalized “website-friendly” assignment rows.
- `public.users`: users (keyed by Firebase UID).
- `public.user_preferences`: durable copy of tutor preferences.
- `public.analytics_events`: event tracking.
- `public.assignment_clicks` and `public.broadcast_messages`: click tracking + broadcast message mapping (from `2025-12-25_click_tracking.sql`).

#### Redis (backend runtime store)
- Code: `TutorDexBackend/redis_store.py`.
- Stores:
  - tutor profiles: `tutordex:tutor:<tutor_id>` hash
  - tutor list set: `tutordex:tutors`
  - Telegram link codes: `tutordex:tg_link:<code>` (TTL)
  - click cooldown keys: `tutordex:click_cd:<external_id>:<ip_hash>` (set with NX)

#### Local files
Used for “fallback when not configured”:
- Broadcast fallback JSONL: `TutorDexAggregator/outgoing_broadcasts.jsonl` (configurable).
- DM fallback JSONL: `TutorDexAggregator/outgoing_dm.jsonl`.
- Collector logs: `TutorDexAggregator/logs/` and backend logs in `TutorDexBackend/logs/`.
- Telegram link bot offset persistence: `TutorDexBackend/telegram_link_bot_offset.json` (mounted in docker as `telegram_link_bot_state` volume).

### 3.7 Backend APIs

#### Website-facing endpoints (some public, some authenticated)
Website calls these paths via `TutorDexWebsite/src/backend.js` (which adds `Authorization: Bearer <Firebase ID token>` when available):
- `GET /me/tutor` → read current tutor preferences.
- `PUT /me/tutor` → upsert tutor preferences.
- `POST /me/telegram/link-code` → generate a short-lived link code.
- `GET /assignments` → list open assignments (paged). (public for `sort=newest`; `sort=distance` requires auth)
- `GET /assignments/facets` → filter dropdown counts. (public)
- `POST /analytics/event` → record a UI event.

Auth enforcement is optional.
- Code: `TutorDexBackend/firebase_auth.py` and token verification `verify_bearer_token`.
- Behavior toggle is in backend (`AUTH_REQUIRED`), enforced in app middleware/routes via `AuthService.require_uid()` and `AuthService.require_admin()` (see `TutorDexBackend/services/auth_service.py`).

#### Matching endpoint (used by Aggregator for DM sending)
- `POST /match/payload`.
- Implementation: `TutorDexBackend/matching.py` → `match_from_payload(store, payload)`.
- Critical expectation: the Aggregator worker provides deterministic signals in `meta.signals` (Supabase row `meta.signals` contains `{ "ok": true, "signals": { ... } }`) — the actual signal map lives under `meta.signals.signals` (subjects + levels). Matching relies on these deterministic rollups for stability.

#### Assignment DM routing (launch-simple default, 2026-01-15)

TutorDex currently uses a conservative “launch-simple” DM routing rule:
- Must match **level + subject** the tutor selected.
- If the tutor has a postal code/coords saved, only send if **distance ≤ dm_max_distance_km** (default 5km).
- If the tutor has **no postal code**, distance filtering is skipped (send all subject+level matches).
- If the tutor has coords but the assignment is in-person/hybrid and distance cannot be computed, it does **not** match (avoid false positives).

**Where this lives:**
- Backend matching: `TutorDexBackend/matching.py`
- Tutor preference field: `public.user_preferences.dm_max_distance_km` (default 5)
- Website profile: `TutorDexWebsite/profile.html` + `TutorDexWebsite/src/page-profile.js`
- DB migration: `TutorDexAggregator/supabase sqls/2026-01-15_add_dm_max_distance_km.sql`

#### Assignment rating system (optional / future-facing)

The assignment rating + adaptive threshold system from 2026-01-09 remains in the repo (schema + functions + code), but is not the default routing strategy for launch.

If you re-enable it later, see:
- Design: `docs/assignment_rating_system.md`
- Implementation: `docs/ASSIGNMENT_RATING_IMPLEMENTATION_SUMMARY.md`
- Migration: `TutorDexAggregator/supabase sqls/2026-01-09_assignment_ratings.sql`
- Env toggle: `DM_USE_ADAPTIVE_THRESHOLD` (repo examples set this to `false`)

### 3.8 Frontend consumption

The website is a static Firebase-hosted app.
- HTML pages: `TutorDexWebsite/index.html`, `TutorDexWebsite/assignments.html`, `TutorDexWebsite/profile.html`.
- Auth bootstrap: `TutorDexWebsite/auth.js`.
- Assignment page logic: `TutorDexWebsite/src/page-assignments.js`.
- Profile page logic: `TutorDexWebsite/src/page-profile.js`.

Assignments are loaded from backend:
- `listOpenAssignmentsPaged` in `TutorDexWebsite/src/backend.js` calls `GET /assignments?limit=...&sort=...&...`.
- Public browsing protections (anonymous users) live in `TutorDexBackend/services/cache_service.py`:
  - rate limiting on `GET /assignments` and `GET /assignments/facets`
  - public limit caps for `/assignments`
  - short Redis-backed caching for common anonymous queries (facets + first page newest)
- The assignment rows are mapped by `mapAssignmentRow(row)` in `page-assignments.js`.

Assignments page UX (tutor-focused):
- Guest browsing is enabled on `TutorDexWebsite/assignments.html` (`data-require-auth="false"`); profile remains authenticated.
- Cards show both timestamps:
  - `Posted ...` uses `published_at` (fallback `created_at` / `last_seen`)
  - `Bumped/Updated ...` uses `source_last_seen` (fallbacks) which drives “Open-likelihood”
- Filters are remembered locally (localStorage) so the page reopens “ready”.
- Subject search (label/code contains match) auto-selects a canonical subject filter.
- A compact/full toggle supports faster scanning; cards also support local-only Save/Hide.

DB/RPC requirement:
- The website expects `source_last_seen` to be returned by the assignment listing RPCs; apply `TutorDexAggregator/supabase sqls/2026-01-04_03_rpc_return_source_last_seen.sql` if your feed doesn’t include bump timestamps.

Subjects filtering (taxonomy v2):
- Backend supports subject filters as *codes*:
  - `subject_general=<general_category_code>` (e.g. `MATH`, `SCIENCE`)
  - `subject_canonical=<canonical_subject_code>` (e.g. `MATH.SEC_EMATH`)
- Back-compat: `subject=<string>` still works (matches legacy `signals_subjects` and also matches code arrays in DB RPCs).

Distance-based sorting:
- Website uses “Nearest” sort option.
- Backend must support distance pagination (Supabase RPC `list_open_assignments_v2` from `2025-12-29_assignments_distance_sort.sql`).
- Website enables Nearest only when the tutor profile has `postal_lat` and `postal_lon`.

### 3.9 User interaction (apply, click, track)

#### “Apply Now” click
On the assignment card:
- If `message_link` exists, the Apply button is an `<a>` to the original Telegram message.
- On click, `page-assignments.js` calls `sendClickBeacon(...)` from `TutorDexWebsite/src/backend.js`.

Beacon payload:
- `event_type`: typically `apply_click`
- `assignment_external_id`: assignment id (prefers `external_id`)
- `destination_type`: `telegram_message`
- `destination_url`: telegram message URL

Backend endpoint:
- `POST /track`.
- Dedup logic:
  - `AnalyticsService.check_click_cooldown()` uses Redis `SET NX EX` keyed by `external_id` + hashed IP.

Supabase updates:
- Backend resolves a canonical `original_url`:
  - prefer `destination_url` from beacon
  - else look up `broadcast_messages.original_url` via `SupabaseStore.get_broadcast_message` (see `AnalyticsService.resolve_broadcast_url()`).
- Backend increments clicks via Supabase RPC `increment_assignment_clicks` (defined in `TutorDexAggregator/supabase sqls/2025-12-25_click_tracking.sql`).

#### Analytics events
- Website calls `trackEvent(...)` (POST `/analytics/event`) on view/save flows.
- Backend writes to `public.analytics_events` using `SupabaseStore.insert_event`.

### 3.10 Analytics / logging / auditing

Logging:
- Aggregator: `TutorDexAggregator/logging_setup.py` emits structured logs, and can emit JSON logs when `LOG_JSON=true` (root `docker-compose.yml` sets it).
- Backend: `TutorDexBackend/logging_setup.py` similar pattern.

Metrics:
- Aggregator collector exposes `/metrics` via `observability_http.start_observability_http_server`.
- Backend exposes `/metrics` route.
- Prometheus scrapes them (wired in root compose).

Traces:
- OTEL is wired via `TutorDexAggregator/otel.py` and `TutorDexBackend/otel.py`, but is only active when `OTEL_ENABLED=1` (see `observability/README.md`).

Audit data:
- `telegram_messages_raw` is the “source of truth” audit log for Telegram ingestion.
- `telegram_extractions.meta` stores processing metadata, attempt counts, errors, pipeline version, etc.

---

## 4. TutorDexAggregator

### Purpose
- Pull raw assignments from upstream sources.
- Extract structured data via LLM + deterministic processing.
- Store results in Supabase.
- Optionally broadcast and/or DM matched tutors.

### Entry points
- `collector.py`:
  - `python collector.py backfill ...`
  - `python collector.py tail`
- `workers/extract_worker.py`:
  - `python workers/extract_worker.py`
- Optional/legacy scripts:
  - `expire_assignments.py`, `update_freshness_tiers.py`, `utilities/run_sample_pipeline.py`

### Core pipelines

#### Pipeline A (current, “production”): collector → queue → worker
- Collector (`collector.py`) writes raw rows + enqueues jobs.
- Worker (`workers/extract_worker.py`) drains jobs and runs extraction.

This is the path wired by root `docker-compose.yml`:
- service `collector-tail`: `python collector.py live` (a first-class subcommand that runs `tail` + automated catchup)
- service `aggregator-worker`: `python workers/extract_worker.py`

#### Sidecars (scheduled)
- `tutorcity-fetch` service:
  - Script: `TutorDexAggregator/utilities/tutorcity_fetch.py`
  - Purpose: polls TutorCity API and persists via `supabase_persist` (no raw Telegram tables involved)
  - Interval: configurable via `TUTORCITY_FETCH_INTERVAL_SECONDS` (default: 300s / 5min)
  - Limit: `TUTORCITY_LIMIT` (default: 50 assignments per poll)
  - Bypasses Telegram raw tables and extraction queue
  - Uses same persistence and distribution paths as Telegram assignments
  - Timestamp semantics: `published_at` is source publish time (not updated on polls), `last_seen` updates when content fingerprint changes
  - TutorCity IDs: `external_id` = `assignment_code`; old composite IDs can be cleaned up with `2026-01-04_05_tutorcity_cleanup_composite_external_ids.sql`
  
- `freshness-tiers` service:
  - Script: `TutorDexAggregator/update_freshness_tiers.py`
  - Purpose: periodically updates `assignments.freshness_tier` based on `source_last_seen` age and can expire old assignments
  - Interval: configurable via `FRESHNESS_TIERS_INTERVAL_SECONDS` (default: 3600s / 1 hour)
  - Thresholds: `--green-hours`, `--yellow-hours`, `--orange-hours`, `--red-hours`, `--expire-hours` (defaults: 24/36/48/72/168)
  - Expiration action: `--expire-action` (choices: `expired` status, `hidden`, or `delete`)
  - Optional: `--delete-expired-telegram` flag to also delete Telegram broadcast messages for expired assignments (requires bot token and broadcast message mapping)
  - Enable/disable: `FRESHNESS_TIER_ENABLED` env var
  - Docker compose service runs continuously with a sleep loop

#### Pipeline B (legacy, direct ingest/extract)
Some older scripts/directories have been removed as part of legacy cleanup (see `docs/REMOVED_FILES.md`).

### LLM architecture

#### Prompting strategy
- System prompt can be supplied via env (`LLM_SYSTEM_PROMPT_FILE` or `LLM_SYSTEM_PROMPT_TEXT` in `TutorDexAggregator/.env.example`).
- Examples can be toggled via `LLM_INCLUDE_EXAMPLES` and variant/directory env vars.
- Agency-specific examples live under `TutorDexAggregator/message_examples/`.

This is designed so operators can tweak prompts without code changes.

#### Models used
- The worker calls an OpenAI-compatible API at `LLM_API_URL`.
- The model name is selected via `LLM_MODEL_NAME` / `MODEL_NAME`.

The repo assumes a local model server (LM Studio / llama.cpp HTTP server).
- Evidence: `.env.example` default `LLM_API_URL=http://host.docker.internal:1234` and `start_llama_server_loop.bat`.

#### Validation / auditing flow
- Raw is stored first (audit).
- Extraction job records status + errors + attempts (`telegram_extractions.meta`).
- Canonical JSON is persisted in both `telegram_extractions.canonical_json` and denormalized into `assignments`.

### Error handling & retries
- Queue claim is safe via DB row locking.
- Worker has max attempts and exponential backoff:
  - `EXTRACTION_MAX_ATTEMPTS`, `EXTRACTION_BACKOFF_BASE_S`, `EXTRACTION_BACKOFF_MAX_S`.
- Stale `processing` jobs can be requeued after `EXTRACTION_STALE_PROCESSING_SECONDS`.

### Performance characteristics (what matters)
- The LLM call is the dominant latency per job.
- The worker batch size affects throughput (`EXTRACTION_WORKER_BATCH`).
- Supabase PostgREST calls happen for: claim, load raw, update status, upsert assignment.

### Known sharp edges (documenting reality)
- Compilation detection can skip high-value posts (multi-assignment). Tuning knobs exist but are heuristics.
- Deterministic time override can disagree with LLM output; this is intentional but can be surprising.
- Supabase URL routing differs inside/outside Docker (`SUPABASE_URL_DOCKER` vs `SUPABASE_URL_HOST`). Misconfig is a frequent failure mode.

---

## 5. TutorDexBackend

### Architecture (Refactored 2026-01-12)

**Before refactoring**: `app.py` was a 1547-line monolithic file mixing routing, auth, caching, analytics, and health checks.

**After refactoring**: Modular service architecture with clear separation of concerns:

```
TutorDexBackend/
├── app.py (1033 lines)          # HTTP routing + Pydantic models
├── utils/                        # Pure utility functions
│   ├── config_utils.py          # Environment configuration parsing
│   ├── request_utils.py         # HTTP request utilities (IP, traceparent)
│   └── database_utils.py        # PostgreSQL/Supabase helpers
├── services/                     # Domain services (isolated, testable)
│   ├── auth_service.py          # Firebase token verification, admin auth
│   ├── health_service.py        # Health checks for all services
│   ├── cache_service.py         # Rate limiting + response caching
│   ├── telegram_service.py      # Webhook verification, callbacks
│   └── analytics_service.py     # Click tracking, event insertion
├── matching.py                   # Tutor matching logic (unchanged)
├── redis_store.py               # Redis store operations (unchanged)
├── supabase_store.py            # Supabase operations (unchanged)
├── firebase_auth.py             # Firebase Admin SDK (unchanged)
└── ... (other modules unchanged)
```

**Key service responsibilities**:
- `AuthService`: Firebase token verification, admin API key validation, production config validation
- `HealthService`: Aggregates health checks for Redis, Supabase, worker, collector, webhook
- `CacheService`: Rate limiting for anonymous users, response caching with Redis fallback
- `TelegramService`: Webhook secret verification, callback query handling
- `AnalyticsService`: Click cooldown tracking, URL resolution, event insertion

All 30 API endpoints preserved with identical signatures. Zero breaking changes.

### API surface (actual)
Implemented in `TutorDexBackend/app.py` (HTTP routing) with business logic delegated to services.

Categories:
- Website tutor profile:
  - `GET /me/tutor`, `PUT /me/tutor`
  - `POST /me/telegram/link-code`
- Assignment feed:
  - `GET /assignments` (paged)
  - `GET /assignments/facets`
- Analytics:
  - `POST /analytics/event`
- Click tracking:
  - `POST /track`
- Matching:
  - `POST /match/payload`
- Health/metrics:
  - `GET /health/full`, `GET /metrics`
- Telegram integrations:
  - `POST /telegram/claim` (called by link bot)
  - Telegram callback handling for clicks likely via `/telegram/callback` (see `TutorDexBackend/app.py`; used when Telegram inline buttons send callback queries)

### Auth model
Two layers exist:

1) Website authentication (Firebase)
- Website obtains Firebase ID tokens (`TutorDexWebsite/auth.js` → `getIdToken`).
- Website attaches token in `Authorization: Bearer ...` (`TutorDexWebsite/src/backend.js`).

2) Backend verification (optional)
- Backend can verify tokens with Firebase Admin SDK (`TutorDexBackend/firebase_auth.py`).
- Auth verification logic now centralized in `TutorDexBackend/services/auth_service.py` (`AuthService` class).
- Toggle:
  - `FIREBASE_ADMIN_ENABLED=true`
  - provide `FIREBASE_ADMIN_CREDENTIALS_PATH` (mounted in docker as `/run/secrets/firebase-admin-service-account.json`).

Admin/bot auth:
- Some endpoints accept `x-api-key` (see `.env.example` and `TutorDexBackend/telegram_link_bot.py` which uses `BACKEND_API_KEY` or `ADMIN_API_KEY`).
- Admin auth validation handled by `AuthService.require_admin()`.

### Database schema (tables, key fields)
Backend uses Supabase for durable tables.

Key tables for backend behavior:
- `public.users`: maps `firebase_uid` to internal `id`.
- `public.user_preferences`: durable preferences; backend mirrors/updates from Redis.
- `public.analytics_events`: (user_id?, assignment_id?, event_type, event_time, meta).
- `public.assignments`: read-only feed for website listing.
- `public.assignment_clicks` + `public.broadcast_messages`: click tracking and mapping.

### Click / apply tracking
- Website sends click beacons (`sendClickBeacon`) to `POST /track`.
- Backend deduplicates by IP + assignment via Redis NX keys (logic in `AnalyticsService.check_click_cooldown()`).
- Supabase increments are atomic via RPC `increment_assignment_clicks`.
- If broadcast mapping exists (`broadcast_messages`), backend can edit the Telegram broadcast message content (requires the bot token that originally posted it).

### Telegram integrations
Two integrations exist:

1) Linking tutor Telegram chat IDs
- Website generates a short code: `POST /me/telegram/link-code`.
- Tutor sends `/link <code>` to a Telegram bot, or uses the website deep-link (`/start link_<code>`).
- Poller `TutorDexBackend/telegram_link_bot.py` reads updates via Telegram Bot API `getUpdates` and calls backend `POST /telegram/claim`.
- Backend stores `chat_id` for that tutor in Redis and optionally in Supabase preferences.

2) Callback query handling (for inline buttons)
- Backend callback query handling logic in `TelegramService.answer_callback_query()` (called from `/telegram/callback` endpoint in `app.py`).
- This is used to respond to Telegram callback queries and can open URLs.

### Background jobs / workers
- The backend itself is stateless besides Redis; it does not run internal job queues.
- The Telegram link bot is the only long-running “worker” associated with backend, deployed as a separate docker service.

### Failure modes (what breaks in real life)
- Missing/invalid Firebase Admin service account → auth verification silently disables (see `firebase_auth.init_firebase_admin_if_needed`).
- Supabase RPCs missing:
  - Assignments listing and facets depend on `list_open_assignments` / `list_open_assignments_v2` / `open_assignment_facets`.
  - Click tracking depends on `increment_assignment_clicks`.
- Redis not reachable → matching and click cooldown degrade.

---

## 6. TutorDexWebsite

### Pages & routing
Static pages (Firebase Hosting):
- `index.html`: sign-in/sign-up entry.
- `assignments.html`: assignment browsing.
- `profile.html`: tutor profile/preferences.

No SPA router; navigation is via static links.

### Key UI flows

#### Auth
- Bootstrap: `TutorDexWebsite/auth.js` waits for Firebase auto-init scripts (`/__ /firebase/init.js`) to load.
- Supported methods:
  - Email/password
  - Google sign-in popup
- Pages that require auth use `data-require-auth="true"` on `<body>` (see `assignments.html` and `profile.html`).

#### Browse assignments
- Page script: `TutorDexWebsite/src/page-assignments.js`.
- Calls backend for:
  - facets
  - paginated list
- Renders cards and provides filters.
- Sort semantics:
  - `sort=newest` orders by `assignments.published_at` (fallback `created_at`, then `last_seen`).
  - The UI still displays “updated” time using `last_seen` / `created_at`.

Subjects taxonomy v2 integration:
- Filter dropdowns are derived from taxonomy v2 JSON (not hard-coded arrays).
- Cards prefer taxonomy-derived canonical labels when available (fallback to legacy `signals_subjects` when needed).

#### Manage profile
- Page script: `TutorDexWebsite/src/page-profile.js`.
- Saves preferences to backend, including optional postal code.
- Generates Telegram link code for DM enabling.
- “Check recent matches” queries the backend for how many assignments (open + closed) matched the current preferences in the last 7/14/30 days.

Subjects storage (important):
- Tutor profile `subjects[]` are stored as taxonomy v2 canonical subject codes (not human labels).
- `subject_pairs[].subject` is also stored as canonical codes.

### State management
Vanilla JS + DOM state. There is no React/Vue/etc.

Key in-memory state on assignments page:
- `allAssignments`, cursors (`nextCursorLastSeen`, `nextCursorId`, `nextCursorDistanceKm`).

### Tracking logic
- Click tracking: `sendClickBeacon` in `TutorDexWebsite/src/backend.js`.
- Analytics: `trackEvent` → backend `POST /analytics/event`.

### Integration with backend
- Backend base URL is embedded at build time via `VITE_BACKEND_URL`.
- If missing, the UI explicitly disables backend features and shows a friendly error (see `formatAssignmentsLoadError`).

### Known UX compromises (reality)
- If backend is misconfigured, assignments page becomes unusable (by design; there is no direct Supabase fallback).
- Auth errors frequently come from Firebase Hosting misconfiguration (`auth/configuration-not-found`, `auth/unauthorized-domain`). The site includes helper messaging in `auth.js`.

---

## 7. Shared Modules & Contracts

### Purpose
The `shared/` directory contains Python modules and schemas that are shared across the monorepo components. This ensures consistency in data structures and business logic.

### shared/contracts
**Location:** `shared/contracts/`

**Purpose:** Define and validate the canonical assignment row schema that flows between all components.

**Key files:**
- `assignment_row.schema.json`: The authoritative JSON Schema for assignment rows
- `validate_contracts.py`: Validation tool to ensure synced copies match
- `README.md`: Documentation on contract validation and syncing

**Synced copies:**
The schema is copied to component-specific locations for local validation:
- `TutorDexBackend/contracts/assignment_row.schema.json`
- `TutorDexWebsite/src/generated/assignment_row.schema.json`
- TypeScript definitions: `TutorDexWebsite/src/generated/assignmentRow.d.ts`

**Sync mechanism:**
- CI workflow: `.github/workflows/contracts-validate.yml`
- Validates on PR changes to `shared/contracts/` or component contract files
- Runs: `python3 shared/contracts/validate_contracts.py`
- Fails if synced copies are out of date or schema is invalid
- Developer workflow: manually copy schema to synced locations when making changes

**Contract fields include:**
- Core IDs: `id`, `external_id`, `message_link`
- Academic: `subjects`, `subjects_canonical`, `subjects_general`, `levels`, `specific_student_levels`, `streams`, `academic_requests`
- Location: `postal_code`, `postal_code_estimated`, `postal_lat`, `postal_lon`, `postal_coords_estimated`, `nearest_mrt_computed_*`, `region_computed`
- Metadata: `status`, `freshness_tier`, `published_at`, `source_last_seen`, `last_seen`
- Tutor matching: `tutor_types`, `rate_breakdown`, `rate_min`, `rate_max`, `learning_mode`
- Duplicate detection: `duplicate_group_id`, `is_primary_in_group`, `duplicate_confidence_score`
- Click tracking: `click_count`

### shared/taxonomy
**Location:** `shared/taxonomy/`

**Purpose:** Canonical taxonomies for subjects and tutor types with normalization logic.

#### Subjects taxonomy v2
**Location:** `shared/taxonomy/subjects/`

**Key files:**
- `subjects_taxonomy_v2.json`: The authoritative subject hierarchy with stable codes
- `subjects_map_v2.json`: Mapping from raw subject strings to canonical codes
- `subjects_enums_v2.json`: TypeScript enum exports
- `validate_taxonomy.py`: Validation and sync checking tool
- `sync_taxonomy_artifacts.py`: Generates map and enums from taxonomy
- `implementation_v2.md`: Implementation guide
- `MAPPING_RULES_v2.md`: Rules for adding/updating subject mappings

**Structure:**
- General categories (e.g., `MATH`, `SCIENCE`, `LANGUAGES`) contain canonical subjects
- Canonical subjects have stable codes (e.g., `MATH.SEC_EMATH`, `SCI.SEC_PHYSICS`)
- Level-specific variations supported (Primary Math vs Secondary Math vs JC Math)
- IB/IGCSE subjects tracked separately

**Workflow:**
1. Edit `subjects_taxonomy_v2.json` (add/modify categories or subjects)
2. Run `python3 shared/taxonomy/subjects/sync_taxonomy_artifacts.py` to regenerate map and enums
3. Run `python3 shared/taxonomy/subjects/validate_taxonomy.py --check-sync` to verify
4. CI validates on PR: `.github/workflows/taxonomy-validate.yml`

**Integration:**
- Extraction: `TutorDexAggregator/taxonomy/canonicalize_subjects.py` uses this taxonomy
- Academic requests: `TutorDexAggregator/extractors/academic_requests.py` calls canonicalization
- Database: `TutorDexAggregator/supabase sqls/2026-01-03_subjects_taxonomy_v2.sql` creates DB support
- Backend: filters use `subject_canonical` and `subject_general` codes
- Website: dropdowns derived from taxonomy, not hard-coded arrays

#### Tutor types taxonomy
**Location:** `shared/taxonomy/tutor_types.py`

**Purpose:** Normalize tutor type labels (Part-timer, Full-timer, MOE, Ex-MOE, etc.) with agency-specific aliasing.

**Function:** `normalize_label(label: str, agency: Optional[str] = None) -> Tuple[str, str, float]`
- Returns: `(canonical_name, original_label, confidence)`
- Handles common aliases: "PT" → "part-timer", "FT" → "full-timer", "MOE" → "moe-exmoe"
- Agency-specific rules can be added for special cases

**Integration:**
- Used by: `TutorDexAggregator/extractors/tutor_types.py`
- Output: deterministic `tutor_types[]` and `rate_breakdown{}` in `meta.signals`

**Extensibility:**
- Add agency-specific aliases by extending the mapping logic
- Confidence scoring helps identify uncertain normalizations

### Why shared modules matter
- **Consistency:** All components use the same definitions
- **Validation:** CI catches drift before it reaches production
- **Maintainability:** Single source of truth for taxonomies
- **Type safety:** Generated TypeScript definitions for frontend
- **Backwards compatibility:** Stable codes survive label changes

---

## 8. Infrastructure & Deployment

### Docker setup (single system)
Root `docker-compose.yml` is the intended “run everything” config.

Services:
- `collector-tail` (Aggregator collector)
- `aggregator-worker` (Aggregator extraction worker)
- `backend` (FastAPI)
- `telegram-link-bot` (Telegram poller)
- `redis`
 - Observability stack: `prometheus`, `grafana`, `alertmanager` (Loki/Promtail/Tempo/OTEL removed from default local stack).

### Environments (dev / prod)
There is not a rigid environment abstraction. Reality is env vars + docker compose.

Backend:
- `APP_ENV=prod` enforces `ADMIN_API_KEY` at startup.

Aggregator:
- Controlled by `.env` toggles (queue on/off, broadcast on/off, deterministic time on/off, etc.).

### Secrets management
Current reality:
- Docker compose loads `.env` files from `TutorDexAggregator/.env` and `TutorDexBackend/.env`.
- Firebase Admin JSON is mounted as a Docker secret-ish file (`/run/secrets/firebase-admin-service-account.json`).
- GitHub Actions store secrets for:
  - Tailscale deploy: `TAILSCALE_AUTHKEY`, `SERVER_TS_IP`, `SERVER_USER`, `SERVER_SSH_KEY`
  - Firebase Hosting: `FIREBASE_SERVICE_ACCOUNT`, `VITE_BACKEND_URL` and repo var `FIREBASE_PROJECT_ID`.

### CI/CD
- `.github/workflows/deploy.yml`:
  - Trigger: PR merged into `main`.
  - Action: uses Tailscale then SSH into a Windows server and runs `git pull` + `docker compose up -d --build`.
- `.github/workflows/firebase-hosting.yml`:
  - Deploys the website to Firebase Hosting on `main` pushes and PR previews.

### Hosting assumptions
- The “server” is a Windows machine running Docker Desktop.
- A Supabase instance is expected to exist on the external Docker network `supabase_default` (see root compose `supabase_net`).
  - This repo does not include the Supabase stack itself; it assumes you run it separately.

---

## 9. Operational Playbook

### Run locally (fastest path)

1) Ensure Supabase is running and accessible:
- If self-hosted in Docker, ensure the Kong container is reachable as `supabase-kong:8000` from the TutorDex containers.
- Set `SUPABASE_URL_DOCKER=http://supabase-kong:8000` in both Aggregator and Backend `.env`.

2) Configure env files:
- Copy and edit `TutorDexAggregator/.env.example` → `TutorDexAggregator/.env`.
- Copy and edit `TutorDexBackend/.env.example` → `TutorDexBackend/.env`.

3) Apply DB schema + RPCs in Supabase:

**Core schema and RPCs (required):**
- `TutorDexAggregator/supabase sqls/supabase_schema_full.sql` — base schema with all tables
- `TutorDexAggregator/supabase sqls/2025-12-22_extraction_queue_rpc.sql` — extraction queue claim/enqueue RPCs
- `TutorDexAggregator/supabase sqls/2025-12-25_assignments_facets_pagination.sql` — facets and list RPCs

**Feature-specific migrations (apply as needed):**
- `TutorDexAggregator/supabase sqls/2025-12-25_click_tracking.sql` — click tracking tables + RPCs (for broadcast edits)
- `TutorDexAggregator/supabase sqls/2025-12-29_assignments_distance_sort.sql` — distance-based sorting RPC v2
- `TutorDexAggregator/supabase sqls/2026-01-03_subjects_taxonomy_v2.sql` — subjects taxonomy v2 (canonical codes + filters)
- `TutorDexAggregator/supabase sqls/2026-01-04_01_assignments_published_at.sql` — adds `published_at` column
- `TutorDexAggregator/supabase sqls/2026-01-04_02_assignments_source_last_seen.sql` — adds `source_last_seen` column
- `TutorDexAggregator/supabase sqls/2026-01-04_03_rpc_return_source_last_seen.sql` — updates RPCs to return source timestamps
- `TutorDexAggregator/supabase sqls/2026-01-04_04_verify_source_last_seen_and_indexes.sql` — verification queries for timestamps
- `TutorDexAggregator/supabase sqls/2026-01-04_05_tutorcity_cleanup_composite_external_ids.sql` — TutorCity ID cleanup (one-time)
- `TutorDexAggregator/supabase sqls/2026-01-07_postal_coords_estimated.sql` — adds `postal_coords_estimated` flag
- `TutorDexAggregator/supabase sqls/2026-01-07_update_list_open_assignments_v2.sql` — updates list RPC for estimated coords
- `TutorDexAggregator/supabase sqls/2026-01-09_duplicate_detection.sql` — duplicate detection tables + config
- `TutorDexAggregator/supabase sqls/2026-01-09_assignment_ratings.sql` — assignment rating system tables + threshold calculation
- `TutorDexAggregator/supabase sqls/2026-01-10_add_tutor_types_rate_breakdown_to_list_v2.sql` — adds tutor_types/rate fields to list RPC

**Migration order:**
Apply in chronological order (date prefix). The full schema includes these migrations, but incremental migration is safer for production.

**Verification:**
Run smoke test to confirm all required RPCs exist:
```bash
# Windows (cmd)
scripts\\smoke_test_all.bat

# Or run the Python runner directly (cross-platform)
py -3 scripts/smoke_test.py
```

4) Start the stack:
- From repo root: `docker compose up -d --build`
  - This brings up BOTH the main TutorDex services and the observability stack under the `tutordex` compose project.
  - Note: observability services like Grafana/Prometheus/Loki/Tempo/Promtail/Otel Collector are `image:` services, so `--build` does not rebuild them. To refresh them, run `docker compose pull` first (or use `docker compose up -d --build --pull always`).

Avoid:
- Running `observability/docker-compose.observability.yml` standalone; it creates a second compose project named `observability` and duplicates the monitoring stack.

5) Website local preview:
- From `TutorDexWebsite/`: `npm i` then `npm run serve:firebase`.

### Deploy safely
- Backend + Aggregator deploy via the Windows server pipeline (GitHub Actions + Tailscale SSH). Confirm Supabase connectivity on the server.
- Website deploy via Firebase Hosting pipeline. Confirm `VITE_BACKEND_URL` points to the deployed backend.

### Rollback
Reality: rollback is “git checkout previous commit + docker compose up”.
- If you are in a bad state, the fastest rollback is to revert the merge commit on `main` and let deploy pipeline run.

### Where to look when things break
- Aggregator:
  - Container logs (`docker compose logs collector-tail` / `aggregator-worker`)
  - Supabase `telegram_extractions` statuses and `meta` errors
- Backend:
  - `/health/full` and `/metrics`
  - Redis connectivity
- Website:
  - Firebase Hosting deploy status and browser console auth messages
- Observability:
  - Grafana dashboards + Loki logs (see `observability/README.md`)

---

## 10. System Invariants & Contracts

These are the things that silently break the system if changed.

### Contract A: extraction queue RPCs
- Required functions (Supabase):
  - `public.enqueue_telegram_extractions(...)`
  - `public.claim_telegram_extractions(...)`
- Source file: `TutorDexAggregator/supabase sqls/2025-12-22_extraction_queue_rpc.sql`.

If you change the table schema for `telegram_extractions`, ensure the RPC still returns rows the worker expects.

### Contract B: denormalized assignments columns
The website expects the backend to return fields aligned to `mapAssignmentRow()` in `TutorDexWebsite/src/page-assignments.js`:
- `external_id`, `message_link`, `academic_display_text`, `signals_subjects`, `signals_levels`, `signals_specific_student_levels`, `rate_min`, `rate_raw_text`, `freshness_tier`, `lesson_schedule`, `time_availability_note`, `postal_code_estimated`, `nearest_mrt_computed_*`, etc.
- Subjects taxonomy v2 columns (used for filtering + display):
  - `subjects_canonical`
  - `subjects_general`
  - `canonicalization_version`

These come from the Supabase RPC output columns.
If you rename/remove columns in `public.assignments`, you must update:
- Supabase RPC functions (`list_open_assignments*` / `open_assignment_facets`)
- Backend serialization
- Website mapping

### Contract C: deterministic signals location in payload
Matching depends on the Aggregator embedding deterministic signals in `meta.signals` (see `TutorDexAggregator` worker flow). The persistence layer (`supabase_persist`) prefers these deterministic signals for `tutor_types` and `rate_breakdown` over the LLM `parsed` fields when present.
- Producer: `TutorDexAggregator/signals_builder.py`.
- Consumer: `TutorDexBackend/matching.py::_payload_to_query`.

If you move signals, matching will quietly degrade (empty query → low scores).

### Contract F: duplicate detection schema & config
- The duplicate detection migration (`TutorDexAggregator/supabase sqls/2026-01-09_duplicate_detection.sql`) must be applied and keep the columns `duplicate_group_id`, `is_primary_in_group`, and `duplicate_confidence_score` available on `public.assignments`.
- The async detector (`TutorDexAggregator/duplicate_detector.py`) is invoked from `supabase_persist` when `DUPLICATE_DETECTION_ENABLED=true`. If you remove or rename the detector entrypoints or columns, API listing and broadcaster behavior will break silently.

Matching subject semantics (taxonomy v2):
- Backend matching prefers taxonomy v2 `subjects_canonical` when present in signals, and falls back to legacy subject labels.

Matching assignment type / tutor kind (not implemented yet):
- Tutor profiles store `assignment_types[]` (e.g. private vs tuition centre) and `tutor_kinds[]` (PT/FT/MOE/Ex-MOE). Assignments expose `tutor_types` and `rate_breakdown` at the assignment row level (populated from `meta.signals` when available); however, a fully reliable deterministic `type` signal for some scoring uses may still be incomplete for certain channels.
- Recommendation: only add this as a *soft boost* once a stable assignment-side type signal exists; avoid strict filtering to prevent false negatives.

### Contract D: click tracking RPC
- `public.increment_assignment_clicks(...)` must exist.
- Backend calls it via `SupabaseStore.increment_assignment_clicks`.

### Contract E: Firebase Auth token flow
- Website must be served from Firebase Hosting (or the Firebase Hosting emulator) so `/__/firebase/init.js` exists.
- Backend must either accept unauthenticated calls (dev) or successfully initialize Firebase Admin SDK (prod).

### Contract F: assignment rating schema (NEW 2026-01-09)
- The assignment rating migration (`TutorDexAggregator/supabase sqls/2026-01-09_assignment_ratings.sql`) must be applied when using adaptive thresholds.
- Required components:
  - `public.tutor_assignment_ratings` table with indexes
  - `public.user_preferences.desired_assignments_per_day` column
  - `public.calculate_tutor_rating_threshold(user_id, desired_per_day, lookback_days)` RPC function
- DM system (`TutorDexAggregator/dm_assignments.py`) depends on:
  - Backend rating calculation (`TutorDexBackend/assignment_rating.py`)
  - Supabase historical rate lookup (`SupabaseStore.get_tutor_avg_rate`)
  - Threshold RPC for adaptive filtering
- If the rating table or RPC is missing, DM system gracefully degrades to base score matching (no adaptive thresholds)

### Contract H: DM distance radius (NEW 2026-01-15)
- If you want distance-gated DMs, the DB must include `public.user_preferences.dm_max_distance_km` (default 5). Apply `TutorDexAggregator/supabase sqls/2026-01-15_add_dm_max_distance_km.sql` on existing DBs.

### Contract G: shared taxonomy and contracts
- The `shared/contracts/assignment_row.schema.json` must stay in sync with synced copies in Backend/Website
- CI enforces sync via `.github/workflows/contracts-validate.yml`
- Taxonomy v2 artifacts (`subjects_map_v2.json`, `subjects_enums_v2.json`) must be regenerated when `subjects_taxonomy_v2.json` changes
- CI enforces taxonomy sync via `.github/workflows/taxonomy-validate.yml`
- Breaking changes to taxonomy structure require updating:
  - Aggregator canonicalization logic (`TutorDexAggregator/taxonomy/canonicalize_subjects.py`)
  - Database taxonomy support tables (`TutorDexAggregator/supabase sqls/2026-01-03_subjects_taxonomy_v2.sql`)
  - Backend filter parameters
  - Website dropdown generation

---

## 11. Known Problems & Technical Debt

Blunt list based on observed code patterns:

1) Multiple “modes” / legacy paths exist
- There are older scripts and folders in `TutorDexAggregator/` that are not part of the compose default.
- This increases cognitive load and makes it easy to run the wrong entrypoint.

2) Supabase is a hard external dependency but not included in the repo
- Root compose assumes an external Docker network `supabase_default`.
- There is no pinned Supabase stack definition in this repo, which makes “new machine bootstrap” fragile.

3) Auth enforcement is optional and can fail open
- `firebase_auth.init_firebase_admin_if_needed` logs and returns false on misconfig, which may effectively disable auth if routes do not enforce it strictly.

4) Click tracking depends on a data join that is easy to break
- For full click tracking + broadcast editing, you must have:
  - `assignment_clicks` and `broadcast_messages` tables
  - Aggregator successfully calling `click_tracking_store.upsert_broadcast_message`
  - Backend configured with `TRACKING_EDIT_BOT_TOKEN` (must match posting bot)

5) Heuristic compilation detection
- Multi-assignment posts are skipped; this may throw away high-value data.

6) Taxonomy drift risk (mitigated, but needs discipline)
- Subjects taxonomy v2 is drift-guarded by CI (`shared/taxonomy/subjects/validate_taxonomy.py --check-sync`), but only if updates follow the process:
  - edit `shared/taxonomy/subjects/subjects_taxonomy_v2.json`
  - run `python3 shared/taxonomy/subjects/sync_taxonomy_artifacts.py`
  - validate in CI (or run locally) with `python3 shared/taxonomy/subjects/validate_taxonomy.py --check-sync`

---

## 12. Recently Implemented Refactors (2026-01)

This section tracks refactors that were previously suggested and have now been implemented.

2) Collapse and deprecate legacy aggregator entrypoints
- Operational modes are documented in `TutorDexAggregator/modes/MODES.md` and focus on `collector.py` + `workers/extract_worker.py`.

3) Formalize API contracts
- Shared schema: `shared/contracts/assignment_row.schema.json`
- Synced copies:
  - `TutorDexBackend/contracts/assignment_row.schema.json`
  - `TutorDexWebsite/src/generated/assignment_row.schema.json`

4) Tighten auth behavior in prod
- Backend fails fast in `APP_ENV=prod` if auth is required but Firebase Admin config is missing/unhealthy.

5) Add a “smoke test” command
- Windows cmd wrappers: `scripts/smoke_test_all.bat` (and `scripts/smoke_test_*.bat`)
- Python runner: `scripts/smoke_test.py` (can also be run directly)
- Checks:
  - Backend health endpoint
  - Redis connectivity
  - Supabase connectivity and required RPC functions
  - Treats HTTP 300+ as failure (important for PostgREST ambiguous RPC overloads)

---

End of document.
