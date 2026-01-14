# TutorDex Dependencies

Complete documentation of all external dependencies required to run TutorDex.

## Quick Start

Run the bootstrap script to set up everything:

```bash
./scripts/bootstrap.sh
```

## External Services

### Required Services

These services are required for core functionality:

#### 1. **Supabase (PostgreSQL + PostgREST)**

- **Purpose:** Primary data store for all assignments, tutor profiles, and metadata
- **Version:** 2.0+ (self-hosted recommended)
- **Required For:** All data persistence operations
- **Setup:**
  ```bash
  cd supabase
  docker-compose up -d
  ```
- **Access:** http://localhost:54321
- **Schema:** Tracked via `schema_migrations` table
- **Migration:** `python scripts/migrate.py`

**Environment Variables:**
```bash
SUPABASE_URL=http://localhost:54321
SUPABASE_KEY=your_service_role_key
```

#### 2. **Redis**

- **Purpose:** Tutor profiles, rate limiting, caching, link codes
- **Version:** 7.0+
- **Required For:** Tutor matching, DM subscriptions, cache
- **Setup:**
  ```bash
  docker run -d --name tutordex-redis -p 6379:6379 redis:7-alpine
  ```
- **Access:** redis://localhost:6379
- **Persistence:** Optional (RDB snapshots recommended for production)

**Environment Variables:**
```bash
REDIS_URL=redis://localhost:6379/0
REDIS_PREFIX=tutordex  # Optional key prefix
```

#### 3. **Firebase Authentication**

- **Purpose:** Website user authentication (email/password, Google sign-in)
- **Version:** Latest
- **Required For:** Website user login, API authentication
- **Setup:**
  1. Create project at https://console.firebase.google.com
  2. Enable Authentication → Sign-in methods (Email/Password, Google)
  3. Download service account JSON for backend
  4. Get Web API credentials for website

**Environment Variables (Backend):**
```bash
FIREBASE_ADMIN_ENABLED=1
FIREBASE_ADMIN_CREDENTIALS_PATH=/path/to/service-account.json
```

**Environment Variables (Website):**
```bash
VITE_FIREBASE_API_KEY=your_api_key
VITE_FIREBASE_AUTH_DOMAIN=your-project.firebaseapp.com
VITE_FIREBASE_PROJECT_ID=your-project
```

#### 4. **LLM API (LM Studio or OpenAI-compatible)**

- **Purpose:** Canonical assignment parsing (extract subject, level, rate, location)
- **Version:** OpenAI-compatible API (LM Studio recommended for local development)
- **Required For:** Canonical JSON extraction (deterministic extraction works without LLM)
- **Setup:**
  - **LM Studio:** Download from https://lmstudio.ai/, load Qwen 2.5 7B or similar
  - **Alternative:** Any OpenAI-compatible API (OpenAI, Ollama, vLLM, etc.)
- **Access:** http://localhost:1234 (default for LM Studio)

**Environment Variables:**
```bash
LLM_API_URL=http://localhost:1234  # Or host.docker.internal:1234 in Docker
LLM_MODEL_NAME=default
LLM_CIRCUIT_BREAKER_THRESHOLD=5
LLM_CIRCUIT_BREAKER_TIMEOUT_SECONDS=60
```

**Note:** The system can operate with deterministic extraction only (tutor types and rates). LLM is used for canonical parsing of full assignment details.

---

### Optional Services

These services enhance functionality but are not required for core operations:

#### 5. **Tempo (Distributed Tracing)**

- **Purpose:** End-to-end request tracing for debugging
- **Version:** Latest
- **Required For:** Distributed tracing (Task 3)
- **Setup:** Included in `docker-compose.yml` (Task 3)
- **Access:** http://localhost:3200
- **Enabled By:** `OTEL_ENABLED=1`

#### 6. **Prometheus + Grafana (Observability)**

- **Purpose:** Metrics collection and visualization
- **Version:** Latest
- **Required For:** Monitoring, alerting, business metrics
- **Setup:**
  ```bash
  cd observability
  docker-compose up -d
  ```
- **Access:**
  - Grafana: http://localhost:3300 (admin/admin)
  - Prometheus: http://localhost:9090

#### 7. **Sentry (Error Reporting)**

- **Purpose:** Frontend and backend error tracking
- **Version:** Cloud or self-hosted
- **Required For:** Production error visibility
- **Setup:** Create project at https://sentry.io (free tier sufficient)

**Environment Variables:**
```bash
SENTRY_DSN=https://your_dsn@sentry.io/project_id
SENTRY_ENVIRONMENT=production
```

---

## Dependency Matrix

| Service | Aggregator | Backend | Website | Purpose |
|---------|-----------|---------|---------|---------|
| Supabase | ✅ Required | ✅ Required | - | Data persistence |
| Redis | ✅ Required | ✅ Required | - | Tutor profiles, cache |
| Firebase Auth | - | ✅ Required | ✅ Required | User authentication |
| LLM API | 🟡 Optional | - | - | Canonical parsing |
| Tempo | 🟡 Optional | 🟡 Optional | - | Distributed tracing |
| Prometheus/Grafana | 🟡 Optional | 🟡 Optional | - | Metrics, monitoring |
| Sentry | 🟡 Optional | 🟡 Optional | 🟡 Optional | Error reporting |

Legend:
- ✅ Required: Service must be available for core functionality
- 🟡 Optional: Service enhances functionality but is not required

---

## Versioning and Compatibility

### Database Schema

- **Current Version:** Tracked in `public.schema_migrations` table
- **Migration Tool:** `scripts/migrate.py`
- **Breaking Changes:** Require schema version bump and migration

```bash
# Check current schema version
psql $SUPABASE_URL -c "SELECT version FROM schema_migrations ORDER BY version DESC LIMIT 1"

# Apply pending migrations
python scripts/migrate.py
```

### API Versions

- **Backend API:** v0.1.0 (no versioning yet, backward compatible changes only)
- **Supabase PostgREST:** Compatible with v2.0+
- **LLM API:** OpenAI-compatible v1 endpoints

### Python Dependencies

Managed via `requirements.txt` in each service:

- **Backend:** `TutorDexBackend/requirements.txt`
- **Aggregator:** `TutorDexAggregator/requirements.txt`

```bash
# Install dependencies
pip install -r TutorDexBackend/requirements.txt
pip install -r TutorDexAggregator/requirements.txt
```

### Node.js Dependencies

Website dependencies managed via `package.json`:

```bash
cd TutorDexWebsite
npm install
```

---

## Development vs Production

### Development (Local)

**Recommended Setup:**
- Supabase: Self-hosted via Docker (included)
- Redis: Docker container
- Firebase: Cloud (free tier)
- LLM: LM Studio (local)
- Tempo/Grafana: Docker (optional)

**Start Everything:**
```bash
./scripts/bootstrap.sh
docker-compose up
```

### Production (Deployed)

**Recommended Setup:**
- Supabase: Self-hosted (your infrastructure)
- Redis: Dedicated instance (persistent)
- Firebase: Cloud (production project)
- LLM: Cloud API or self-hosted (GPU recommended)
- Tempo/Grafana: Included in docker-compose

**Differences:**
- Set `APP_ENV=production`
- Enable authentication: `AUTH_REQUIRED=1`
- Use production Firebase project
- Enable Sentry: `SENTRY_DSN=...`
- Enable OTEL: `OTEL_ENABLED=1`

---

## Network Topology

```
┌─────────────────┐
│   TutorDex      │
│   Website       │
│  (Port 5173)    │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│   Backend API   │─────────┐
│   (Port 8000)   │         │
└────────┬────────┘         │
         │                  │ Auth
         │ REST API         ▼
         │            ┌──────────┐
         ▼            │ Firebase │
┌─────────────────┐  │   Auth   │
│   Supabase      │  └──────────┘
│  (Port 54321)   │
└─────────────────┘
         ▲
         │ PostgreSQL
         │
┌────────┴────────┐
│   Aggregator    │──────────┐
│  Collector +    │          │
│    Workers      │          │ API
└─────────────────┘          ▼
         ▲            ┌──────────┐
         │            │ LLM API  │
         │ Messages   │  (1234)  │
         │            └──────────┘
┌────────┴────────┐
│   Telegram      │
│   Channels      │
└─────────────────┘

         Shared:
┌─────────────────┐  ┌─────────────────┐
│     Redis       │  │  Prometheus     │
│   (Port 6379)   │  │  Grafana Tempo  │
└─────────────────┘  └─────────────────┘
```

---

## Troubleshooting

### Supabase Connection Issues

```bash
# Check if Supabase is running
curl http://localhost:54321/rest/v1/

# Check logs
cd supabase
docker-compose logs
```

### Redis Connection Issues

```bash
# Test Redis connection
redis-cli -h localhost -p 6379 ping

# Check if running
docker ps | grep redis
```

### LLM API Issues

```bash
# Test LLM API
curl http://localhost:1234/v1/models

# Check if LM Studio is running
# Open LM Studio → Start Server
```

### Firebase Auth Issues

- Verify service account JSON is valid
- Check Firebase project settings
- Ensure Auth methods are enabled

---

## References

- **Supabase Docs:** https://supabase.com/docs
- **Redis Docs:** https://redis.io/docs
- **Firebase Docs:** https://firebase.google.com/docs
- **LM Studio:** https://lmstudio.ai/
- **Grafana:** https://grafana.com/docs
- **Sentry:** https://docs.sentry.io/

---

**Document Version:** 1.0  
**Last Updated:** 2026-01-14  
**Maintained By:** TutorDex Team
