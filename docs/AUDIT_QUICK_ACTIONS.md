# Codebase Quality Audit — Quick Action Guide

**Source:** `docs/CODEBASE_QUALITY_AUDIT_2026-01.md`  
**Date:** January 12, 2026

This is a condensed action guide extracted from the full 1,200-line audit report.

---

## 🚨 Critical Issues (Fix This Week)

### 1. Fail Fast on Auth Misconfiguration (30 minutes)

**File:** `TutorDexBackend/app.py` (lines 61-70)

**Current Risk:** Firebase Admin can initialize disabled, allowing production to run with no authentication.

**Fix:**
```python
# TutorDexBackend/app.py, startup event
if _is_prod() and not _auth_required():
    raise RuntimeError("AUTH_REQUIRED must be true when APP_ENV=prod")
if _is_prod():
    st = firebase_admin_status()
    if not st.get("enabled") or not st.get("ready"):
        raise RuntimeError(f"Firebase Admin not ready in prod: {st}")
```

**Impact:** Prevents critical security vulnerability (auth bypass).

---

### 2. Detect Supabase RPC Ambiguous Overloads (1 hour)

**File:** `TutorDexAggregator/supabase_env.py` (new helper function)

**Current Risk:** PostgREST returns HTTP 300 when multiple functions match signature; worker logs error but marks job as "ok", causing silent data loss.

**Fix:**
```python
def _check_rpc_response(response, rpc_name):
    if response.status_code == 300:
        raise ValueError(
            f"Supabase RPC '{rpc_name}' returned 300 (ambiguous function overload). "
            "Check for duplicate function definitions in schema."
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase RPC '{rpc_name}' failed: {response.status_code} {response.text}")
    return response

# Use in all Supabase RPC calls across codebase
```

**Impact:** Prevents silent data loss when persistence fails.

---

### 3. Add LLM Circuit Breaker (2-3 hours)

**File:** New `TutorDexAggregator/circuit_breaker.py`

**Current Risk:** When LLM API is down, worker retries each job 3x, burning through entire queue (10k+ jobs × 3 retries = 30k wasted calls).

**Fix:**
```python
class CircuitBreaker:
    def __init__(self, failure_threshold=5, timeout_seconds=60):
        self.failure_count = 0
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.opened_at = None
    
    def call(self, func, *args, **kwargs):
        if self.is_open():
            raise CircuitBreakerOpenError("Circuit breaker open, LLM API unavailable")
        try:
            result = func(*args, **kwargs)
            self.on_success()
            return result
        except Exception:
            self.on_failure()
            raise
    
    def is_open(self):
        if self.opened_at is None:
            return False
        if time.time() - self.opened_at > self.timeout_seconds:
            self.opened_at = None  # Reset after timeout
            self.failure_count = 0
            return False
        return True
    
    def on_success(self):
        self.failure_count = 0
        self.opened_at = None
    
    def on_failure(self):
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.opened_at = time.time()

# Wire into extract_worker.py
llm_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout_seconds=60)
```

**Impact:** Stops queue burn when LLM is down, faster incident detection.

---

## 📊 High-Priority Refactors (This Month)

### 4. Extract Domain Services from `app.py` (1 week)

**Problem:** 1,547-line god object mixing auth, matching, tracking, analytics, admin endpoints.

**Approach:**
1. Extract `AuthService` (Firebase verification + middleware)
2. Extract `MatchingService` (pure function, no HTTP deps)
3. Extract `AnalyticsService` (Supabase event writes)
4. Extract `TelegramService` (link codes, webhook handling)
5. Leave thin routing layer in `app.py`

**Target Structure:**
```
TutorDexBackend/
  app.py (300 lines, HTTP routing only)
  services/
    auth_service.py
    matching_service.py
    analytics_service.py
    telegram_service.py
```

**Impact:** 4× faster onboarding, easier testing, enables future velocity.

---

### 5. Add Migration Version Tracking (1 day)

**Problem:** 19 SQL files, no tracking of what's applied. Operator must remember state.

**Solution:**
```sql
-- New file: TutorDexAggregator/supabase sqls/00_migration_tracking.sql
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    id SERIAL PRIMARY KEY,
    migration_name TEXT UNIQUE NOT NULL,
    applied_at TIMESTAMPTZ DEFAULT NOW()
);
```

```python
# New script: scripts/migrate.py
def apply_migrations(supabase_url, supabase_key):
    migrations = sorted(Path("TutorDexAggregator/supabase sqls").glob("*.sql"))
    for migration_file in migrations:
        name = migration_file.stem
        if not migration_applied(name):
            logger.info(f"Applying migration: {name}")
            execute_sql(migration_file.read_text())
            record_migration(name)
```

**Impact:** Safe deploys (auto-apply migrations), clear audit log.

---

### 6. Add Frontend Error Reporting (1 day)

**Problem:** Website errors invisible to operators (no Sentry, console-only logs).

**Solution:**
```javascript
// TutorDexWebsite/src/errorReporter.js
import * as Sentry from "@sentry/browser";

if (import.meta.env.PROD) {
  Sentry.init({
    dsn: import.meta.env.VITE_SENTRY_DSN,
    environment: "production",
  });
}

export function reportError(error, context = {}) {
  if (import.meta.env.PROD) {
    Sentry.captureException(error, { extra: context });
  }
  console.error("Error:", error, context);
}

// Use in page-assignments.js:
try {
  const assignments = await listOpenAssignmentsPaged(...);
} catch (error) {
  reportError(error, { context: "loadAssignments", filters });
  showErrorMessage("Failed to load assignments. Please try again.");
}
```

**Impact:** Visibility into user-facing errors, faster bug detection.

---

## 🏗️ Long-Term Refactors (This Quarter)

### 7. Break Up `supabase_persist.py` (2-3 weeks)

**Problem:** 1,311 lines, 300-line merge function with 7 nesting levels.

**Strategy:**
1. Extract `GeoEnricher` (coordinate resolution, Nominatim, MRT lookup)
2. Extract `MergePolicy` (rules for preferring signals, timestamps)
3. Extract `AssignmentRow` domain object (typed dataclass)
4. Extract `EventPublisher` (broadcast, DM, duplicate detection)
5. Leave thin Supabase adapter

**Impact:** 5× easier to understand merge logic, testable without DB.

---

### 8. Add End-to-End Tracing (1 week)

**Problem:** Cannot trace message → extraction → persistence → broadcast → DM.

**Solution:**
- Enable OTEL in production (`OTEL_ENABLED=1`)
- Add trace context propagation across services
- Restore Tempo from git history (`observability/tempo/`)

**Impact:** Trace failed DMs to source message, understand end-to-end latency.

---

### 9. Add HTTP Integration Tests (2-3 days)

**Problem:** No automated tests for backend API surface.

**Solution:**
```python
# tests/test_backend_api.py
from fastapi.testclient import TestClient
from TutorDexBackend.app import app

client = TestClient(app)

def test_health_endpoint():
    response = client.get("/health/full")
    assert response.status_code == 200

def test_assignments_list_public():
    response = client.get("/assignments?sort=newest&limit=10")
    assert response.status_code == 200
    assert len(response.json()["assignments"]) <= 10

# ... 20+ tests
```

**Impact:** Catch API breaking changes in CI, refactor with confidence.

---

## 📋 System Non-Negotiables

Recommended guardrails to enforce going forward:

1. **Fail Fast in Production** — Misconfig that could cause data loss/security issues MUST cause startup failure
2. **No Silent Failures in Critical Paths** — Errors that could corrupt data MUST be explicit and observable
3. **External Dependencies Declared** — All services required for production MUST be documented, versioned, bootstrappable
4. **Schema Changes → Migration + Contract** — Assignment table or API contract changes MUST include SQL migration + schema update + CI pass
5. **Files Over 500 Lines → Justification** — Large files must have documented reason or be refactored
6. **Observability Not Optional** — All async/background operations MUST emit metrics and structured logs

---

## 🎯 Priority Order

**Week 1:**
1. Auth fail-fast (30 min) ← **DO FIRST**
2. Supabase RPC 300 detection (1 hour)
3. LLM circuit breaker (2-3 hours)

**Week 2-4:**
4. Extract services from `app.py` (1 week)
5. Migration tracking (1 day)
6. Frontend error reporting (1 day)

**Quarter:**
7. Break up `supabase_persist.py` (2-3 weeks)
8. End-to-end tracing (1 week)
9. HTTP integration tests (2-3 days)

---

## 📊 Complexity Metrics

**Current State:**
- 113 Python files, 126 total code files
- 3 files > 1,500 lines (app.py: 1547, extract_worker.py: 1610, supabase_persist.py: 1311)
- 22 test files (good coverage for extractors, zero coverage for APIs)
- 25+ documentation files (excellent)
- 7 `__init__.py` files (poor package structure)

**Red Flags:**
- God objects in critical paths
- Bare `except:` blocks swallow errors
- No custom exception classes (only 1 found)
- External Supabase dependency not included/versioned

**Green Flags:**
- Strong observability (50+ metrics, 17 alerts)
- Comprehensive documentation culture
- Contract validation in CI
- Deterministic signal extraction (reduces LLM variance)

---

**For full analysis, see:** `docs/CODEBASE_QUALITY_AUDIT_2026-01.md`
