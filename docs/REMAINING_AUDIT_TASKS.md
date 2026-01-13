# Remaining Tasks from Codebase Quality Audit (January 2026)

**Document created:** 2026-01-13  
**Source:** `docs/CODEBASE_QUALITY_AUDIT_2026-01.md`  
**Status:** Active Implementation Guide

---

## Overview

This document lists all remaining tasks from the January 2026 Codebase Quality Audit, organized by recommended implementation order. Priorities 1-7 have been completed as of 2026-01-13.

### ✅ Completed Priorities (1-7)

1. ✅ **Fail Fast on Auth Misconfiguration** - Already implemented in `app.py` startup
2. ✅ **Detect Supabase RPC 300 Errors** - Implemented in `supabase_env.py`
3. ✅ **Add LLM Circuit Breaker** - Implemented in `circuit_breaker.py`
4. ✅ **Extract Domain Services from app.py** - Refactored 1547→1033 lines (33% reduction)
5. ✅ **Add Migration Version Tracking** - Implemented `scripts/migrate.py`
6. ✅ **Add Frontend Error Reporting** - Sentry integration complete
7. ✅ **Break Up supabase_persist.py** - Refactored 1311→416 lines (68% reduction)

**Note:** Priority 7 was completed after the audit was written. The `supabase_persist.py` file has been successfully refactored into 6 focused service modules:
- `services/row_builder.py` (491 lines) - Assignment row construction
- `services/merge_policy.py` (148 lines) - Conservative merge logic
- `services/geocoding_service.py` (101 lines) - Postal code → coordinates
- `services/event_publisher.py` (71 lines) - Broadcast/DM/duplicate detection
- `services/persistence_operations.py` (71 lines) - Agency upserts
- Core `supabase_persist.py` (416 lines) - Thin orchestration layer

See `docs/IMPLEMENTATION_PRIORITIES_1-3.md` for details on priorities 1-3 and related PRs for priorities 4-7.

---

## 🎯 Recommended Implementation Order

### **Phase 1: Testing & Configuration Foundation** (Next 2 Weeks)

These tasks provide foundational improvements that enable safer refactoring and reduce operational errors.

---

#### **Task 1: Add HTTP Integration Tests for Backend** ⭐ HIGHEST PRIORITY

**Priority:** 10 (from audit)  
**Effort:** 2-3 days  
**Impact:** HIGH  
**Risk:** Medium (requires test infrastructure)

**Problem:** No automated tests for backend API surface. Breaking changes to API go undetected until production.

**Solution:** Add FastAPI TestClient-based integration tests for all 30 endpoints.

**Implementation:**

```python
# New file: tests/test_backend_api.py
from fastapi.testclient import TestClient
from TutorDexBackend.app import app
import pytest

client = TestClient(app)

# Health endpoints
def test_health_endpoint():
    response = client.get("/health/full")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_health_redis():
    response = client.get("/health/redis")
    assert response.status_code in [200, 503]  # May be unavailable in test

# Public endpoints (no auth)
def test_assignments_list_public():
    response = client.get("/assignments?sort=newest&limit=10")
    assert response.status_code == 200
    data = response.json()
    assert "assignments" in data
    assert len(data["assignments"]) <= 10

def test_assignments_list_pagination():
    response = client.get("/assignments?sort=newest&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "pagination" in data
    assert data["pagination"]["limit"] == 5

def test_assignments_requires_auth_for_distance():
    """Distance sorting requires auth (tutor location)"""
    response = client.get("/assignments?sort=distance")
    assert response.status_code in [400, 401]

# Subject taxonomy endpoints
def test_subjects_list():
    response = client.get("/subjects")
    assert response.status_code == 200
    data = response.json()
    assert "subjects" in data
    assert len(data["subjects"]) > 0

def test_levels_list():
    response = client.get("/levels")
    assert response.status_code == 200
    data = response.json()
    assert "levels" in data

# Matching endpoint (public, requires payload)
def test_match_payload_missing_data():
    response = client.post("/match/payload", json={})
    assert response.status_code == 422  # Validation error

def test_match_payload_valid():
    payload = {
        "assignment_data": {
            "id": "test123",
            "level": "Primary",
            "subjects": ["Mathematics"],
            "location": {"region": "North"},
        }
    }
    response = client.post("/match/payload", json=payload)
    assert response.status_code in [200, 400]  # May fail if Redis unavailable

# Auth-required endpoints (mock Firebase token)
@pytest.fixture
def auth_headers(monkeypatch):
    """Mock Firebase token verification for testing"""
    # TODO: Mock firebase_admin.auth.verify_id_token
    return {"Authorization": "Bearer mock_token"}

def test_profile_get_requires_auth():
    response = client.get("/profile")
    assert response.status_code == 401

def test_profile_update_requires_auth():
    response = client.put("/profile", json={"subjects": ["Mathematics"]})
    assert response.status_code == 401

# Admin endpoints (require admin key)
def test_admin_stats_requires_key():
    response = client.get("/admin/stats")
    assert response.status_code == 401

def test_admin_stats_with_valid_key(monkeypatch):
    monkeypatch.setenv("ADMIN_API_KEY", "test_key")
    response = client.get("/admin/stats", headers={"X-Admin-Key": "test_key"})
    # May succeed or fail depending on DB state
    assert response.status_code in [200, 500]

# Rate limiting tests
def test_rate_limiting_headers():
    """Check that rate limit headers are present"""
    response = client.get("/assignments")
    # If rate limiting is enabled, check headers
    if "X-RateLimit-Limit" in response.headers:
        assert "X-RateLimit-Remaining" in response.headers

# Error handling tests
def test_invalid_sort_parameter():
    response = client.get("/assignments?sort=invalid")
    assert response.status_code == 400

def test_negative_limit():
    response = client.get("/assignments?limit=-1")
    assert response.status_code == 400

# CORS tests
def test_cors_headers():
    response = client.options("/assignments")
    # Check CORS headers if configured
    assert "Access-Control-Allow-Origin" in response.headers or response.status_code == 200
```

**Files to Create:**
- `tests/test_backend_api.py` (~500 lines, 30+ tests)
- `tests/conftest.py` (shared fixtures for Firebase mocking)
- `tests/test_backend_auth.py` (focused auth tests)
- `tests/test_backend_admin.py` (focused admin endpoint tests)

**Benefits:**
- ✅ Catch API breaking changes in CI
- ✅ Refactor backend with confidence
- ✅ Document expected API behavior
- ✅ Test auth/rate limiting/CORS logic

**Success Criteria:**
- All 30 endpoints have at least 1 test (success case)
- Auth-required endpoints tested with/without token
- Admin endpoints tested with/without admin key
- CI runs tests on every PR
- Test suite runs in <30 seconds

**Dependencies:**
- `pytest` (already in use)
- `httpx` (for TestClient, may already be installed)
- Mock for Firebase token verification

**Risks:**
- May discover bugs in existing endpoints
- Need to mock Redis/Supabase for isolated tests
- May need to refactor some endpoints for testability

---

#### **Task 2: Consolidate Environment Config**

**Priority:** 9 (from audit)  
**Effort:** 2-3 days  
**Impact:** MEDIUM  
**Risk:** Medium (touches many files)

**Problem:** Environment variable parsing spread across 10+ files with inconsistent defaults. Every file has `_truthy()`, `_env_int()`, `_env_first()` helpers duplicated.

**Solution:** Create centralized config using `pydantic-settings` with single source of truth.

**Implementation:**

```python
# New file: shared/config.py
from pydantic_settings import BaseSettings
from typing import Optional

class AggregatorConfig(BaseSettings):
    """Configuration for TutorDexAggregator services"""
    
    # Supabase
    supabase_url: str
    supabase_key: str
    
    # Pipeline versioning
    extraction_pipeline_version: str = "2026-01-02_det_time_v1"
    schema_version: str = "2026-01-01"
    
    # Extraction worker
    extraction_max_attempts: int = 3
    extraction_worker_batch_size: int = 10
    extraction_worker_poll_seconds: int = 5
    extraction_worker_oneshot: bool = False
    
    # LLM API
    llm_api_url: str = "http://host.docker.internal:1234"
    llm_model_name: str = "default"
    llm_circuit_breaker_threshold: int = 5
    llm_circuit_breaker_timeout_seconds: int = 60
    
    # Side-effects (opt-in for worker)
    enable_broadcast: bool = False
    enable_dms: bool = False
    enable_persistence: bool = True
    
    # Telegram
    telegram_api_id: Optional[str] = None
    telegram_api_hash: Optional[str] = None
    telegram_session_name: str = "tutordex_collector"
    
    # Observability
    otel_enabled: bool = False
    prometheus_port: int = 8001
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

class BackendConfig(BaseSettings):
    """Configuration for TutorDexBackend API"""
    
    # Environment
    app_env: str = "dev"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    
    # Auth
    auth_required: bool = True
    firebase_admin_enabled: bool = True
    firebase_admin_credentials_path: Optional[str] = None
    admin_api_key: Optional[str] = None
    
    # Database
    supabase_url: str
    supabase_key: str
    redis_url: str = "redis://localhost:6379/0"
    
    # Rate limiting
    rate_limit_enabled: bool = True
    rate_limit_default: str = "100/minute"
    
    # Observability
    otel_enabled: bool = False
    log_level: str = "INFO"
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

class WebsiteConfig(BaseSettings):
    """Configuration for TutorDexWebsite"""
    
    # Firebase
    firebase_api_key: str
    firebase_auth_domain: str
    firebase_project_id: str
    
    # Backend API
    backend_api_url: str = "http://localhost:8000"
    
    # Sentry
    sentry_dsn: Optional[str] = None
    sentry_environment: str = "production"
    sentry_sample_rate: float = 0.1
    
    class Config:
        env_prefix = "VITE_"
        env_file = ".env"
        env_file_encoding = "utf-8"
```

**Migration Strategy:**

1. **Create shared/config.py** with all config classes
2. **Update one service at a time** (start with aggregator worker)
3. **Keep backward compatibility** during transition:
   ```python
   # In extract_worker.py
   try:
       from shared.config import AggregatorConfig
       cfg = AggregatorConfig()
       SUPABASE_URL = cfg.supabase_url
   except ImportError:
       # Fallback to old env parsing (temporary)
       SUPABASE_URL = os.environ["SUPABASE_URL"]
   ```
4. **Remove old helpers** once all files migrated

**Files to Modify:**
- Create `shared/config.py`
- Update `TutorDexAggregator/workers/extract_worker.py`
- Update `TutorDexAggregator/collector.py`
- Update `TutorDexBackend/app.py` (or use existing `config_utils.py`)
- Update all files with `_truthy()`, `_env_int()`, `_env_first()` helpers

**Benefits:**
- ✅ Single source of truth for config
- ✅ Type-checked defaults (prevents int/str errors)
- ✅ Easy to audit required vs optional vars
- ✅ Auto-generate .env.example from schema
- ✅ Better error messages for missing/invalid config

**Success Criteria:**
- All services use shared config classes
- No more duplicated env parsing helpers
- `.env.example` auto-generated from schema
- Startup validates all required env vars

**Dependencies:**
- `pydantic-settings` (add to requirements.txt)

---

### **Phase 2: Observability** (Next 1-2 Weeks)

**Note:** The original Phase 2 included Task 4 (Break Up supabase_persist.py), which has been completed. Only Task 3 (End-to-End Tracing) remains in this phase.

This task improves system visibility for debugging and performance analysis.

---

#### **Task 3: Add End-to-End Tracing**

**Priority:** 8 (from audit)  
**Effort:** 1 week  
**Impact:** MEDIUM  
**Risk:** Low (additive, doesn't break existing)

**Problem:** Cannot trace: Telegram message → extraction → persistence → broadcast → DM. OTEL instrumentation exists but `OTEL_ENABLED=1` is optional.

**Solution:** Enable OTEL by default in production, add trace context propagation, restore Tempo.

**Implementation:**

**Step 1: Enable OTEL by default in production**

```yaml
# docker-compose.yml
services:
  tutordex-aggregator:
    environment:
      OTEL_ENABLED: "${OTEL_ENABLED:-1}"  # Default to enabled
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4318"
      OTEL_SERVICE_NAME: "tutordex-aggregator"
      
  tutordex-backend:
    environment:
      OTEL_ENABLED: "${OTEL_ENABLED:-1}"
      OTEL_EXPORTER_OTLP_ENDPOINT: "http://otel-collector:4318"
      OTEL_SERVICE_NAME: "tutordex-backend"
```

**Step 2: Add trace context propagation**

```python
# TutorDexAggregator/collector.py
from opentelemetry import trace
tracer = trace.get_tracer(__name__)

async def process_message(message):
    with tracer.start_as_current_span("telegram_message_seen") as span:
        span.set_attribute("channel", channel_link)
        span.set_attribute("message_id", message.id)
        
        # Store trace_id for propagation
        trace_id = span.get_span_context().trace_id
        
        # Pass trace_id to extraction queue
        enqueue_extraction(raw_id, trace_id=trace_id)

# TutorDexAggregator/workers/extract_worker.py
def process_extraction(extraction):
    # Continue existing trace
    if extraction.get("trace_id"):
        with tracer.start_as_current_span(
            "extraction_job",
            context=set_span_in_context(NonRecordingSpan(trace_id=extraction["trace_id"]))
        ):
            # All work here is traced
            extract_and_persist(extraction)
```

**Step 3: Restore Tempo**

```yaml
# observability/tempo/docker-compose.yml
services:
  tempo:
    image: grafana/tempo:latest
    command: [ "-config.file=/etc/tempo.yaml" ]
    volumes:
      - ./tempo.yaml:/etc/tempo.yaml
      - tempo-data:/tmp/tempo
    ports:
      - "3200:3200"   # tempo
      - "4317:4317"   # otlp grpc
      - "4318:4318"   # otlp http
      
  otel-collector:
    image: otel/opentelemetry-collector:latest
    command: ["--config=/etc/otel-collector.yaml"]
    volumes:
      - ./otel-collector.yaml:/etc/otel-collector.yaml
    ports:
      - "4317:4317"   # OTLP gRPC receiver
      - "4318:4318"   # OTLP HTTP receiver

volumes:
  tempo-data:
```

**Step 4: Add Tempo datasource to Grafana**

```yaml
# observability/grafana/provisioning/datasources/tempo.yaml
apiVersion: 1
datasources:
  - name: Tempo
    type: tempo
    access: proxy
    url: http://tempo:3200
    isDefault: false
```

**Benefits:**
- ✅ Trace failed DMs back to original message
- ✅ Understand end-to-end latency (ingestion → delivery)
- ✅ Correlate logs/metrics/traces in Grafana
- ✅ Debug multi-stage failures

**Success Criteria:**
- Trace ID propagates: collector → worker → persist → broadcast → DM
- Grafana shows trace visualization
- Can click from log entry to trace
- Can see span duration for each stage

**Files to Create/Modify:**
- `observability/tempo/tempo.yaml`
- `observability/tempo/otel-collector.yaml`
- `docker-compose.yml` (add tempo, otel-collector)
- `TutorDexAggregator/collector.py` (add trace context)
- `TutorDexAggregator/workers/extract_worker.py` (propagate trace)
- `TutorDexAggregator/supabase_persist.py` (propagate trace)

**Dependencies:**
- Tempo (Grafana tracing backend)
- OpenTelemetry Collector
- `opentelemetry-api`, `opentelemetry-sdk` (already in requirements.txt)

---

#### ~~**Task 4: Break Up `supabase_persist.py`**~~ ✅ **COMPLETED**

**Priority:** 7 (from audit)  
**Status:** ✅ **ALREADY COMPLETE** (discovered 2026-01-13)  
**Original Effort Estimate:** 2-3 weeks  
**Impact:** HIGH - Successfully delivered

**Problem (Historical):** The `supabase_persist.py` file was 1,311 lines with complex merge logic, geo-enrichment, and side-effects all embedded together.

**Solution (Implemented):** The file has been successfully refactored into focused service modules.

**Actual Implementation:**

```
✅ Completed Refactoring:
  supabase_persist.py: 1311 lines → 416 lines (68% reduction)
  
  Extracted Services:
    ├── services/row_builder.py (491 lines)
    │   └── Assignment row construction and validation
    ├── services/merge_policy.py (148 lines)
    │   └── Conservative merge logic with quality-based overwrites
    ├── services/geocoding_service.py (101 lines)
    │   └── Postal code → coordinates resolution
    ├── services/event_publisher.py (71 lines)
    │   └── Broadcast/DM/duplicate detection orchestration
    └── services/persistence_operations.py (71 lines)
        └── Agency upserts and helper operations
```

**Current Architecture:**

The `supabase_persist.py` file now serves as a thin orchestration layer:
- Imports focused service modules
- Delegates row building to `row_builder.py`
- Delegates merge logic to `merge_policy.py`
- Delegates geocoding to `geocoding_service.py`
- Delegates side-effects to `event_publisher.py`

**Success Criteria Achieved:**
- ✅ Main file reduced to 416 lines (originally 1311)
- ✅ Each service module < 500 lines
- ✅ Clear separation of concerns
- ✅ Merge logic isolated in dedicated module
- ✅ Geo-enrichment extracted to standalone service
- ✅ Side-effects (broadcast/DM/duplicate) decoupled

**Files:**
- `TutorDexAggregator/supabase_persist.py` (416 lines) - orchestration
- `TutorDexAggregator/services/row_builder.py` (491 lines)
- `TutorDexAggregator/services/merge_policy.py` (148 lines)
- `TutorDexAggregator/services/geocoding_service.py` (101 lines)
- `TutorDexAggregator/services/event_publisher.py` (71 lines)
- `TutorDexAggregator/services/persistence_operations.py` (71 lines)

**This task is complete and can be removed from the remaining work list.**

---

### **Phase 3: Additional Improvements** (Ongoing)

These are smaller improvements that can be done opportunistically.

---

#### **Task 5: Add Assignment State Machine**

**Effort:** 2-3 days  
**Impact:** MEDIUM  
**Risk:** Low

**Problem:** Assignment status is nullable, transitions not enforced. Code can jump from open → deleted without close.

**Solution:** Add explicit state machine with enforced transitions.

```python
# New file: TutorDexAggregator/domain/assignment_status.py
from enum import Enum
from typing import Optional

class AssignmentStatus(str, Enum):
    PENDING = "pending"      # Just ingested, not yet validated
    OPEN = "open"            # Active, visible to tutors
    CLOSED = "closed"        # Filled or expired
    HIDDEN = "hidden"        # Hidden by admin/tutor
    DELETED = "deleted"      # Soft-deleted
    EXPIRED = "expired"      # Past expiry date

class StatusTransitionError(Exception):
    """Raised when invalid status transition is attempted"""
    pass

class AssignmentStateMachine:
    """Enforces valid status transitions"""
    
    VALID_TRANSITIONS = {
        AssignmentStatus.PENDING: [AssignmentStatus.OPEN, AssignmentStatus.DELETED],
        AssignmentStatus.OPEN: [AssignmentStatus.CLOSED, AssignmentStatus.HIDDEN, AssignmentStatus.EXPIRED, AssignmentStatus.DELETED],
        AssignmentStatus.CLOSED: [AssignmentStatus.OPEN, AssignmentStatus.DELETED],  # Can reopen
        AssignmentStatus.HIDDEN: [AssignmentStatus.OPEN, AssignmentStatus.DELETED],
        AssignmentStatus.EXPIRED: [AssignmentStatus.CLOSED, AssignmentStatus.DELETED],
        AssignmentStatus.DELETED: [],  # Terminal state
    }
    
    @classmethod
    def can_transition(cls, from_status: AssignmentStatus, to_status: AssignmentStatus) -> bool:
        """Check if transition is valid"""
        return to_status in cls.VALID_TRANSITIONS.get(from_status, [])
    
    @classmethod
    def transition(cls, from_status: AssignmentStatus, to_status: AssignmentStatus) -> AssignmentStatus:
        """Execute transition (raises if invalid)"""
        if not cls.can_transition(from_status, to_status):
            raise StatusTransitionError(
                f"Invalid transition: {from_status} → {to_status}"
            )
        return to_status
```

**Integration:**

```python
# In TutorDexBackend/app.py (admin endpoint to close assignment)
@app.post("/admin/assignments/{assignment_id}/close")
async def close_assignment(assignment_id: str):
    assignment = fetch_assignment(assignment_id)
    
    # Enforce state machine
    new_status = AssignmentStateMachine.transition(
        from_status=AssignmentStatus(assignment["status"]),
        to_status=AssignmentStatus.CLOSED
    )
    
    # Update status
    update_assignment_status(assignment_id, new_status)
    return {"status": "ok"}
```

**Benefits:**
- ✅ Prevent invalid transitions
- ✅ Clear documentation of lifecycle
- ✅ Easier to add new states

---

#### **Task 6: Add Business Metrics**

**Effort:** 1-2 days  
**Impact:** MEDIUM  
**Risk:** Low

**Problem:** Limited business-level metrics. No "assignments per hour", "tutors with DM subscriptions", "average time-to-match".

**Solution:** Add business metrics to Prometheus.

```python
# TutorDexAggregator/observability_metrics.py (add to existing file)
from prometheus_client import Histogram, Gauge

# Business metrics
assignments_per_hour = Gauge(
    "assignments_created_per_hour",
    "Number of assignments created in last hour",
)

tutors_with_active_dms = Gauge(
    "tutors_with_active_dm_subscriptions",
    "Number of tutors with active DM subscriptions in Redis",
)

time_to_match = Histogram(
    "assignment_time_to_match_seconds",
    "Time from assignment creation to first match",
    buckets=[60, 300, 600, 1800, 3600, 7200, 14400],  # 1min to 4hours
)

# Update in various places:
# - assignments_per_hour: increment on persist
# - tutors_with_active_dms: update on profile save
# - time_to_match: record when DM sent
```

**Grafana Panels:**

```yaml
# Add to tutordex_overview.json
- title: "Assignments per Hour"
  type: graph
  targets:
    - expr: rate(assignments_created_per_hour[1h])

- title: "Active Tutors"
  type: stat
  targets:
    - expr: tutors_with_active_dm_subscriptions

- title: "Time to First Match (p95)"
  type: graph
  targets:
    - expr: histogram_quantile(0.95, assignment_time_to_match_seconds)
```

---

#### **Task 7: Add Rate Limiting on Public Endpoints**

**Effort:** 1 day  
**Impact:** MEDIUM  
**Risk:** Low

**Problem:** `/assignments` endpoint is public, no rate limit. Scrapers/competitors can hammer endpoint.

**Solution:** Add rate limiting middleware.

```python
# TutorDexBackend/middleware/rate_limit.py
from fastapi import Request, HTTPException
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)

# In app.py
from middleware.rate_limit import limiter, RateLimitExceeded

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Apply to endpoints
@app.get("/assignments")
@limiter.limit("100/minute")  # 100 requests per minute per IP
async def list_assignments(request: Request):
    # ... existing code
```

**Configuration:**

```python
# Different limits for different endpoints
PUBLIC_ENDPOINTS = "100/minute"
AUTH_ENDPOINTS = "300/minute"
ADMIN_ENDPOINTS = "1000/minute"
```

**Dependencies:**
- `slowapi` (FastAPI-compatible rate limiting)

---

#### **Task 8: Consolidate Supabase Clients**

**Effort:** 2-3 days  
**Impact:** LOW-MEDIUM  
**Risk:** Low

**Problem:** Three separate Supabase client implementations (supabase_persist.py, supabase_store.py, supabase_raw_persist.py) with duplicated auth header injection.

**Solution:** Create single SupabaseClient class.

```python
# New file: shared/supabase_client.py
import requests
from typing import Dict, Any, Optional, List

class SupabaseClient:
    """
    Unified Supabase PostgREST client.
    Handles auth, error handling, retries.
    """
    
    def __init__(self, url: str, key: str, timeout: int = 30):
        self.url = url
        self.key = key
        self.timeout = timeout
    
    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
    
    def select(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        columns: str = "*",
        limit: Optional[int] = None
    ) -> List[Dict]:
        """SELECT query with filters"""
        url = f"{self.url}/rest/v1/{table}"
        params = {"select": columns}
        if filters:
            for key, value in filters.items():
                params[key] = f"eq.{value}"
        if limit:
            params["limit"] = limit
        
        response = requests.get(url, headers=self._headers(), params=params, timeout=self.timeout)
        response.raise_for_status()
        return response.json()
    
    def insert(self, table: str, data: Dict[str, Any]) -> Dict:
        """INSERT single row"""
        url = f"{self.url}/rest/v1/{table}"
        response = requests.post(url, headers=self._headers(), json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()[0] if response.json() else {}
    
    def upsert(self, table: str, data: Dict[str, Any], on_conflict: str = "id") -> Dict:
        """UPSERT single row"""
        headers = self._headers()
        headers["Prefer"] = f"resolution=merge-duplicates,return=representation"
        url = f"{self.url}/rest/v1/{table}?on_conflict={on_conflict}"
        response = requests.post(url, headers=headers, json=data, timeout=self.timeout)
        response.raise_for_status()
        return response.json()[0] if response.json() else {}
    
    def rpc(self, function: str, params: Dict[str, Any]) -> Any:
        """Call RPC function"""
        url = f"{self.url}/rest/v1/rpc/{function}"
        response = requests.post(url, headers=self._headers(), json=params, timeout=self.timeout)
        
        # Check for HTTP 300 (audit Priority 2)
        from supabase_env import check_rpc_response
        check_rpc_response(response, function)
        
        return response.json()
```

**Migration:**
- Replace all raw `requests.post()` calls with `SupabaseClient` methods
- Keep existing behavior (same errors, same retries)

---

#### **Task 9: Document External Dependencies**

**Effort:** 1 day  
**Impact:** LOW  
**Risk:** None

**Problem:** Supabase instance required but not included/versioned. LLM API assumed available. No `scripts/bootstrap.sh`.

**Solution:** Document and version all dependencies.

```bash
# New file: scripts/bootstrap.sh
#!/bin/bash
# Bootstrap all TutorDex dependencies for local development

set -e

echo "🚀 Bootstrapping TutorDex development environment..."

# Check prerequisites
command -v docker >/dev/null 2>&1 || { echo "❌ Docker required"; exit 1; }
command -v docker-compose >/dev/null 2>&1 || { echo "❌ docker-compose required"; exit 1; }

# Start Supabase (self-hosted)
echo "📦 Starting Supabase..."
cd supabase
docker-compose up -d
cd ..

# Wait for Supabase to be ready
echo "⏳ Waiting for Supabase..."
until curl -s http://localhost:54321/rest/v1/ > /dev/null; do
  sleep 2
done
echo "✅ Supabase ready"

# Apply migrations
echo "📝 Applying database migrations..."
python scripts/migrate.py

# Start Redis
echo "📦 Starting Redis..."
docker run -d --name tutordex-redis -p 6379:6379 redis:7-alpine

# Start LLM API (LM Studio)
echo "💡 LLM API should be running at http://localhost:1234"
echo "   Start LM Studio manually if not running"

# Start observability stack
echo "📊 Starting observability stack..."
cd observability
docker-compose up -d
cd ..

echo "✅ Bootstrap complete!"
echo ""
echo "Next steps:"
echo "  1. Copy .env.example to .env in each service"
echo "  2. Start services: docker-compose up"
echo "  3. Access Grafana: http://localhost:3300"
```

**Documentation:**

```markdown
# DEPENDENCIES.md

## External Dependencies

### Required Services

1. **Supabase (PostgreSQL + PostgREST)**
   - Version: 2.0+ (self-hosted)
   - Required for: All data persistence
   - Bootstrap: `cd supabase && docker-compose up`
   - Schema version: Tracked in `schema_migrations` table

2. **Redis**
   - Version: 7.0+
   - Required for: Tutor profiles, rate limiting, caching
   - Bootstrap: `docker run -d -p 6379:6379 redis:7-alpine`

3. **LLM API (LM Studio or compatible)**
   - Model: Qwen 2.5 7B or similar
   - Required for: Assignment parsing
   - URL: http://localhost:1234 (configurable)
   - Note: Optional for some workflows (deterministic extraction works without LLM)

4. **Firebase (Cloud)**
   - Service: Authentication
   - Required for: Website user auth
   - Setup: Create project at console.firebase.google.com

### Optional Services

1. **Tempo** (distributed tracing)
   - Version: latest
   - Required for: End-to-end tracing
   - Bootstrap: `cd observability/tempo && docker-compose up`

2. **Sentry** (error reporting)
   - Service: Cloud or self-hosted
   - Required for: Frontend error reporting
   - Setup: Create project at sentry.io (free tier sufficient)
```

---

#### **Task 10: Add Pre-commit Hook for Large Files**

**Effort:** 1 hour  
**Impact:** LOW  
**Risk:** None

**Problem:** Files over 500 lines require justification. No automated check.

**Solution:** Add pre-commit hook.

```bash
# New file: .githooks/pre-commit
#!/bin/bash
# Pre-commit hook: warn on large files (>500 lines)

RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔍 Checking for large files..."

# Check Python files
large_files=$(find . -name "*.py" -not -path "./.git/*" -not -path "./venv/*" | xargs wc -l | awk '$1 > 500 {print $2, $1}')

if [ -n "$large_files" ]; then
  echo -e "${YELLOW}⚠️  Warning: Large files detected:${NC}"
  echo "$large_files" | while read -r file lines; do
    echo -e "  ${file}: ${RED}${lines} lines${NC}"
  done
  echo ""
  echo "Files over 500 lines should have a justification comment at the top."
  echo "Consider refactoring large files into smaller modules."
  echo ""
  read -p "Continue with commit? (y/n) " -n 1 -r
  echo
  if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    exit 1
  fi
fi

exit 0
```

**Install:**

```bash
# In README.md, add to setup instructions
git config core.hooksPath .githooks
chmod +x .githooks/pre-commit
```

---

## Summary of Remaining Work

### High Priority (Next 2 Weeks)
1. ✅ **Task 1**: HTTP Integration Tests (2-3 days) - Critical for refactoring confidence
2. ✅ **Task 2**: Consolidate Environment Config (2-3 days) - Reduces operational errors

### Medium Priority (Next Month)
3. ✅ **Task 3**: End-to-End Tracing (1 week) - Better debugging
4. ✅ **Task 4**: Break Up supabase_persist.py (2-3 weeks) - Major complexity reduction

### Medium Priority (Next 1-2 Weeks) ✅ **Task 4 Complete!**
3. Task 3: End-to-End Tracing (1 week)
4. ~~Task 4: Break Up supabase_persist.py (2-3 weeks)~~ ✅ **COMPLETED**

### Low Priority (Ongoing)
5. Task 5: Assignment State Machine (2-3 days)
6. Task 6: Business Metrics (1-2 days)
7. Task 7: Rate Limiting (1 day)
8. Task 8: Consolidate Supabase Clients (2-3 days)
9. Task 9: Document Dependencies (1 day)
10. Task 10: Pre-commit Hook (1 hour)

---

## Total Estimated Effort

- **High Priority**: 4-6 days (Tasks 1-2)
- **Medium Priority**: 1 week (Task 3 only - Task 4 complete)
- **Low Priority**: 1-2 weeks (Tasks 5-10)

**Total: 2-4 weeks** of focused work to complete all remaining audit recommendations.

**Note:** Original estimate was 5-7 weeks, but Task 4 (supabase_persist refactor, estimated 2-3 weeks) has been completed, reducing remaining work by ~3 weeks.

---

## References

- **Full Audit**: `docs/CODEBASE_QUALITY_AUDIT_2026-01.md`
- **Quick Actions**: `docs/AUDIT_QUICK_ACTIONS.md`
- **Completed Priorities**: `docs/IMPLEMENTATION_PRIORITIES_1-3.md`
- **Next Milestones**: `docs/NEXT_MILESTONES.md`

---

**Document Status:** Active  
**Last Updated:** 2026-01-13  
**Next Review:** After completing Task 3 (End-to-End Tracing)
