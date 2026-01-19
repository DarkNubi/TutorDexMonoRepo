# Dual Environment Migration Plan — TutorDex

**Version:** 1.0  
**Date:** 2026-01-19  
**Status:** PRE-MIGRATION ANALYSIS (DO NOT EXECUTE)  
**Author:** Infrastructure Architect

---

## Executive Summary

This document provides an **execution-ready migration plan** for transitioning TutorDex from a single-environment deployment to a dual-environment (staging + production) setup on a single Windows host. The migration maintains **zero tolerance for accidental prod data corruption** while enabling safe testing and validation in a staging environment.

**Key Constraints:**
- Single physical Windows host
- Single Docker Engine instance
- Two isolated Docker Compose projects (staging + production)
- Separate PostgreSQL databases per environment (separate Supabase instances)
- Separate Redis instances per environment
- No branch-based environment separation (single `main` branch)
- Reverse proxy (Caddy) already exists for routing
- System is pre-launch but may contain real data

**Migration Strategy:**
- Use Docker Compose project naming (`-p` flag) for service isolation
- Environment-specific `.env` files (`.env.staging`, `.env.prod`)
- Prefixed volume names and networks per environment
- Port separation: staging on alternate ports, prod on standard ports
- Explicit environment variable (`APP_ENV=staging|prod`) for runtime safety
- Code-level prod protections prevent accidental cross-environment operations

---

## 1. Current State Analysis

### 1.1 Service Inventory

The TutorDex system consists of the following Docker Compose services:

#### Core Application Services (7)
1. **collector-tail** - Telegram message collector with automated catchup
   - Image: Built from `./TutorDexAggregator`
   - Command: `python collector.py live`
   - Dependencies: Supabase, Telegram API credentials
   - Metrics port: 9001
   - Stateful: Yes (Telegram session files)

2. **aggregator-worker** - Extraction queue worker (LLM + deterministic parsing)
   - Image: Built from `./TutorDexAggregator`
   - Command: `python workers/extract_worker.py`
   - Dependencies: Supabase, LLM API, collector-tail
   - Metrics port: 9002
   - Stateful: No (queue state in Supabase)

3. **backend** - FastAPI backend API server
   - Image: Built from `./TutorDexBackend`
   - Command: `uvicorn app:app --host 0.0.0.0 --port 8000`
   - Dependencies: Supabase, Redis, Firebase Auth
   - External port: 8000
   - Metrics port: 8000/metrics
   - Stateful: No (state in Supabase/Redis)

4. **telegram-link-bot** - Telegram link bot poller
   - Image: Built from `./TutorDexBackend`
   - Command: `python telegram_link_bot.py --poll-seconds 2`
   - Dependencies: Backend, Supabase
   - Stateful: Yes (offset file in volume)

5. **redis** - Redis 7 (Alpine) with persistence
   - Image: `redis:7-alpine`
   - Command: `redis-server --save 60 1 --appendonly yes`
   - Stateful: Yes (RDB + AOF persistence)
   - Volume: `redis_data:/data`

6. **freshness-tiers** - Assignment freshness tier updater (scheduled loop)
   - Image: Built from `./TutorDexAggregator`
   - Command: Shell loop calling `python update_freshness_tiers.py`
   - Dependencies: Supabase
   - Stateful: No

7. **tutorcity-fetch** - TutorCity API poller (scheduled loop)
   - Image: Built from `./TutorDexAggregator`
   - Command: Shell loop calling `python utilities/tutorcity_fetch.py`
   - Dependencies: Supabase, external TutorCity API
   - Stateful: No

#### Observability Services (8)
8. **prometheus** - Prometheus v2.50.1 (metrics collection + alerting)
   - Image: `prom/prometheus:v2.50.1`
   - External port: 9090
   - Volume: `prometheus_data:/prometheus`
   - Stateful: Yes (TSDB data)

9. **alertmanager** - Alertmanager v0.27.0 (alert routing)
   - Image: `prom/alertmanager:v0.27.0`
   - External port: 9093
   - Volume: `alertmanager_data:/alertmanager`
   - Stateful: Yes (alert state)

10. **alertmanager-telegram** - Custom Telegram alert webhook receiver
    - Image: Built from `./observability/alertmanager-telegram`
    - Dependencies: Telegram bot token

11. **grafana** - Grafana v12.3.1 (dashboards + visualization)
    - Image: `grafana/grafana:12.3.1`
    - External port: 3300
    - Volume: `grafana_data:/var/lib/grafana`
    - Stateful: Yes (dashboards, users, config)

12. **cadvisor** - cAdvisor v0.51.0 (container resource metrics)
    - Image: `gcr.io/cadvisor/cadvisor:v0.51.0`
    - Privileged: Yes
    - Stateful: No

13. **node-exporter** - Node Exporter v1.8.1 (host system metrics)
    - Image: `prom/node-exporter:v1.8.1`
    - Stateful: No

14. **blackbox-exporter** - Blackbox Exporter v0.25.0 (endpoint probing)
    - Image: `prom/blackbox-exporter:v0.25.0`
    - Stateful: No

15. **tempo** - Grafana Tempo (distributed tracing storage)
    - Image: `grafana/tempo:latest`
    - Ports: 3200 (HTTP), 4317 (OTLP gRPC), 4318 (OTLP HTTP)
    - Volume: `tempo_data:/tmp/tempo`
    - Stateful: Yes (trace data)

16. **otel-collector** - OpenTelemetry Collector
    - Image: `otel/opentelemetry-collector:latest`
    - Dependencies: Tempo
    - Stateful: No

### 1.2 Environment-Sensitive Components

#### 1.2.1 Databases
**Supabase (PostgreSQL + PostgREST)**
- **Connection:** External network `supabase_net` (named `supabase_default`)
- **Current State:** Single Supabase instance shared by all services
- **Tables:** `assignments`, `telegram_messages_raw`, `telegram_extractions`, `users`, `user_preferences`, `analytics_events`, etc.
- **Migration Need:** **CRITICAL** - Must have separate Supabase instances per environment
- **Risk:** Highest risk for prod data corruption

**Redis**
- **Connection:** Service name `redis` in Docker network
- **Current State:** Single Redis instance with named volume `redis_data`
- **Keys:** Tutor profiles (`tutordex:*`), rate limiting, link codes, click cooldowns
- **Migration Need:** **CRITICAL** - Must have separate Redis instances per environment
- **Risk:** High risk for cross-environment pollution

#### 1.2.2 Secrets & Credentials
**Current Secret Locations:**
1. **Telegram Credentials:**
   - `TELEGRAM_API_ID`, `TELEGRAM_API_HASH` (TutorDexAggregator/.env)
   - `SESSION_STRING` (session string for collector)
   - `GROUP_BOT_TOKEN`, `DM_BOT_TOKEN`, `ALERT_BOT_TOKEN` (bot tokens)

2. **Supabase Credentials:**
   - `SUPABASE_URL` (or `SUPABASE_URL_DOCKER`/`SUPABASE_URL_HOST`)
   - `SUPABASE_SERVICE_ROLE_KEY`

3. **Firebase Credentials:**
   - `FIREBASE_ADMIN_CREDENTIALS_PATH` → `/run/secrets/firebase-admin-service-account.json`
   - Host path: `./TutorDexBackend/secrets/firebase-admin-service-account.json`

4. **LLM API:**
   - `LLM_API_URL` (typically `http://host.docker.internal:1234` or localhost)

5. **Admin Keys:**
   - `ADMIN_API_KEY` (backend admin endpoints)
   - `BACKEND_API_KEY` (aggregator → backend authentication)

6. **Webhook Tokens:**
   - `WEBHOOK_SECRET_TOKEN`, `WEBHOOK_SECRET_TOKEN_DM`, `WEBHOOK_SECRET_TOKEN_GROUP`

**Migration Need:** All secrets must be **environment-specific** to prevent accidental cross-environment API calls.

#### 1.2.3 Telegram Bots & Channels
**Bot Instances:**
1. **Collector Bot** (SESSION_STRING) - Reads from Telegram channels
2. **Group Bot** (GROUP_BOT_TOKEN) - Broadcasts to aggregator channel
3. **DM Bot** (DM_BOT_TOKEN) - Sends DMs to matched tutors
4. **Alert Bot** (ALERT_BOT_TOKEN) - Sends monitoring alerts
5. **Link Bot** (TRACKING_EDIT_BOT_TOKEN or GROUP_BOT_TOKEN) - Handles Telegram link codes

**Channels:**
1. **Source Channels** (CHANNEL_LIST) - Channels to ingest from
2. **Aggregator Channel** (AGGREGATOR_CHANNEL_ID) - Where assignments are broadcast
3. **Skipped Messages Channel** (SKIPPED_MESSAGES_CHAT_ID) - Triage/debugging channel
4. **Alert Channel** (ALERT_CHAT_ID) - Monitoring alerts destination

**Migration Need:** 
- Staging should use **separate test bots and channels**
- Production bots/channels must be **explicitly configured to prevent staging→prod broadcasts**
- **DANGER:** Accidental broadcast from staging to prod channel would send test data to real tutors

#### 1.2.4 Schedulers & Background Workers
**Scheduled Services:**
1. **freshness-tiers** - Runs every `FRESHNESS_TIERS_INTERVAL_SECONDS` (default 3600s)
   - Updates assignment freshness tiers in database
   - Safe to run concurrently in staging/prod (separate databases)

2. **tutorcity-fetch** - Runs every `TUTORCITY_FETCH_INTERVAL_SECONDS` (default 300s)
   - Fetches assignments from external TutorCity API
   - **RISK:** Could pull duplicates if both envs fetch from same API simultaneously
   - **Mitigation:** Use environment-specific API keys or disable in staging

**Migration Need:**
- Schedulers are safe if databases are separated
- TutorCity fetch should be disabled in staging or use a test API endpoint

#### 1.2.5 Broadcasters & DM Senders
**Side-Effect Components (CRITICAL):**

1. **Broadcast System** (TutorDexAggregator/broadcast_assignments.py)
   - **Trigger:** `ENABLE_BROADCAST=true` in aggregator worker
   - **Target:** Telegram channel specified by `AGGREGATOR_CHANNEL_ID`
   - **Danger:** If staging uses prod channel ID, test assignments will be broadcast to real tutors
   - **Current Protection:** None (toggle is environment variable only)

2. **DM System** (TutorDexAggregator/dm_assignments.py)
   - **Trigger:** `ENABLE_DMS=true` in aggregator worker
   - **Target:** Tutor chat IDs from matching engine + Redis
   - **Danger:** If staging uses prod Redis/database, test DMs will be sent to real tutors
   - **Current Protection:** None (toggle is environment variable only)

3. **Click Tracking Edits** (TutorDexBackend/telegram_callback.py)
   - **Trigger:** Telegram webhook callbacks
   - **Target:** Updates message edit count in broadcast channel
   - **Danger:** Staging could edit prod broadcast messages if webhook misconfigured
   - **Current Protection:** None (webhook URL must be environment-specific)

**Migration Need:** **HIGHEST PRIORITY SAFETY CONTROLS**
- Add explicit `APP_ENV` checks before any Telegram API write operations
- Add startup validation that refuses to start with prod credentials in staging
- Add dry-run mode for staging to log actions without executing

### 1.3 Implicit/Missing Environment Awareness

**Current Issues:**
1. **No APP_ENV Enforcement:**
   - `APP_ENV` variable exists in config but is not checked before dangerous operations
   - Services don't validate that Supabase URL matches expected environment
   - No startup assertion: "if APP_ENV=prod, require all prod credentials"

2. **Volume Naming:**
   - Volumes use simple names (`redis_data`, `grafana_data`) without environment prefix
   - Multiple environments would share volumes unless explicitly separated

3. **Network Naming:**
   - Internal network is named `tutordex` (no environment prefix)
   - Would conflict if both environments run simultaneously

4. **Port Conflicts:**
   - All services expose same ports (8000 for backend, 9090 for Prometheus, etc.)
   - Cannot run both environments simultaneously without port remapping

5. **Hardcoded Service Names:**
   - Services reference each other by name (`redis`, `backend`, `prometheus`)
   - Docker Compose project naming will handle this automatically

6. **External Supabase Network:**
   - Current setup expects external network `supabase_default`
   - Each environment must connect to its own Supabase instance's network


---

## 2. Target State Architecture

### 2.1 Environment Isolation Boundaries

**Staging Environment:**
- **Purpose:** Safe testing, development validation, schema migrations
- **Data:** Test data only, can be reset/destroyed
- **External APIs:** Test bots, test channels, staging Supabase
- **Port Mapping:** Alternate ports (8001, 9091, 3301, etc.)
- **Docker Project Name:** `tutordex-staging`
- **Volume Prefix:** `staging_`
- **Network Name:** `tutordex-staging`

**Production Environment:**
- **Purpose:** Live service for real tutors and assignments
- **Data:** Real tutor profiles, assignments, analytics (must be protected)
- **External APIs:** Production bots, production channels, production Supabase
- **Port Mapping:** Standard ports (8000, 9090, 3300, etc.)
- **Docker Project Name:** `tutordex-prod`
- **Volume Prefix:** `prod_`
- **Network Name:** `tutordex-prod`

### 2.2 Docker Compose Project Separation Strategy

**Key Principle:** Use Docker Compose's built-in project isolation (`-p` flag) to namespace all resources.

**Implementation:**
```bash
# Staging
docker compose -f docker-compose.yml -p tutordex-staging --env-file .env.staging up -d

# Production
docker compose -f docker-compose.yml -p tutordex-prod --env-file .env.prod up -d
```

**Automatic Isolation:**
- **Service Names:** `tutordex-staging-backend-1`, `tutordex-prod-backend-1`
- **Network Names:** `tutordex-staging` (auto-created), `tutordex-prod` (auto-created)
- **Volume Names:** `tutordex-staging_redis_data`, `tutordex-prod_redis_data` (auto-prefixed)

**Shared Resources:**
- None. Each environment is completely isolated.
- Exception: Host directories (logs, secrets) must use environment-specific paths.

### 2.3 Database Separation Strategy

#### Supabase (PostgreSQL)

**Requirement:** Separate Supabase instance per environment.

**Options:**

**Option A: Separate Supabase Projects (Recommended for Production)**
- Run two separate Supabase Docker Compose stacks
- Completely isolated databases, auth, storage, APIs
- Each gets its own external network (`supabase_staging_default`, `supabase_prod_default`)
- **Pros:** Complete isolation, separate backups, no risk of cross-contamination
- **Cons:** Higher resource usage (2x PostgreSQL instances)

**Option B: Single Supabase with Separate Databases**
- One Supabase instance, two PostgreSQL databases (`tutordex_staging`, `tutordex_prod`)
- Use database-level isolation via connection strings
- **Pros:** Lower resource usage
- **Cons:** Shared auth system, higher risk of misconfiguration

**Recommendation: Option A** for safety. Resource cost on modern hardware is acceptable.

**Migration Steps:**
1. Deploy second Supabase instance for staging
2. Run schema migrations on staging database
3. Populate staging with test data (do NOT copy prod data initially)
4. Validate all services connect to correct Supabase instance

#### Redis Separation

**Strategy:** Separate Redis container per environment (via Docker Compose project naming).

**Automatic Isolation:**
- Service name in docker-compose.yml: `redis`
- Staging container name: `tutordex-staging-redis-1`
- Production container name: `tutordex-prod-redis-1`
- Staging volume: `tutordex-staging_redis_data`
- Production volume: `tutordex-prod_redis_data`

**No Code Changes Needed:** Services reference `redis://redis:6379/0` which resolves within their project's network.

**Key Prefix Validation:** Although Redis instances are separate, maintain `REDIS_PREFIX` for clarity:
- Staging: `REDIS_PREFIX=tutordex-staging:`
- Production: `REDIS_PREFIX=tutordex:` (or `tutordex-prod:`)

### 2.4 Secrets Strategy

**Directory Structure:**
```
TutorDexAggregator/
  .env.staging          # Staging secrets
  .env.prod            # Production secrets
  .env.example         # Template (no secrets)

TutorDexBackend/
  .env.staging          # Staging secrets
  .env.prod            # Production secrets
  .env.example         # Template
  secrets/
    firebase-admin-staging.json
    firebase-admin-prod.json

TutorDexWebsite/
  .env.staging          # Staging Firebase config
  .env.prod            # Production Firebase config
  .env.example         # Template
```

**Git Exclusions (already in .gitignore):**
- `.env` (legacy single-environment file)
- `.env.staging`
- `.env.prod`
- `secrets/*.json`

**Deployment Strategy:**
1. Store secrets in environment-specific files on the Windows host
2. Mount appropriate file based on compose invocation
3. Use wrapper scripts to ensure correct env file is selected

**Critical Requirement:** Never copy prod secrets to staging. Generate separate test credentials for:
- Telegram test bots
- Staging Supabase credentials
- Separate Firebase project or test service account
- Separate admin API keys

### 2.5 Port Allocation

| Service | Staging Port | Production Port |
|---------|-------------|-----------------|
| Backend API | 8001 | 8000 |
| Prometheus | 9091 | 9090 |
| Alertmanager | 9094 | 9093 |
| Grafana | 3301 | 3300 |
| Tempo HTTP | 3201 | 3200 |
| Tempo OTLP gRPC | 4319 | 4317 |
| Tempo OTLP HTTP | 4320 | 4318 |

**Caddy Reverse Proxy Routing:**
```
# Production
tutordex.yourdomain.com → localhost:8000

# Staging
staging.tutordex.yourdomain.com → localhost:8001
```

**Internal Ports (no change needed):**
- Redis: 6379 (isolated by network)
- Collector metrics: 9001
- Worker metrics: 9002


---

## 3. Required File-Level Changes

### 3.1 Docker Compose Configuration

**File:** `docker-compose.yml`

**Change 1: Add Environment Variable for APP_ENV**

Add to each application service's `environment` section:

```yaml
# Example for backend service
backend:
  build: ./TutorDexBackend
  env_file:
    - ./TutorDexBackend/.env  # Will be overridden by --env-file flag
  environment:
    APP_ENV: "${APP_ENV:-dev}"  # REQUIRED: Must be set to staging|prod
    LOG_JSON: "true"
    # ... rest of environment vars
```

Apply to services:
- `collector-tail`
- `aggregator-worker`
- `backend`
- `telegram-link-bot`
- `freshness-tiers`
- `tutorcity-fetch`

**Change 2: Parameterize External Ports**

Replace hardcoded ports with environment variables:

```yaml
backend:
  ports:
    - "${BACKEND_PORT:-8000}:8000"

prometheus:
  ports:
    - "${PROMETHEUS_PORT:-9090}:9090"

alertmanager:
  ports:
    - "${ALERTMANAGER_PORT:-9093}:9093"

grafana:
  ports:
    - "${GRAFANA_PORT:-3300}:3000"

tempo:
  ports:
    - "${TEMPO_HTTP_PORT:-3200}:3200"
    - "${TEMPO_OTLP_GRPC_PORT:-4317}:4317"
    - "${TEMPO_OTLP_HTTP_PORT:-4318}:4318"
```

**Change 3: Remove Hardcoded Network Names**

Current:
```yaml
networks:
  tutordex:
    name: tutordex  # REMOVE THIS LINE

  supabase_net:
    external: true
    name: supabase_default  # MUST BE PARAMETERIZED
```

Updated:
```yaml
networks:
  tutordex:
    # name is auto-generated: ${COMPOSE_PROJECT_NAME}_tutordex
    # e.g., tutordex-staging_tutordex or tutordex-prod_tutordex

  supabase_net:
    external: true
    name: ${SUPABASE_NETWORK:-supabase_default}
```

**Change 4: Parameterize Grafana Admin Credentials**

Already parameterized in current file (no change needed):
```yaml
grafana:
  environment:
    GF_SECURITY_ADMIN_USER: "${GRAFANA_ADMIN_USER:-admin}"
    GF_SECURITY_ADMIN_PASSWORD: "${GRAFANA_ADMIN_PASSWORD:-admin}"
```

**Change 5: Add OTEL Environment Label**

Update:
```yaml
otel-collector:
  environment:
    ENVIRONMENT: ${APP_ENV:-production}  # Use APP_ENV consistently
```

### 3.2 Environment Files

**File:** `.env.staging` (CREATE NEW)

```bash
# =============================================================================
# STAGING ENVIRONMENT CONFIGURATION
# =============================================================================
# CRITICAL: This file contains STAGING credentials only.
# NEVER copy production secrets to this file.
# =============================================================================

# ----------------------------------------------------------------------------
# ENVIRONMENT IDENTIFICATION (MANDATORY)
# ----------------------------------------------------------------------------
APP_ENV=staging
COMPOSE_PROJECT_NAME=tutordex-staging

# ----------------------------------------------------------------------------
# PORT ALLOCATIONS (STAGING)
# ----------------------------------------------------------------------------
BACKEND_PORT=8001
PROMETHEUS_PORT=9091
ALERTMANAGER_PORT=9094
GRAFANA_PORT=3301
TEMPO_HTTP_PORT=3201
TEMPO_OTLP_GRPC_PORT=4319
TEMPO_OTLP_HTTP_PORT=4320

# ----------------------------------------------------------------------------
# SUPABASE (STAGING INSTANCE)
# ----------------------------------------------------------------------------
SUPABASE_URL_DOCKER=http://supabase-kong-staging:8000
SUPABASE_URL_HOST=http://localhost:54322  # Staging Supabase port
SUPABASE_URL=http://localhost:54322
SUPABASE_SERVICE_ROLE_KEY=<STAGING_SERVICE_ROLE_KEY>
SUPABASE_KEY=<STAGING_ANON_KEY>
SUPABASE_ENABLED=true
SUPABASE_RAW_ENABLED=true
SUPABASE_NETWORK=supabase_staging_default

# ----------------------------------------------------------------------------
# REDIS (ISOLATED BY DOCKER NETWORK)
# ----------------------------------------------------------------------------
REDIS_URL=redis://redis:6379/0
REDIS_PREFIX=tutordex-staging:

# ----------------------------------------------------------------------------
# TELEGRAM (STAGING BOTS AND CHANNELS)
# ----------------------------------------------------------------------------
TELEGRAM_API_ID=<SAME_AS_PROD_OR_SEPARATE>
TELEGRAM_API_HASH=<SAME_AS_PROD_OR_SEPARATE>
SESSION_STRING=<STAGING_SESSION_STRING>
GROUP_BOT_TOKEN=<STAGING_BOT_TOKEN>
DM_BOT_TOKEN=<STAGING_DM_BOT_TOKEN>
ALERT_BOT_TOKEN=<STAGING_ALERT_BOT_TOKEN>
TRACKING_EDIT_BOT_TOKEN=<STAGING_EDIT_BOT_TOKEN>

# STAGING CHANNELS (MUST BE DIFFERENT FROM PROD)
AGGREGATOR_CHANNEL_ID=<STAGING_CHANNEL_ID>
CHANNEL_LIST=<STAGING_SOURCE_CHANNELS>
SKIPPED_MESSAGES_CHAT_ID=<STAGING_TRIAGE_CHANNEL>
ALERT_CHAT_ID=<STAGING_ALERT_CHANNEL>

# ----------------------------------------------------------------------------
# SIDE-EFFECT CONTROLS (STAGING)
# ----------------------------------------------------------------------------
# IMPORTANT: Disable or carefully control side effects in staging
ENABLE_BROADCAST=false  # DO NOT broadcast from staging by default
ENABLE_DMS=false        # DO NOT send DMs from staging by default
ENABLE_BROADCAST_TRACKING=false

# ----------------------------------------------------------------------------
# FIREBASE (STAGING PROJECT OR TEST SERVICE ACCOUNT)
# ----------------------------------------------------------------------------
FIREBASE_ADMIN_ENABLED=true
FIREBASE_ADMIN_CREDENTIALS_PATH=/run/secrets/firebase-admin-service-account.json
# Host mount: ./TutorDexBackend/secrets/firebase-admin-staging.json

# ----------------------------------------------------------------------------
# LLM (SHARED OR STAGING-SPECIFIC)
# ----------------------------------------------------------------------------
LLM_API_URL=http://host.docker.internal:1234
LLM_MODEL_NAME=lfm2-8b-a1b

# ----------------------------------------------------------------------------
# ADMIN KEYS (STAGING-SPECIFIC)
# ----------------------------------------------------------------------------
ADMIN_API_KEY=<STAGING_ADMIN_KEY>
BACKEND_API_KEY=<STAGING_BACKEND_KEY>

# ----------------------------------------------------------------------------
# OBSERVABILITY
# ----------------------------------------------------------------------------
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=<STAGING_GRAFANA_PASSWORD>
SENTRY_DSN=<STAGING_SENTRY_DSN>
SENTRY_ENVIRONMENT=staging
OTEL_ENABLED=1

# ----------------------------------------------------------------------------
# EXTRACTION PIPELINE
# ----------------------------------------------------------------------------
EXTRACTION_PIPELINE_VERSION=2026-01-02_det_time_v1
SCHEMA_VERSION=2026-01-01
```

**File:** `.env.prod` (CREATE NEW)

```bash
# =============================================================================
# PRODUCTION ENVIRONMENT CONFIGURATION
# =============================================================================
# CRITICAL: This file contains PRODUCTION credentials.
# Handle with extreme care. Never commit to git.
# =============================================================================

# ----------------------------------------------------------------------------
# ENVIRONMENT IDENTIFICATION (MANDATORY)
# ----------------------------------------------------------------------------
APP_ENV=prod
COMPOSE_PROJECT_NAME=tutordex-prod

# ----------------------------------------------------------------------------
# PORT ALLOCATIONS (PRODUCTION)
# ----------------------------------------------------------------------------
BACKEND_PORT=8000
PROMETHEUS_PORT=9090
ALERTMANAGER_PORT=9093
GRAFANA_PORT=3300
TEMPO_HTTP_PORT=3200
TEMPO_OTLP_GRPC_PORT=4317
TEMPO_OTLP_HTTP_PORT=4318

# ----------------------------------------------------------------------------
# SUPABASE (PRODUCTION INSTANCE)
# ----------------------------------------------------------------------------
SUPABASE_URL_DOCKER=http://supabase-kong:8000
SUPABASE_URL_HOST=http://localhost:54321  # Production Supabase port
SUPABASE_URL=http://localhost:54321
SUPABASE_SERVICE_ROLE_KEY=<PROD_SERVICE_ROLE_KEY>
SUPABASE_KEY=<PROD_ANON_KEY>
SUPABASE_ENABLED=true
SUPABASE_RAW_ENABLED=true
SUPABASE_NETWORK=supabase_default

# ----------------------------------------------------------------------------
# REDIS (ISOLATED BY DOCKER NETWORK)
# ----------------------------------------------------------------------------
REDIS_URL=redis://redis:6379/0
REDIS_PREFIX=tutordex:

# ----------------------------------------------------------------------------
# TELEGRAM (PRODUCTION BOTS AND CHANNELS)
# ----------------------------------------------------------------------------
TELEGRAM_API_ID=<PROD_API_ID>
TELEGRAM_API_HASH=<PROD_API_HASH>
SESSION_STRING=<PROD_SESSION_STRING>
GROUP_BOT_TOKEN=<PROD_BOT_TOKEN>
DM_BOT_TOKEN=<PROD_DM_BOT_TOKEN>
ALERT_BOT_TOKEN=<PROD_ALERT_BOT_TOKEN>
TRACKING_EDIT_BOT_TOKEN=<PROD_EDIT_BOT_TOKEN>

# PRODUCTION CHANNELS
AGGREGATOR_CHANNEL_ID=<PROD_CHANNEL_ID>
CHANNEL_LIST=<PROD_SOURCE_CHANNELS>
SKIPPED_MESSAGES_CHAT_ID=<PROD_TRIAGE_CHANNEL>
ALERT_CHAT_ID=<PROD_ALERT_CHANNEL>

# ----------------------------------------------------------------------------
# SIDE-EFFECT CONTROLS (PRODUCTION)
# ----------------------------------------------------------------------------
ENABLE_BROADCAST=true
ENABLE_DMS=true
ENABLE_BROADCAST_TRACKING=true

# ----------------------------------------------------------------------------
# FIREBASE (PRODUCTION PROJECT)
# ----------------------------------------------------------------------------
FIREBASE_ADMIN_ENABLED=true
FIREBASE_ADMIN_CREDENTIALS_PATH=/run/secrets/firebase-admin-service-account.json
# Host mount: ./TutorDexBackend/secrets/firebase-admin-prod.json

# ----------------------------------------------------------------------------
# LLM (PRODUCTION)
# ----------------------------------------------------------------------------
LLM_API_URL=http://host.docker.internal:1234
LLM_MODEL_NAME=lfm2-8b-a1b

# ----------------------------------------------------------------------------
# ADMIN KEYS (PRODUCTION-SPECIFIC)
# ----------------------------------------------------------------------------
ADMIN_API_KEY=<PROD_ADMIN_KEY>
BACKEND_API_KEY=<PROD_BACKEND_KEY>
AUTH_REQUIRED=true

# ----------------------------------------------------------------------------
# OBSERVABILITY
# ----------------------------------------------------------------------------
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=<PROD_GRAFANA_PASSWORD>
SENTRY_DSN=<PROD_SENTRY_DSN>
SENTRY_ENVIRONMENT=production
OTEL_ENABLED=1

# ----------------------------------------------------------------------------
# EXTRACTION PIPELINE
# ----------------------------------------------------------------------------
EXTRACTION_PIPELINE_VERSION=2026-01-02_det_time_v1
SCHEMA_VERSION=2026-01-01
```

### 3.3 Deployment Scripts

**File:** `scripts/deploy_staging.sh` (CREATE NEW)

```bash
#!/bin/bash
set -euo pipefail

echo "=== Deploying TutorDex STAGING ==="

# Change to repo root
cd "$(dirname "$0")/.."

# Validate environment file exists
if [ ! -f .env.staging ]; then
    echo "ERROR: .env.staging not found"
    exit 1
fi

# Pull latest images (optional, for base images)
docker compose -p tutordex-staging pull prometheus alertmanager grafana redis tempo otel-collector || true

# Build and start services
docker compose \
    -f docker-compose.yml \
    -p tutordex-staging \
    --env-file .env.staging \
    up -d --build

echo "Staging deployment complete."
echo "Backend: http://localhost:8001"
echo "Grafana: http://localhost:3301"
echo "Prometheus: http://localhost:9091"
```

**File:** `scripts/deploy_prod.sh` (CREATE NEW)

```bash
#!/bin/bash
set -euo pipefail

echo "=== Deploying TutorDex PRODUCTION ==="
echo "WARNING: This will restart production services."
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Deployment cancelled."
    exit 0
fi

# Change to repo root
cd "$(dirname "$0")/.."

# Validate environment file exists
if [ ! -f .env.prod ]; then
    echo "ERROR: .env.prod not found"
    exit 1
fi

# Pull latest images
docker compose -p tutordex-prod pull prometheus alertmanager grafana redis tempo otel-collector || true

# Build and start services
docker compose \
    -f docker-compose.yml \
    -p tutordex-prod \
    --env-file .env.prod \
    up -d --build

echo "Production deployment complete."
echo "Backend: http://localhost:8000"
echo "Grafana: http://localhost:3300"
echo "Prometheus: http://localhost:9090"
```

**File:** `scripts/stop_staging.sh` (CREATE NEW)

```bash
#!/bin/bash
set -euo pipefail

echo "=== Stopping TutorDex STAGING ==="

cd "$(dirname "$0")/.."

docker compose \
    -f docker-compose.yml \
    -p tutordex-staging \
    --env-file .env.staging \
    down

echo "Staging stopped."
```

**File:** `scripts/stop_prod.sh` (CREATE NEW)

```bash
#!/bin/bash
set -euo pipefail

echo "=== Stopping TutorDex PRODUCTION ==="
echo "WARNING: This will stop production services."
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Operation cancelled."
    exit 0
fi

cd "$(dirname "$0")/.."

docker compose \
    -f docker-compose.yml \
    -p tutordex-prod \
    --env-file .env.prod \
    down

echo "Production stopped."
```

**File:** `scripts/logs_staging.sh` (CREATE NEW)

```bash
#!/bin/bash
cd "$(dirname "$0")/.."
docker compose -p tutordex-staging logs -f "$@"
```

**File:** `scripts/logs_prod.sh` (CREATE NEW)

```bash
#!/bin/bash
cd "$(dirname "$0")/.."
docker compose -p tutordex-prod logs -f "$@"
```

Make all scripts executable:
```bash
chmod +x scripts/deploy_*.sh scripts/stop_*.sh scripts/logs_*.sh
```

### 3.4 Code Changes for Safety Guardrails

**File:** `shared/config.py`

Add validation method:

```python
def validate_environment_integrity(cfg: BaseSettings) -> None:
    """
    Validate that environment configuration is internally consistent.
    
    Raises RuntimeError if dangerous misconfigurations detected.
    """
    app_env = str(getattr(cfg, "app_env", "dev")).strip().lower()
    
    if app_env in {"prod", "production"}:
        # Production environment checks
        supabase_url = str(getattr(cfg, "supabase_url", "") or "").strip()
        
        # Example validation: prod should not use :54322 (staging supabase port)
        if ":54322" in supabase_url:
            raise RuntimeError(
                f"FATAL: APP_ENV=prod but SUPABASE_URL contains staging port :54322. "
                f"This would corrupt staging data. Fix .env.prod configuration."
            )
        
        # Validate critical prod settings
        if not getattr(cfg, "auth_required", True):
            raise RuntimeError("AUTH_REQUIRED must be true in production")
        
        if not getattr(cfg, "firebase_admin_enabled", False):
            raise RuntimeError("FIREBASE_ADMIN_ENABLED must be true in production")
    
    elif app_env == "staging":
        # Staging environment checks
        supabase_url = str(getattr(cfg, "supabase_url", "") or "").strip()
        
        # Example: staging should not use :54321 (prod supabase port)
        if ":54321" in supabase_url:
            raise RuntimeError(
                f"FATAL: APP_ENV=staging but SUPABASE_URL contains production port :54321. "
                f"This would corrupt production data. Fix .env.staging configuration."
            )
```

Call this function at startup in:
- `TutorDexAggregator/collector.py`
- `TutorDexAggregator/workers/extract_worker_main.py`
- `TutorDexBackend/app.py`

**File:** `TutorDexBackend/app.py`

Add to startup event:

```python
from shared.config import validate_environment_integrity, load_backend_config

@app.on_event("startup")
async def _startup_log() -> None:
    cfg = load_backend_config()
    validate_environment_integrity(cfg)  # ADD THIS LINE
    
    auth_service.validate_production_config()
    logger.info(
        "startup",
        extra={
            "auth_required": auth_service.is_auth_required(),
            "app_env": getattr(cfg, "app_env", None),
            "supabase_enabled": sb.enabled(),
            "redis_prefix": getattr(getattr(store, "cfg", None), "prefix", None),
        },
    )
```

**File:** `TutorDexAggregator/delivery/broadcast_client.py`

Add production check before broadcasting:

```python
def _check_production_broadcast_safety(cfg) -> None:
    """Validate broadcast targets are appropriate for environment."""
    app_env = str(getattr(cfg, "app_env", "dev")).strip().lower()
    channel_id = str(getattr(cfg, "aggregator_channel_id", "") or "").strip()
    
    # Example: ensure staging doesn't broadcast to prod channel
    # (Requires maintaining a list of known prod channel IDs or convention)
    if app_env == "staging" and channel_id and not channel_id.endswith("_test"):
        logger.warning(
            "broadcast_env_check",
            extra={
                "app_env": app_env,
                "channel_id": channel_id,
                "message": "Staging environment broadcasting to non-test channel. Verify configuration."
            }
        )

def send_broadcast(assignment_data: Dict, cfg) -> bool:
    """Send broadcast with environment safety check."""
    _check_production_broadcast_safety(cfg)
    # ... existing broadcast logic
```

**File:** `TutorDexAggregator/dm_assignments_impl.py`

Add similar check:

```python
def _check_production_dm_safety(cfg) -> None:
    """Validate DM configuration is appropriate for environment."""
    app_env = str(getattr(cfg, "app_env", "dev")).strip().lower()
    
    if app_env == "staging":
        logger.warning(
            "dm_env_check",
            extra={
                "app_env": app_env,
                "message": "Staging environment sending DMs. Verify recipients are test accounts."
            }
        )

def send_dms(assignment_data: Dict, cfg) -> None:
    """Send DMs with environment safety check."""
    _check_production_dm_safety(cfg)
    # ... existing DM logic
```

### 3.5 GitHub Actions Workflow Updates

**File:** `.github/workflows/deploy.yml`

Update to support environment-specific deployments:

```yaml
name: Deploy via Tailscale + OpenSSH

on:
  push:
    branches: ["main"]

jobs:
  deploy-production:
    runs-on: ubuntu-latest
    environment: production  # Requires manual approval in GitHub

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Connect to Tailscale
        uses: tailscale/github-action@v4
        with:
          authkey: ${{ secrets.TAILSCALE_AUTHKEY }}

      - name: Setup SSH
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.SERVER_SSH_KEY }}" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          ssh-keyscan -H ${{ secrets.SERVER_TS_IP }} >> ~/.ssh/known_hosts

      - name: Deploy to Production
        run: |
          ssh -i ~/.ssh/id_ed25519 \
              -o IdentitiesOnly=yes \
              "${{ secrets.SERVER_USER }}@${{ secrets.SERVER_TS_IP }}" << 'EOF'
   
            cd /d D:/TutorDex
            
            # Pull latest code
            git pull origin main
            
            # Deploy production
            ./scripts/deploy_prod.sh
          EOF

  deploy-staging:
    runs-on: ubuntu-latest
    environment: staging  # Optional: can auto-deploy to staging

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Connect to Tailscale
        uses: tailscale/github-action@v4
        with:
          authkey: ${{ secrets.TAILSCALE_AUTHKEY }}

      - name: Setup SSH
        run: |
          mkdir -p ~/.ssh
          echo "${{ secrets.SERVER_SSH_KEY }}" > ~/.ssh/id_ed25519
          chmod 600 ~/.ssh/id_ed25519
          ssh-keyscan -H ${{ secrets.SERVER_TS_IP }} >> ~/.ssh/known_hosts

      - name: Deploy to Staging
        run: |
          ssh -i ~/.ssh/id_ed25519 \
              -o IdentitiesOnly=yes \
              "${{ secrets.SERVER_USER }}@${{ secrets.SERVER_TS_IP }}" << 'EOF'
   
            cd /d D:/TutorDex
            
            # Pull latest code
            git pull origin main
            
            # Deploy staging
            ./scripts/deploy_staging.sh
          EOF
```


---

## 4. Environment Variable Contract

### 4.1 Shared Variables (Same in Both Environments)

| Variable | Purpose | Notes |
|----------|---------|-------|
| `EXTRACTION_PIPELINE_VERSION` | Pipeline version for extraction queue | Keep in sync for consistency |
| `SCHEMA_VERSION` | Assignment JSON schema version | Keep in sync for compatibility |
| `LLM_MODEL_NAME` | LLM model identifier | Can differ if testing new models in staging |
| `LOG_LEVEL` | Logging verbosity | Typically `INFO` in both |
| `LOG_JSON` | JSON logging format | `true` in both for observability |
| `OTEL_ENABLED` | Enable OpenTelemetry tracing | `1` in both for consistency |

### 4.2 Staging-Only Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `APP_ENV` | `staging` | **MANDATORY** environment identifier |
| `COMPOSE_PROJECT_NAME` | `tutordex-staging` | Docker Compose project namespace |
| `BACKEND_PORT` | `8001` | Alternate port to avoid conflicts |
| `PROMETHEUS_PORT` | `9091` | Alternate port |
| `ALERTMANAGER_PORT` | `9094` | Alternate port |
| `GRAFANA_PORT` | `3301` | Alternate port |
| `TEMPO_HTTP_PORT` | `3201` | Alternate port |
| `SUPABASE_URL` | Staging Supabase instance | **CRITICAL** - must be staging |
| `SUPABASE_SERVICE_ROLE_KEY` | Staging credentials | **CRITICAL** - never use prod key |
| `REDIS_PREFIX` | `tutordex-staging:` | Namespace (though Redis is isolated) |
| `ENABLE_BROADCAST` | `false` (default) | **DANGER** - disable unless testing |
| `ENABLE_DMS` | `false` (default) | **DANGER** - disable unless testing |
| `GROUP_BOT_TOKEN` | Staging bot token | Test bot only |
| `DM_BOT_TOKEN` | Staging DM bot token | Test bot only |
| `AGGREGATOR_CHANNEL_ID` | Staging channel ID | Test channel only |
| `CHANNEL_LIST` | Staging source channels | Test channels only |
| `FIREBASE_ADMIN_CREDENTIALS_PATH` | `firebase-admin-staging.json` | Staging service account |
| `SENTRY_DSN` | Staging Sentry project | Separate error tracking |
| `SENTRY_ENVIRONMENT` | `staging` | Label for Sentry events |

### 4.3 Production-Only Variables

| Variable | Value | Purpose |
|----------|-------|---------|
| `APP_ENV` | `prod` | **MANDATORY** environment identifier |
| `COMPOSE_PROJECT_NAME` | `tutordex-prod` | Docker Compose project namespace |
| `BACKEND_PORT` | `8000` | Standard production port |
| `PROMETHEUS_PORT` | `9090` | Standard port |
| `ALERTMANAGER_PORT` | `9093` | Standard port |
| `GRAFANA_PORT` | `3300` | Standard port |
| `TEMPO_HTTP_PORT` | `3200` | Standard port |
| `SUPABASE_URL` | Production Supabase instance | **CRITICAL** - must be prod |
| `SUPABASE_SERVICE_ROLE_KEY` | Production credentials | **CRITICAL** - never share with staging |
| `REDIS_PREFIX` | `tutordex:` | Production namespace |
| `ENABLE_BROADCAST` | `true` | Enable live broadcasting |
| `ENABLE_DMS` | `true` | Enable live DM delivery |
| `GROUP_BOT_TOKEN` | Production bot token | Live bot |
| `DM_BOT_TOKEN` | Production DM bot token | Live bot |
| `AGGREGATOR_CHANNEL_ID` | Production channel ID | Live channel |
| `CHANNEL_LIST` | Production source channels | Live channels |
| `FIREBASE_ADMIN_CREDENTIALS_PATH` | `firebase-admin-prod.json` | Production service account |
| `AUTH_REQUIRED` | `true` | **MANDATORY** in production |
| `ADMIN_API_KEY` | Production admin key | **MANDATORY** in production |
| `SENTRY_DSN` | Production Sentry project | Production error tracking |
| `SENTRY_ENVIRONMENT` | `production` | Label for Sentry events |

### 4.4 Dangerous Variables (Require Extra Caution)

| Variable | Risk | Mitigation |
|----------|------|------------|
| `ENABLE_BROADCAST` | Staging could broadcast to prod channel | Code-level env check, default `false` in staging |
| `ENABLE_DMS` | Staging could DM real tutors | Code-level env check, default `false` in staging |
| `AGGREGATOR_CHANNEL_ID` | Wrong channel ID = messages to wrong audience | Validate at startup, use naming convention (e.g., `_test` suffix) |
| `SUPABASE_URL` | Wrong URL = data in wrong database | Startup validation (port check), clear naming |
| `SUPABASE_SERVICE_ROLE_KEY` | Wrong key = access to wrong database | Never copy prod key to staging env file |
| `GROUP_BOT_TOKEN` | Wrong token = bot operates in wrong context | Use separate bots for staging/prod |
| `DM_BOT_TOKEN` | Wrong token = DMs from wrong bot | Use separate bots for staging/prod |
| `REDIS_PREFIX` | Low risk (isolated by network) | Still use distinct prefixes for clarity |

### 4.5 Environment Variable Validation Checklist

Before starting any environment, validate:

**Staging Checklist:**
- [ ] `APP_ENV=staging`
- [ ] `SUPABASE_URL` contains staging port (`:54322`) or staging host
- [ ] `AGGREGATOR_CHANNEL_ID` is a test channel (not prod)
- [ ] `GROUP_BOT_TOKEN` is a test bot token
- [ ] `DM_BOT_TOKEN` is a test bot token (or empty)
- [ ] `ENABLE_BROADCAST=false` (unless actively testing)
- [ ] `ENABLE_DMS=false` (unless actively testing)
- [ ] `BACKEND_PORT=8001` (or other non-8000 port)

**Production Checklist:**
- [ ] `APP_ENV=prod`
- [ ] `SUPABASE_URL` contains production port (`:54321`) or production host
- [ ] `AGGREGATOR_CHANNEL_ID` is the live production channel
- [ ] `GROUP_BOT_TOKEN` is the production bot token
- [ ] `DM_BOT_TOKEN` is the production DM bot token
- [ ] `AUTH_REQUIRED=true`
- [ ] `ADMIN_API_KEY` is set and secret
- [ ] `BACKEND_PORT=8000`


---

## 5. Docker & Deployment Changes

### 5.1 Required docker-compose.yml Modifications

**Summary of Changes:**

1. ✅ Add `APP_ENV` environment variable to all application services
2. ✅ Parameterize external port mappings with environment variables
3. ✅ Remove hardcoded network name from `tutordex` network (allow auto-naming)
4. ✅ Parameterize `supabase_net` external network name
5. ✅ Ensure `OTEL_COLLECTOR` uses `APP_ENV` consistently

**Minimal Diff Preview:**

```diff
diff --git a/docker-compose.yml b/docker-compose.yml
index original..modified
@@ services:
   aggregator-worker:
     environment:
+      APP_ENV: "${APP_ENV:-dev}"
       LOG_JSON: "true"
       
   collector-tail:
     environment:
+      APP_ENV: "${APP_ENV:-dev}"
       LOG_JSON: "true"
       
   backend:
     ports:
-      - "0.0.0.0:8000:8000"
+      - "0.0.0.0:${BACKEND_PORT:-8000}:8000"
     environment:
+      APP_ENV: "${APP_ENV:-dev}"
       LOG_JSON: "true"
       
   telegram-link-bot:
     environment:
+      APP_ENV: "${APP_ENV:-dev}"
       LOG_JSON: "true"
       
   prometheus:
     ports:
-      - "0.0.0.0:${PROMETHEUS_PORT:-9090}:9090"
+      - "0.0.0.0:${PROMETHEUS_PORT:-9090}:9090"  # Already parameterized
       
   grafana:
     ports:
-      - "0.0.0.0:${GRAFANA_PORT:-3300}:3000"
+      - "0.0.0.0:${GRAFANA_PORT:-3300}:3000"  # Already parameterized
       
   tempo:
     ports:
-      - "3200:3200"
-      - "4317:4317"
-      - "4318:4318"
+      - "${TEMPO_HTTP_PORT:-3200}:3200"
+      - "${TEMPO_OTLP_GRPC_PORT:-4317}:4317"
+      - "${TEMPO_OTLP_HTTP_PORT:-4318}:4318"
       
   otel-collector:
     environment:
-      ENVIRONMENT: ${APP_ENV:-production}
+      ENVIRONMENT: ${APP_ENV:-dev}

 networks:
   tutordex:
-    name: tutordex
+    # Auto-generated: ${COMPOSE_PROJECT_NAME}_tutordex
     
   supabase_net:
     external: true
-    name: supabase_default
+    name: ${SUPABASE_NETWORK:-supabase_default}
```

### 5.2 Volume Naming Strategy

**Current Volumes:**
- `telegram_link_bot_state`
- `redis_data`
- `prometheus_data`
- `alertmanager_data`
- `grafana_data`
- `tempo_data`

**Automatic Prefixing via Docker Compose:**

When using `docker compose -p tutordex-staging`, volumes are automatically prefixed:
- `tutordex-staging_telegram_link_bot_state`
- `tutordex-staging_redis_data`
- `tutordex-staging_prometheus_data`
- etc.

When using `docker compose -p tutordex-prod`, volumes are automatically prefixed:
- `tutordex-prod_telegram_link_bot_state`
- `tutordex-prod_redis_data`
- `tutordex-prod_prometheus_data`
- etc.

**No Manual Changes Needed:** Docker Compose project naming handles this automatically.

**Volume Inspection Commands:**
```bash
# List staging volumes
docker volume ls --filter name=tutordex-staging

# List production volumes
docker volume ls --filter name=tutordex-prod

# Inspect specific volume
docker volume inspect tutordex-prod_redis_data
```

### 5.3 Network Naming Strategy

**Current Networks:**
- `tutordex` (internal application network)
- `supabase_net` (external, connects to Supabase)

**Automatic Naming:**

After removing `name: tutordex` from `docker-compose.yml`, Docker Compose will auto-generate:
- Staging: `tutordex-staging_tutordex` (or `tutordex-staging_default`)
- Production: `tutordex-prod_tutordex` (or `tutordex-prod_default`)

Services within each project reference each other by service name (`redis`, `backend`, etc.), which Docker Compose resolves within the correct network automatically.

**External Supabase Networks:**

Parameterize via `SUPABASE_NETWORK` environment variable:
- Staging: `SUPABASE_NETWORK=supabase_staging_default`
- Production: `SUPABASE_NETWORK=supabase_default`

**Prerequisite:** Each Supabase instance must be running with its own network:
```bash
# Staging Supabase
cd /path/to/supabase-staging
docker compose -p supabase-staging up -d

# Production Supabase
cd /path/to/supabase-prod
docker compose -p supabase up -d
```

### 5.4 Docker Compose Commands

#### Starting Staging Environment

```bash
cd /path/to/TutorDexMonoRepo

# Full command
docker compose \
    -f docker-compose.yml \
    -p tutordex-staging \
    --env-file .env.staging \
    up -d --build

# Or use the helper script
./scripts/deploy_staging.sh
```

**What Happens:**
1. Reads `.env.staging` for all environment variables
2. Creates project namespace `tutordex-staging`
3. Builds images for aggregator, backend, alertmanager-telegram
4. Pulls base images (redis, prometheus, grafana, etc.)
5. Creates network `tutordex-staging_tutordex`
6. Creates volumes `tutordex-staging_redis_data`, etc.
7. Starts all services with staging configuration
8. Backend accessible on port 8001

#### Starting Production Environment

```bash
cd /path/to/TutorDexMonoRepo

# Full command
docker compose \
    -f docker-compose.yml \
    -p tutordex-prod \
    --env-file .env.prod \
    up -d --build

# Or use the helper script
./scripts/deploy_prod.sh
```

**What Happens:**
1. Reads `.env.prod` for all environment variables
2. Creates project namespace `tutordex-prod`
3. Builds images for aggregator, backend, alertmanager-telegram
4. Pulls base images (redis, prometheus, grafana, etc.)
5. Creates network `tutordex-prod_tutordex`
6. Creates volumes `tutordex-prod_redis_data`, etc.
7. Starts all services with production configuration
8. Backend accessible on port 8000

#### Stopping Staging (Without Affecting Production)

```bash
# Full command
docker compose \
    -f docker-compose.yml \
    -p tutordex-staging \
    --env-file .env.staging \
    down

# Or use helper script
./scripts/stop_staging.sh
```

**Effect:**
- Stops and removes all `tutordex-staging` containers
- Preserves volumes (data is retained)
- Does NOT affect `tutordex-prod` containers

#### Stopping Production (Without Affecting Staging)

```bash
# Full command
docker compose \
    -f docker-compose.yml \
    -p tutordex-prod \
    --env-file .env.prod \
    down

# Or use helper script
./scripts/stop_prod.sh
```

**Effect:**
- Stops and removes all `tutordex-prod` containers
- Preserves volumes (data is retained)
- Does NOT affect `tutordex-staging` containers

#### Viewing Logs

```bash
# Staging logs (all services)
docker compose -p tutordex-staging logs -f

# Staging logs (specific service)
docker compose -p tutordex-staging logs -f backend

# Production logs (all services)
docker compose -p tutordex-prod logs -f

# Production logs (specific service)
docker compose -p tutordex-prod logs -f aggregator-worker

# Or use helper scripts
./scripts/logs_staging.sh backend
./scripts/logs_prod.sh aggregator-worker
```

#### Rebuilding Specific Service

```bash
# Rebuild staging backend
docker compose -p tutordex-staging build backend
docker compose -p tutordex-staging up -d backend

# Rebuild production aggregator
docker compose -p tutordex-prod build aggregator-worker collector-tail
docker compose -p tutordex-prod up -d aggregator-worker collector-tail
```

#### Completely Removing Environment (Including Volumes)

```bash
# DANGER: Deletes all staging data
docker compose -p tutordex-staging down -v

# DANGER: Deletes all production data
docker compose -p tutordex-prod down -v
```

**WARNING:** The `-v` flag deletes volumes. Use with extreme caution. Only appropriate when decommissioning an environment entirely.

### 5.5 Port Conflict Prevention

| Service | Staging Port | Production Port | Conflict Risk |
|---------|-------------|-----------------|---------------|
| Backend | 8001 | 8000 | ✅ No conflict |
| Prometheus | 9091 | 9090 | ✅ No conflict |
| Alertmanager | 9094 | 9093 | ✅ No conflict |
| Grafana | 3301 | 3300 | ✅ No conflict |
| Tempo HTTP | 3201 | 3200 | ✅ No conflict |
| Tempo OTLP gRPC | 4319 | 4317 | ✅ No conflict |
| Tempo OTLP HTTP | 4320 | 4318 | ✅ No conflict |
| Redis | N/A (internal) | N/A (internal) | ✅ No conflict (network-isolated) |
| Collector metrics | N/A (internal) | N/A (internal) | ✅ No conflict (network-isolated) |
| Worker metrics | N/A (internal) | N/A (internal) | ✅ No conflict (network-isolated) |

**Validation Command:**
```bash
# Check for port conflicts before starting
netstat -an | findstr ":8000 :8001 :9090 :9091 :3300 :3301"

# On Linux/WSL
ss -tulpn | grep -E ":(8000|8001|9090|9091|3300|3301|3200|3201)"
```


---

## 6. Safety Guardrails (CRITICAL)

### 6.1 Code-Level Production Protections

#### 6.1.1 Startup Environment Validation

**Implementation:** Add to `shared/config.py`

```python
def validate_environment_integrity(cfg: BaseSettings) -> None:
    """
    Validate environment configuration at startup.
    
    Prevents dangerous misconfigurations like:
    - APP_ENV=prod with staging database URL
    - APP_ENV=staging with production database URL
    - Missing required production settings
    
    Raises:
        RuntimeError: If dangerous misconfiguration detected
    """
    app_env = str(getattr(cfg, "app_env", "dev")).strip().lower()
    
    if app_env in {"prod", "production"}:
        # PRODUCTION ENVIRONMENT CHECKS
        supabase_url = str(getattr(cfg, "supabase_url", "") or "").strip().lower()
        
        # Check 1: Prod should not use staging Supabase port
        if ":54322" in supabase_url:
            raise RuntimeError(
                "FATAL CONFIGURATION ERROR:\n"
                "APP_ENV=prod but SUPABASE_URL contains staging port :54322\n"
                "This configuration would write production data to staging database.\n"
                "Fix: Update .env.prod to use production Supabase URL (port :54321)"
            )
        
        # Check 2: Prod requires authentication
        if not getattr(cfg, "auth_required", True):
            raise RuntimeError(
                "FATAL CONFIGURATION ERROR:\n"
                "APP_ENV=prod but AUTH_REQUIRED=false\n"
                "Production must have authentication enabled.\n"
                "Fix: Set AUTH_REQUIRED=true in .env.prod"
            )
        
        # Check 3: Prod requires Firebase admin
        if hasattr(cfg, "firebase_admin_enabled") and not getattr(cfg, "firebase_admin_enabled", False):
            raise RuntimeError(
                "FATAL CONFIGURATION ERROR:\n"
                "APP_ENV=prod but FIREBASE_ADMIN_ENABLED=false\n"
                "Production must have Firebase authentication enabled.\n"
                "Fix: Set FIREBASE_ADMIN_ENABLED=true in .env.prod"
            )
        
        # Check 4: Prod requires admin API key
        if hasattr(cfg, "admin_api_key"):
            admin_key = str(getattr(cfg, "admin_api_key", "") or "").strip()
            if not admin_key or admin_key == "changeme" or len(admin_key) < 32:
                raise RuntimeError(
                    "FATAL CONFIGURATION ERROR:\n"
                    "APP_ENV=prod but ADMIN_API_KEY is missing or weak\n"
                    "Production must have a strong admin API key.\n"
                    "Fix: Set ADMIN_API_KEY to a secure random string in .env.prod"
                )
    
    elif app_env == "staging":
        # STAGING ENVIRONMENT CHECKS
        supabase_url = str(getattr(cfg, "supabase_url", "") or "").strip().lower()
        
        # Check 1: Staging should not use production Supabase port
        if ":54321" in supabase_url and ":54322" not in supabase_url:
            raise RuntimeError(
                "FATAL CONFIGURATION ERROR:\n"
                "APP_ENV=staging but SUPABASE_URL contains production port :54321\n"
                "This configuration would write staging test data to production database.\n"
                "Fix: Update .env.staging to use staging Supabase URL (port :54322)"
            )
        
        # Check 2: Warn if broadcast enabled in staging (allow but warn)
        if hasattr(cfg, "enable_broadcast") and getattr(cfg, "enable_broadcast", False):
            import logging
            logging.warning(
                "STAGING BROADCAST ENABLED: "
                "ENABLE_BROADCAST=true in staging environment. "
                "Ensure AGGREGATOR_CHANNEL_ID points to a test channel, not production channel."
            )
        
        # Check 3: Warn if DMs enabled in staging
        if hasattr(cfg, "enable_dms") and getattr(cfg, "enable_dms", False):
            import logging
            logging.warning(
                "STAGING DMs ENABLED: "
                "ENABLE_DMS=true in staging environment. "
                "Ensure only test tutor accounts will receive DMs."
            )
```

**Integration Points:**

1. **Aggregator Collector** (`TutorDexAggregator/collector.py`):
```python
from shared.config import load_aggregator_config, validate_environment_integrity

def main():
    cfg = load_aggregator_config()
    validate_environment_integrity(cfg)  # ADD THIS
    # ... rest of collector logic
```

2. **Aggregator Worker** (`TutorDexAggregator/workers/extract_worker_main.py`):
```python
from shared.config import load_aggregator_config, validate_environment_integrity

def main():
    cfg = load_aggregator_config()
    validate_environment_integrity(cfg)  # ADD THIS
    # ... rest of worker logic
```

3. **Backend** (`TutorDexBackend/app.py`):
```python
from shared.config import load_backend_config, validate_environment_integrity

@app.on_event("startup")
async def _startup_log() -> None:
    cfg = load_backend_config()
    validate_environment_integrity(cfg)  # ADD THIS
    # ... rest of startup logic
```

#### 6.1.2 Broadcast Safety Check

**Implementation:** Add to `TutorDexAggregator/delivery/broadcast_client.py`

```python
def validate_broadcast_safety(cfg) -> None:
    """
    Validate broadcast configuration before sending messages.
    
    Prevents staging from accidentally broadcasting to production channel.
    """
    app_env = str(getattr(cfg, "app_env", "dev")).strip().lower()
    channel_id = str(getattr(cfg, "aggregator_channel_id", "") or "").strip()
    enable_broadcast = getattr(cfg, "enable_broadcast", False)
    
    if not enable_broadcast:
        return  # Broadcast disabled, no check needed
    
    if not channel_id:
        raise RuntimeError(
            "BROADCAST ERROR: ENABLE_BROADCAST=true but AGGREGATOR_CHANNEL_ID is empty"
        )
    
    # Convention: staging channels should have "_test" or "_staging" in ID
    if app_env == "staging":
        if not any(marker in channel_id.lower() for marker in ["test", "staging", "dev"]):
            raise RuntimeError(
                f"BROADCAST SAFETY ERROR:\n"
                f"APP_ENV=staging but AGGREGATOR_CHANNEL_ID does not contain 'test', 'staging', or 'dev'\n"
                f"Channel ID: {channel_id}\n"
                f"This may be a production channel.\n"
                f"Fix: Use a test channel ID or add '_test' suffix to confirm it's a test channel"
            )
        
        logger.warning(
            "staging_broadcast_active",
            extra={
                "channel_id": channel_id,
                "message": "Staging environment will broadcast to Telegram. Ensure this is intentional."
            }
        )

def send_broadcast(...):
    validate_broadcast_safety(cfg)  # ADD AT START OF FUNCTION
    # ... existing broadcast logic
```

#### 6.1.3 DM Safety Check

**Implementation:** Add to `TutorDexAggregator/dm_assignments_impl.py`

```python
def validate_dm_safety(cfg) -> None:
    """
    Validate DM configuration before sending messages.
    
    Warns when staging is sending DMs to ensure recipients are test accounts.
    """
    app_env = str(getattr(cfg, "app_env", "dev")).strip().lower()
    enable_dms = getattr(cfg, "enable_dms", False)
    
    if not enable_dms:
        return  # DMs disabled, no check needed
    
    if app_env == "staging":
        logger.warning(
            "staging_dms_active",
            extra={
                "message": "Staging environment will send DMs. Ensure recipients are test accounts only."
            }
        )
    
    # Additional check: if staging uses prod Redis/Supabase, recipient list will be from prod
    # This is why database isolation is critical

def send_dms(...):
    validate_dm_safety(cfg)  # ADD AT START OF FUNCTION
    # ... existing DM logic
```

### 6.2 Operational Safeguards

#### 6.2.1 Pre-Start Validation Script

**File:** `scripts/validate_env.sh` (CREATE NEW)

```bash
#!/bin/bash
set -euo pipefail

ENV_FILE="${1:-.env.prod}"

if [ ! -f "$ENV_FILE" ]; then
    echo "ERROR: Environment file not found: $ENV_FILE"
    exit 1
fi

echo "Validating $ENV_FILE..."

# Source the env file
set -a
source "$ENV_FILE"
set +a

# Validation functions
check_required() {
    local var_name="$1"
    local var_value="${!var_name:-}"
    
    if [ -z "$var_value" ]; then
        echo "  ❌ MISSING: $var_name is required but not set"
        return 1
    else
        echo "  ✅ SET: $var_name"
        return 0
    fi
}

check_prod_ports() {
    local env="${APP_ENV:-dev}"
    
    if [ "$env" == "prod" ]; then
        if [ "${BACKEND_PORT:-8000}" != "8000" ]; then
            echo "  ⚠️  WARNING: Production BACKEND_PORT is not 8000 (found: ${BACKEND_PORT})"
        fi
        if [ "${PROMETHEUS_PORT:-9090}" != "9090" ]; then
            echo "  ⚠️  WARNING: Production PROMETHEUS_PORT is not 9090 (found: ${PROMETHEUS_PORT})"
        fi
    fi
}

check_staging_ports() {
    local env="${APP_ENV:-dev}"
    
    if [ "$env" == "staging" ]; then
        if [ "${BACKEND_PORT:-8001}" == "8000" ]; then
            echo "  ❌ ERROR: Staging BACKEND_PORT conflicts with production (8000)"
            return 1
        fi
        if [ "${PROMETHEUS_PORT:-9091}" == "9090" ]; then
            echo "  ❌ ERROR: Staging PROMETHEUS_PORT conflicts with production (9090)"
            return 1
        fi
    fi
}

check_supabase_url() {
    local env="${APP_ENV:-dev}"
    local url="${SUPABASE_URL:-}"
    
    if [ "$env" == "prod" ] && [[ "$url" == *":54322"* ]]; then
        echo "  ❌ FATAL: Production using staging Supabase port (:54322)"
        return 1
    fi
    
    if [ "$env" == "staging" ] && [[ "$url" == *":54321"* ]] && [[ "$url" != *":54322"* ]]; then
        echo "  ❌ FATAL: Staging using production Supabase port (:54321)"
        return 1
    fi
}

# Run validations
ERRORS=0

echo ""
echo "Required Variables:"
check_required "APP_ENV" || ERRORS=$((ERRORS + 1))
check_required "COMPOSE_PROJECT_NAME" || ERRORS=$((ERRORS + 1))
check_required "SUPABASE_URL" || ERRORS=$((ERRORS + 1))
check_required "SUPABASE_SERVICE_ROLE_KEY" || ERRORS=$((ERRORS + 1))

echo ""
echo "Port Configuration:"
check_prod_ports || ERRORS=$((ERRORS + 1))
check_staging_ports || ERRORS=$((ERRORS + 1))

echo ""
echo "Database Configuration:"
check_supabase_url || ERRORS=$((ERRORS + 1))

echo ""
if [ $ERRORS -eq 0 ]; then
    echo "✅ Validation PASSED: $ENV_FILE"
    exit 0
else
    echo "❌ Validation FAILED: $ERRORS error(s) found in $ENV_FILE"
    exit 1
fi
```

Make executable:
```bash
chmod +x scripts/validate_env.sh
```

**Usage:**
```bash
# Validate staging environment
./scripts/validate_env.sh .env.staging

# Validate production environment
./scripts/validate_env.sh .env.prod
```

**Integration:** Update deployment scripts to call validation:

```bash
# In deploy_staging.sh and deploy_prod.sh
./scripts/validate_env.sh "$ENV_FILE" || exit 1
```

#### 6.2.2 Startup Confirmation Prompt

**Implementation:** Already included in `scripts/deploy_prod.sh`:

```bash
echo "=== Deploying TutorDex PRODUCTION ==="
echo "WARNING: This will restart production services."
read -p "Continue? (yes/no): " confirm

if [ "$confirm" != "yes" ]; then
    echo "Deployment cancelled."
    exit 0
fi
```

**Do NOT add confirmation prompt to staging** - staging should be easy to deploy repeatedly.

#### 6.2.3 Dry-Run Mode for Staging

**Environment Variable:** `DRY_RUN=1`

**Implementation Example (broadcast):**

```python
def send_broadcast(assignment_data: Dict, cfg) -> bool:
    dry_run = os.getenv("DRY_RUN", "0") == "1"
    
    if dry_run:
        logger.info(
            "broadcast_dry_run",
            extra={
                "assignment_code": assignment_data.get("assignment_code"),
                "channel_id": cfg.aggregator_channel_id,
                "action": "would_broadcast"
            }
        )
        return True  # Pretend success
    
    # ... actual broadcast logic
```

### 6.3 Human-Error Prevention Steps

#### 6.3.1 Environment Indicator in Logs

**Implementation:** Add environment label to all log messages

```python
# In logging_setup.py or app startup
logger = logging.getLogger("tutordex")
logger.info(
    "startup",
    extra={
        "environment": os.getenv("APP_ENV", "unknown"),
        "compose_project": os.getenv("COMPOSE_PROJECT_NAME", "unknown"),
        "message": "=== ENVIRONMENT: {} ===".format(os.getenv("APP_ENV", "UNKNOWN").upper())
    }
)
```

#### 6.3.2 Distinct Grafana Dashboards

**Implementation:**
- Staging Grafana (port 3301): Add "🧪 STAGING" prefix to all dashboard names
- Production Grafana (port 3300): Add "🔴 PRODUCTION" prefix to all dashboard names

**Manual Step:** After migration, edit Grafana dashboards:
1. Open Grafana UI for each environment
2. Edit dashboard settings → General → Title
3. Staging: "🧪 STAGING - [Dashboard Name]"
4. Production: "🔴 PRODUCTION - [Dashboard Name]"

#### 6.3.3 Host-Level Directory Organization

**Recommended Structure on Windows Host:**

```
D:\TutorDex\
├── TutorDexMonoRepo\           # Git repository
│   ├── .env.staging            # Staging secrets
│   ├── .env.prod              # Production secrets
│   ├── docker-compose.yml
│   └── scripts\
├── supabase-staging\           # Staging Supabase instance
│   └── docker-compose.yml
├── supabase-prod\              # Production Supabase instance
│   └── docker-compose.yml
└── README_ENVIRONMENTS.txt     # HUMAN-READABLE GUIDE
```

**README_ENVIRONMENTS.txt Content:**

```
TUTORDEX DUAL-ENVIRONMENT SETUP
================================

STAGING (Testing & Development)
- Backend: http://localhost:8001
- Grafana: http://localhost:3301 (admin/[staging_password])
- Start: cd TutorDexMonoRepo && scripts\deploy_staging.sh
- Stop:  cd TutorDexMonoRepo && scripts\stop_staging.sh
- Logs:  cd TutorDexMonoRepo && scripts\logs_staging.sh

PRODUCTION (Live Service)
- Backend: http://localhost:8000
- Grafana: http://localhost:3300 (admin/[prod_password])
- Start: cd TutorDexMonoRepo && scripts\deploy_prod.sh
- Stop:  cd TutorDexMonoRepo && scripts\stop_prod.sh
- Logs:  cd TutorDexMonoRepo && scripts\logs_prod.sh

CRITICAL SAFETY RULES:
1. NEVER copy .env.prod to .env.staging (or vice versa)
2. NEVER copy production secrets to staging environment
3. ALWAYS verify APP_ENV before starting services
4. ALWAYS use deployment scripts (not raw docker compose commands)

Emergency Contact: [Your contact info]
```

#### 6.3.4 Colored Terminal Prompts

**Optional Enhancement:** Use terminal colors in deployment scripts:

```bash
# deploy_staging.sh
echo -e "\033[1;34m=== Deploying TutorDex STAGING ===\033[0m"

# deploy_prod.sh
echo -e "\033[1;31m=== Deploying TutorDex PRODUCTION ===\033[0m"
echo -e "\033[1;31mWARNING: This will restart production services.\033[0m"
```


---

## 7. Migration Sequence (Step-by-Step)

**Timeline:** 2-4 hours (depending on Supabase setup time)

**Prerequisites:**
- [ ] Read this entire document
- [ ] Understand all safety guardrails
- [ ] Have backup of current production database
- [ ] Windows host has Docker Desktop running
- [ ] Have test Telegram bots and channels ready

### Phase 1: Preparation (NO DOWNTIME)

**Step 1.1:** Backup Current Production State
```bash
# Backup production Supabase database
cd /path/to/supabase-prod
docker compose exec postgres pg_dump -U postgres tutordex > tutordex_backup_$(date +%Y%m%d_%H%M%S).sql

# Backup production Redis
docker compose -p tutordex exec redis redis-cli BGSAVE

# Optional: Copy redis dump.rdb from volume
docker run --rm -v tutordex_redis_data:/data -v D:/TutorDex/backups:/backup alpine cp /data/dump.rdb /backup/redis_backup_$(date +%Y%m%d_%H%M%S).rdb
```

**Validation:**
- [ ] Database backup file exists and is > 0 bytes
- [ ] Redis backup successful (check Docker logs)

---

**Step 1.2:** Deploy Staging Supabase Instance

```bash
cd D:/TutorDex
mkdir supabase-staging
cd supabase-staging

# Download Supabase self-hosted setup
# (Assuming you have existing Supabase docker-compose.yml)
# Modify ports to avoid conflicts:
# - Kong: 54322 (instead of 54321)
# - PostgreSQL: 54323 (instead of 54322)
# - Studio: 54324 (instead of 54323)

# Start staging Supabase
docker compose -p supabase-staging up -d

# Wait for services to be ready
docker compose -p supabase-staging logs -f
# Wait for "API started successfully" message
```

**Validation:**
- [ ] Staging Supabase accessible at http://localhost:54322
- [ ] PostgreSQL accessible at localhost:54323
- [ ] Studio accessible at http://localhost:54324
- [ ] Network `supabase_staging_default` exists: `docker network ls | grep staging`

**STOP POINT:** Do not proceed until staging Supabase is fully operational.

---

**Step 1.3:** Initialize Staging Database Schema

```bash
cd D:/TutorDex/TutorDexMonoRepo

# Apply full schema to staging database
# Option A: Via Supabase Studio UI (http://localhost:54324)
#   - SQL Editor → Run supabase_schema_full.sql

# Option B: Via psql
docker compose -p supabase-staging exec postgres psql -U postgres -d tutordex -f /path/to/supabase_schema_full.sql

# Apply any additional migrations
# (Run all migration files in TutorDexAggregator/supabase sqls/)
```

**Validation:**
- [ ] Tables exist: `assignments`, `telegram_messages_raw`, `telegram_extractions`, etc.
- [ ] Query succeeds: `SELECT COUNT(*) FROM assignments;` (should return 0)

---

**Step 1.4:** Create Staging Environment Files

```bash
cd D:/TutorDex/TutorDexMonoRepo

# Create staging env files
cp TutorDexAggregator/.env.example TutorDexAggregator/.env.staging
cp TutorDexBackend/.env.example TutorDexBackend/.env.staging

# Edit .env.staging files with staging credentials
# CRITICAL: Use test bots, test channels, staging Supabase URL
# CRITICAL: Set ENABLE_BROADCAST=false and ENABLE_DMS=false initially

# Create top-level .env.staging for docker-compose
cat > .env.staging << 'EOF'
APP_ENV=staging
COMPOSE_PROJECT_NAME=tutordex-staging
BACKEND_PORT=8001
PROMETHEUS_PORT=9091
ALERTMANAGER_PORT=9094
GRAFANA_PORT=3301
TEMPO_HTTP_PORT=3201
TEMPO_OTLP_GRPC_PORT=4319
TEMPO_OTLP_HTTP_PORT=4320
SUPABASE_NETWORK=supabase_staging_default
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=[generate_secure_password]
OTEL_ENABLED=1
EOF
```

**Validation:**
- [ ] `.env.staging` exists with correct APP_ENV=staging
- [ ] `TutorDexAggregator/.env.staging` has staging Supabase URL
- [ ] `TutorDexBackend/.env.staging` has staging Supabase URL
- [ ] No production secrets in staging files

**STOP POINT:** Review all staging env files for correctness before proceeding.

---

**Step 1.5:** Apply Code Changes

```bash
cd D:/TutorDex/TutorDexMonoRepo

# Apply docker-compose.yml modifications (see Section 3.1)
# - Add APP_ENV to all services
# - Parameterize ports
# - Update networks configuration

# Apply safety guardrail code changes (see Section 6.1)
# - Add validate_environment_integrity() to shared/config.py
# - Add validation calls to collector.py, extract_worker_main.py, app.py
# - Add broadcast/DM safety checks

# Create deployment scripts (see Section 3.3)
mkdir -p scripts
# Create deploy_staging.sh, deploy_prod.sh, stop_staging.sh, stop_prod.sh, validate_env.sh
chmod +x scripts/*.sh

# Test validation script
./scripts/validate_env.sh .env.staging
```

**Validation:**
- [ ] `docker-compose.yml` has `APP_ENV: "${APP_ENV:-dev}"` in all services
- [ ] `shared/config.py` has `validate_environment_integrity()` function
- [ ] Deployment scripts exist and are executable
- [ ] Validation script passes for staging env file

---

### Phase 2: Staging Environment Testing (NO PRODUCTION IMPACT)

**Step 2.1:** Start Staging Environment

```bash
cd D:/TutorDex/TutorDexMonoRepo

# Start staging
./scripts/deploy_staging.sh

# Monitor startup
./scripts/logs_staging.sh
```

**Validation:**
- [ ] All containers start successfully
- [ ] No errors in logs about missing environment variables
- [ ] Backend startup log shows `APP_ENV: staging`
- [ ] Backend accessible at http://localhost:8001/health
- [ ] Grafana accessible at http://localhost:3301

**STOP POINT:** Fix any startup errors before proceeding. Production is still unaffected.

---

**Step 2.2:** Validate Staging Database Isolation

```bash
# Insert test record in staging
curl -X POST http://localhost:8001/admin/test_assignment \
    -H "X-Api-Key: <staging_admin_key>" \
    -d '{"assignment_code": "TEST001", "subject": "Math"}'

# Verify it appears in staging database only
docker compose -p supabase-staging exec postgres psql -U postgres -d tutordex -c "SELECT assignment_code FROM assignments;"
# Should see TEST001

# Verify production database is untouched (if prod is running)
docker compose -p supabase exec postgres psql -U postgres -d tutordex -c "SELECT COUNT(*) FROM assignments;"
# Should show original count (no TEST001)
```

**Validation:**
- [ ] Test record in staging database
- [ ] Production database unchanged
- [ ] Staging Redis isolated (check with redis-cli if needed)

---

**Step 2.3:** Test Staging Services

```bash
# Test backend API
curl http://localhost:8001/health
curl http://localhost:8001/health/dependencies

# Test Prometheus
curl http://localhost:9091/-/healthy

# Test Grafana
# Open http://localhost:3301 in browser, login with staging credentials

# Test collector (if Telegram credentials are configured)
./scripts/logs_staging.sh collector-tail
# Should see collector startup logs

# Test worker
./scripts/logs_staging.sh aggregator-worker
# Should see worker startup logs
```

**Validation:**
- [ ] Backend health endpoint returns 200
- [ ] Prometheus is scraping metrics
- [ ] Grafana dashboards load (may need to mark as staging)
- [ ] Collector and worker start without errors
- [ ] No broadcasts or DMs sent (ENABLE_BROADCAST=false, ENABLE_DMS=false)

**STOP POINT:** Do not proceed to production migration until staging is fully validated.

---

### Phase 3: Production Environment Setup (DOWNTIME WINDOW)

**Estimated Downtime:** 10-15 minutes

**Step 3.1:** Announce Maintenance Window

```
EXAMPLE ANNOUNCEMENT:
"TutorDex will undergo scheduled maintenance from [time] to [time] (approximately 15 minutes).
During this time, the website and Telegram bot may be unavailable.
We apologize for any inconvenience."
```

---

**Step 3.2:** Stop Current Production Services

```bash
cd D:/TutorDex/TutorDexMonoRepo

# Current single-environment services (no project name)
docker compose down

# Verify all containers stopped
docker ps | grep tutordex
# Should be empty (or only staging containers)
```

**Validation:**
- [ ] No TutorDex containers running (except staging)
- [ ] Supabase still running
- [ ] Redis data preserved in volume

---

**Step 3.3:** Rename Production Supabase for Clarity (Optional)

```bash
# If your Supabase is currently named "supabase", rename project for clarity
cd /path/to/current/supabase

docker compose -p supabase down
docker compose -p supabase-prod up -d

# Update network name reference
# Ensure SUPABASE_NETWORK=supabase_default in .env.prod
```

**Validation:**
- [ ] Supabase accessible at original port (54321)
- [ ] Network `supabase_default` exists

---

**Step 3.4:** Create Production Environment Files

```bash
cd D:/TutorDex/TutorDexMonoRepo

# Create production env files from current .env (if exists)
# Or create from .env.example
cp TutorDexAggregator/.env TutorDexAggregator/.env.prod
cp TutorDexBackend/.env TutorDexBackend/.env.prod

# Create top-level .env.prod
cat > .env.prod << 'EOF'
APP_ENV=prod
COMPOSE_PROJECT_NAME=tutordex-prod
BACKEND_PORT=8000
PROMETHEUS_PORT=9090
ALERTMANAGER_PORT=9093
GRAFANA_PORT=3300
TEMPO_HTTP_PORT=3200
TEMPO_OTLP_GRPC_PORT=4317
TEMPO_OTLP_HTTP_PORT=4318
SUPABASE_NETWORK=supabase_default
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=[existing_prod_password]
OTEL_ENABLED=1
EOF

# CRITICAL: Verify production credentials are correct
./scripts/validate_env.sh .env.prod
```

**Validation:**
- [ ] `.env.prod` has `APP_ENV=prod`
- [ ] Production Supabase URL is correct (:54321)
- [ ] Production bot tokens are set
- [ ] `ENABLE_BROADCAST=true` and `ENABLE_DMS=true` (if desired)
- [ ] `AUTH_REQUIRED=true`
- [ ] Validation script passes

**STOP POINT:** Triple-check production env files before starting services.

---

**Step 3.5:** Start Production Environment with New Configuration

```bash
cd D:/TutorDex/TutorDexMonoRepo

# Start production with explicit project name
./scripts/deploy_prod.sh

# Monitor startup closely
./scripts/logs_prod.sh
```

**Watch For:**
- [ ] Startup log shows `APP_ENV: prod`
- [ ] Supabase connection successful
- [ ] Redis connection successful
- [ ] No environment validation errors
- [ ] Collector connects to Telegram
- [ ] Worker claims jobs from extraction queue
- [ ] Backend API responds at :8000

**Validation:**
```bash
# Health check
curl http://localhost:8000/health

# Verify correct database
curl http://localhost:8000/assignments?limit=10
# Should return existing production assignments

# Check container names
docker ps | grep tutordex
# Should see tutordex-prod-* containers

# Check volumes
docker volume ls | grep tutordex-prod
# Should see tutordex-prod_redis_data, etc.
```

**STOP POINT:** If anything is wrong, immediately stop prod and investigate. Staging can be used as reference.

---

**Step 3.6:** Verify Production Functionality

```bash
# Test backend
curl http://localhost:8000/health/dependencies

# Test Prometheus
curl http://localhost:9090/-/healthy

# Open Grafana
# http://localhost:3300 → Should show production dashboards

# Check logs for any errors
./scripts/logs_prod.sh backend
./scripts/logs_prod.sh collector-tail
./scripts/logs_prod.sh aggregator-worker

# Verify broadcast (if enabled)
# Check Telegram aggregator channel for new posts

# Verify DMs (if enabled)
# Check that DMs are being sent to matched tutors
```

**Validation:**
- [ ] Backend serving requests
- [ ] Metrics being collected
- [ ] Dashboards visible
- [ ] Collector ingesting messages
- [ ] Worker processing extractions
- [ ] Broadcast working (if enabled)
- [ ] DMs working (if enabled)

---

**Step 3.7:** End Maintenance Window

```
EXAMPLE ANNOUNCEMENT:
"TutorDex is back online! All services have been restored.
Thank you for your patience during the maintenance."
```

---

### Phase 4: Post-Migration Validation (PRODUCTION LIVE)

**Step 4.1:** Monitor Production for 30 Minutes

```bash
# Watch logs continuously
./scripts/logs_prod.sh -f

# Monitor error rates in Grafana
# http://localhost:3300 → Check error dashboards

# Check Sentry for any new errors
# (if configured)

# Verify assignments are being added
# Check database row count every few minutes
```

**Validation:**
- [ ] No increase in error rates
- [ ] Assignments continue to be ingested
- [ ] Website remains accessible
- [ ] Telegram bots responding

---

**Step 4.2:** Test Staging and Production Isolation

```bash
# Start both environments simultaneously
./scripts/deploy_staging.sh
./scripts/deploy_prod.sh

# Verify no port conflicts
netstat -an | findstr ":8000 :8001 :9090 :9091 :3300 :3301"

# Stop staging without affecting production
./scripts/stop_staging.sh

# Verify production still running
curl http://localhost:8000/health
# Should return 200

# Restart staging
./scripts/deploy_staging.sh

# Verify both running
docker ps | grep tutordex
# Should see both tutordex-staging-* and tutordex-prod-* containers
```

**Validation:**
- [ ] Both environments can run simultaneously
- [ ] Stopping one does not affect the other
- [ ] Separate volumes confirmed: `docker volume ls | grep tutordex`
- [ ] Separate networks confirmed: `docker network ls | grep tutordex`

---

**Step 4.3:** Document Deployed State

```bash
# Create deployment record
cat > D:/TutorDex/DEPLOYMENT_RECORD_$(date +%Y%m%d).txt << EOF
TutorDex Dual-Environment Deployment
Date: $(date)
Operator: [Your Name]

PRODUCTION:
- Compose Project: tutordex-prod
- Backend Port: 8000
- Grafana Port: 3300
- Volumes: $(docker volume ls --filter name=tutordex-prod --format "{{.Name}}" | wc -l) volumes
- Containers: $(docker ps --filter name=tutordex-prod --format "{{.Names}}" | wc -l) running

STAGING:
- Compose Project: tutordex-staging
- Backend Port: 8001
- Grafana Port: 3301
- Volumes: $(docker volume ls --filter name=tutordex-staging --format "{{.Name}}" | wc -l) volumes
- Containers: $(docker ps --filter name=tutordex-staging --format "{{.Names}}" | wc -l) running

VALIDATION:
- Production health: PASSED
- Staging isolation: CONFIRMED
- Database separation: CONFIRMED
- Port conflicts: NONE

NOTES:
[Add any issues encountered or deviations from plan]
EOF
```

---

## 8. Rollback Plan

**Scenario:** Migration fails, need to restore single-environment setup.

### Rollback Procedure

**Step R1:** Stop New Dual-Environment Setup

```bash
cd D:/TutorDex/TutorDexMonoRepo

# Stop both environments
./scripts/stop_prod.sh
./scripts/stop_staging.sh

# Or forcefully:
docker compose -p tutordex-prod down
docker compose -p tutordex-staging down
```

---

**Step R2:** Revert Code Changes

```bash
cd D:/TutorDex/TutorDexMonoRepo

# Option A: Git revert (if changes were committed)
git revert [commit_hash]
git push origin main

# Option B: Git reset (if local only)
git reset --hard [pre-migration_commit]

# Option C: Restore from backup
# (If you backed up the entire directory before starting)
```

---

**Step R3:** Restore Original docker-compose.yml

```bash
# Ensure docker-compose.yml has no APP_ENV variables
# Ensure networks use simple names (tutordex, supabase_default)
# Ensure ports are not parameterized
```

---

**Step R4:** Restore Original .env Files

```bash
cd D:/TutorDex/TutorDexMonoRepo

# Restore from backup (if you backed up before migration)
cp TutorDexAggregator/.env.backup TutorDexAggregator/.env
cp TutorDexBackend/.env.backup TutorDexBackend/.env
```

---

**Step R5:** Start Original Single-Environment Setup

```bash
cd D:/TutorDex/TutorDexMonoRepo

# Start without project name (original behavior)
docker compose up -d --build

# Verify services start
docker compose logs -f
```

---

**Step R6:** Validate Production Restored

```bash
# Health check
curl http://localhost:8000/health

# Check database access
curl http://localhost:8000/assignments?limit=5

# Check Grafana
# http://localhost:3300

# Check Prometheus
curl http://localhost:9090/-/healthy
```

---

**Step R7:** Clean Up Staging Resources (Optional)

```bash
# Remove staging Supabase
cd D:/TutorDex/supabase-staging
docker compose -p supabase-staging down -v

# Remove staging volumes
docker volume rm $(docker volume ls --filter name=tutordex-staging --format "{{.Name}}")

# Remove staging env files
rm D:/TutorDex/TutorDexMonoRepo/.env.staging
rm D:/TutorDex/TutorDexMonoRepo/TutorDexAggregator/.env.staging
rm D:/TutorDex/TutorDexMonoRepo/TutorDexBackend/.env.staging
```

---

### State Preservation Requirements

**During Migration:**
- [ ] Production Supabase database must remain untouched
- [ ] Production Redis volume must be preserved (`redis_data`)
- [ ] Telegram session files must be preserved
- [ ] Grafana dashboards must be preserved (`grafana_data`)
- [ ] Prometheus data can be lost (metrics are regenerated)
- [ ] No production credentials should be deleted

**If Rollback Needed:**
- Production database is unchanged (was never migrated, only re-referenced)
- Production Redis volume still exists with original name
- Original `.env` files were backed up
- Original docker-compose.yml can be restored from git

---

## 9. Non-Goals

**Explicit list of things NOT to change during this migration:**

### 9.1 Code Functionality
- [ ] **NO** changes to LLM extraction logic
- [ ] **NO** changes to matching algorithm
- [ ] **NO** changes to broadcast message formatting
- [ ] **NO** changes to DM delivery logic
- [ ] **NO** changes to assignment parsing
- [ ] **NO** changes to duplicate detection
- [ ] **NO** changes to click tracking
- [ ] **NO** changes to Redis schema or key structure
- [ ] **NO** changes to Supabase table schemas (except adding env tracking if needed)

### 9.2 External Services
- [ ] **NO** changes to Telegram API integration
- [ ] **NO** changes to Firebase Auth configuration
- [ ] **NO** changes to LLM API endpoints
- [ ] **NO** changes to TutorCity API integration
- [ ] **NO** changes to Nominatim geocoding

### 9.3 Observability
- [ ] **NO** changes to Prometheus metrics (names, labels, cardinality)
- [ ] **NO** changes to Grafana dashboard logic (only labels/titles)
- [ ] **NO** changes to Alertmanager alert rules
- [ ] **NO** changes to Sentry configuration

### 9.4 Website
- [ ] **NO** changes to website code (TutorDexWebsite/)
- [ ] **NO** changes to Firebase Hosting deployment
- [ ] **NO** changes to website API integration

### 9.5 Infrastructure
- [ ] **NO** migration to Kubernetes or other orchestration platform
- [ ] **NO** migration to cloud providers
- [ ] **NO** changes to Windows host operating system
- [ ] **NO** Docker Engine upgrade (unless required for compatibility)
- [ ] **NO** changes to Tailscale VPN configuration
- [ ] **NO** changes to Caddy reverse proxy (already supports environment routing)

### 9.6 Database Schemas
- [ ] **NO** changes to `assignments` table structure
- [ ] **NO** changes to `telegram_messages_raw` structure
- [ ] **NO** changes to RPC function signatures
- [ ] **NO** data migrations between databases
- [ ] **NO** index modifications

### 9.7 Configuration Schema
- [ ] **NO** changes to `shared/config.py` structure (only additions for validation)
- [ ] **NO** changes to environment variable names (except adding new ones)
- [ ] **NO** changes to `.env.example` template structure

### 9.8 Branch Strategy
- [ ] **NO** creation of staging or production branches
- [ ] **NO** changes to GitHub workflows (except to support dual-environment deployment)
- [ ] **NO** changes to commit/PR process

### 9.9 Testing
- [ ] **NO** addition of new test suites (this is a migration, not a feature)
- [ ] **NO** changes to existing test structure or CI validation

### 9.10 Documentation
- [ ] **NO** rewriting of existing docs (only add this migration plan)
- [ ] **NO** changes to component README files (unless critical env info)

---

## 10. Success Criteria

**Migration is considered successful when:**

1. ✅ Staging environment runs independently on alternate ports
2. ✅ Production environment runs on standard ports with existing data
3. ✅ Both environments can run simultaneously without conflicts
4. ✅ Staging uses separate Supabase database (no prod data)
5. ✅ Staging uses separate Redis instance (no shared keys)
6. ✅ Production data is unchanged (0 records modified unintentionally)
7. ✅ All safety guardrails pass validation at startup
8. ✅ Deployment scripts work reliably for both environments
9. ✅ Production services resume normal operation post-migration
10. ✅ No increase in production error rates or alert frequency
11. ✅ Code-level validations prevent cross-environment contamination
12. ✅ Documentation updated and deployment guide created

---

## 11. Appendices

### Appendix A: Quick Reference - Commands

```bash
# STAGING
./scripts/deploy_staging.sh         # Start staging
./scripts/stop_staging.sh           # Stop staging
./scripts/logs_staging.sh backend   # View logs
./scripts/validate_env.sh .env.staging  # Validate config
docker compose -p tutordex-staging ps   # List containers

# PRODUCTION
./scripts/deploy_prod.sh            # Start production
./scripts/stop_prod.sh              # Stop production
./scripts/logs_prod.sh backend      # View logs
./scripts/validate_env.sh .env.prod # Validate config
docker compose -p tutordex-prod ps  # List containers

# UTILITIES
docker volume ls | grep tutordex    # List volumes
docker network ls | grep tutordex   # List networks
docker ps --filter name=tutordex    # List all TutorDex containers
netstat -an | findstr ":8000 :8001" # Check port usage
```

### Appendix B: Troubleshooting

**Issue:** "Port already in use" error

**Solution:**
```bash
# Find process using port
netstat -ano | findstr :8000

# Stop conflicting container
docker ps | grep 8000
docker stop [container_id]
```

**Issue:** "Network not found: supabase_default"

**Solution:**
```bash
# Ensure Supabase is running
cd /path/to/supabase
docker compose ps

# Check network exists
docker network ls | grep supabase

# If missing, recreate
docker compose down && docker compose up -d
```

**Issue:** "Environment validation failed" on startup

**Solution:**
```bash
# Check APP_ENV matches expected
grep APP_ENV .env.prod  # Should be "prod"
grep APP_ENV .env.staging  # Should be "staging"

# Verify Supabase URLs match environment
grep SUPABASE_URL .env.prod  # Should have :54321
grep SUPABASE_URL .env.staging  # Should have :54322
```

**Issue:** Staging accidentally sending broadcasts to prod channel

**Solution:**
```bash
# IMMEDIATELY stop staging
./scripts/stop_staging.sh

# Verify AGGREGATOR_CHANNEL_ID in .env.staging
grep AGGREGATOR_CHANNEL_ID TutorDexAggregator/.env.staging

# Ensure it's a test channel, not prod
# Fix and restart with ENABLE_BROADCAST=false initially
```

---

## 12. Sign-Off Checklist

**Before executing this migration, confirm:**

- [ ] I have read this entire document
- [ ] I understand the safety guardrails and their purpose
- [ ] I have test bots and channels ready for staging
- [ ] I have backed up the production database
- [ ] I have backed up production .env files
- [ ] I have scheduled a maintenance window
- [ ] I have a rollback plan and know how to execute it
- [ ] I have validated the `.env.staging` file (no prod secrets)
- [ ] I have validated the `.env.prod` file (correct credentials)
- [ ] I understand how to stop one environment without affecting the other
- [ ] I know how to identify which environment a container belongs to
- [ ] I have tested the validation scripts
- [ ] I have informed stakeholders of the maintenance window

**Signature:** ___________________________  **Date:** ___________

---

**END OF MIGRATION PLAN**

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-19 | Infrastructure Architect | Initial comprehensive migration plan |

