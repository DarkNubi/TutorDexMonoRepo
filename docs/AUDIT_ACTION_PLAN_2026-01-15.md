# Codebase Quality Audit - Action Plan (January 15, 2026)

**Source:** [CODEBASE_QUALITY_AUDIT_2026-01-15.md](CODEBASE_QUALITY_AUDIT_2026-01-15.md)  
**Date:** January 15, 2026  
**Status:** 🔴 **IMMEDIATE ACTION REQUIRED**

---

## Executive Summary

The January 15, 2026 audit reveals a codebase in **good health** overall, with significant improvements from the 16 completed priorities. However, **three critical risks** have emerged that require immediate attention:

1. **Supabase Client Triplication** - 3 incompatible implementations causing maintenance burden
2. **Silent Failure Epidemic** - 120+ swallowed exceptions hiding production issues
3. **Untested Critical Logic** - Matching algorithm, worker orchestration, frontend have zero tests

**Estimated Cost:** 2-3 weeks to address critical issues  
**Expected ROI:** 5× faster incident resolution, 3× fewer production bugs

---

## 🔴 Critical Actions (This Week)

### Priority 1: Fix Security Vulnerabilities (1 day)

**Problem:** Unpinned dependencies with known CVEs expose production system

**Actions:**
```bash
# 1. Pin json-repair or remove it
# TutorDexAggregator/requirements.txt
json-repair==0.25.0  # Add version

# 2. Upgrade requests to patch CVEs
# TutorDexBackend/requirements.txt
# TutorDexAggregator/requirements.txt
requests>=2.31.0  # Was: 2.28.0

# 3. Add pip audit to CI
# .github/workflows/security-check.yml
name: Security Scan
on: [push, pull_request]
jobs:
  audit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - run: pip install pip-audit
      - run: pip-audit -r TutorDexBackend/requirements.txt
      - run: pip-audit -r TutorDexAggregator/requirements.txt
```

**Success Criteria:**
- ✅ All dependencies have pinned versions
- ✅ No known CVEs in production
- ✅ CI fails on security vulnerabilities

**Owner:** DevOps / Senior Engineer  
**Due Date:** January 17, 2026 (2 days)

---

### Priority 2: Add Matching Algorithm Tests (1 day)

**Problem:** Business-critical matching logic (293 lines) has ZERO tests

**Actions:**
1. Create `tests/test_matching_algorithm.py`
2. Test cases to cover:
   - Subject/level matching with scoring
   - Distance-based filtering (5km radius)
   - Rate range validation
   - Edge cases: missing fields, malformed input
   - DM recipient limiting logic
3. Mock Redis and Supabase dependencies

**Test Outline:**
```python
# tests/test_matching_algorithm.py
import pytest
from TutorDexBackend.matching import match_from_payload

class TestMatchingAlgorithm:
    def test_exact_subject_level_match(self):
        # Tutor wants Primary Math
        # Assignment is Primary Math
        # Should match with high score
        pass

    def test_distance_filter_5km(self):
        # Tutor at postal 123456
        # Assignment 3km away → match
        # Assignment 7km away → no match
        pass

    def test_rate_range_validation(self):
        # Tutor wants $40-60/hr
        # Assignment offers $50/hr → match
        # Assignment offers $20/hr → no match
        pass

    def test_missing_tutor_coords_skips_distance(self):
        # Tutor has no postal code
        # Should match without distance filter
        pass

    def test_dm_max_recipients_limit(self):
        # 100 tutors match
        # Should return only DM_MAX_RECIPIENTS
        pass
```

**Success Criteria:**
- ✅ 20+ test cases covering all branches
- ✅ Tests pass with mocked dependencies
- ✅ Code coverage >80% for `matching.py`

**Owner:** Backend Engineer  
**Due Date:** January 17, 2026 (2 days)

---

### Priority 3: Enable Automated Security Scanning (4 hours)

**Problem:** No automated vulnerability detection; manual audits miss issues

**Actions:**
1. Add Dependabot configuration
2. Enable npm audit in CI
3. Configure Snyk or GitHub Advanced Security

**Implementation:**
```yaml
# .github/dependabot.yml
version: 2
updates:
  - package-ecosystem: "pip"
    directory: "/TutorDexBackend"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5

  - package-ecosystem: "pip"
    directory: "/TutorDexAggregator"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5

  - package-ecosystem: "npm"
    directory: "/TutorDexWebsite"
    schedule:
      interval: "weekly"
    open-pull-requests-limit: 5
```

```yaml
# .github/workflows/firebase-hosting.yml (update)
# Remove --no-audit flag
- run: npm ci  # Was: npm ci --no-audit --no-fund
```

**Success Criteria:**
- ✅ Dependabot PRs created weekly
- ✅ npm audit runs in CI
- ✅ Security alerts surface in GitHub

**Owner:** DevOps / Senior Engineer  
**Due Date:** January 16, 2026 (1 day)

---

## 🟡 High-Priority Actions (Next 2 Weeks)

### Priority 4: Consolidate Supabase Clients (1 week)

**Problem:** 3 incompatible implementations → 3× maintenance burden

**Current State:**
- `shared/supabase_client.py` (450 lines) - "official" client
- `TutorDexAggregator/utils/supabase_client.py` (100+ lines) - duplicate
- `TutorDexBackend/supabase_store.py` (649 lines) - most used, incompatible

**Action Plan:**

**Phase 1: Audit (Day 1)**
1. Document all method signatures across 3 clients
2. Identify API differences (prefer, extra_headers, etc.)
3. List all call sites in codebase

**Phase 2: Design (Day 2)**
1. Decide on unified API (recommend: extend `shared/supabase_client.py`)
2. Add missing methods to shared client
3. Write migration guide

**Phase 3: Backend Migration (Days 3-4)**
1. Update `TutorDexBackend/supabase_store.py` to use shared client
2. Refactor 649 lines to adapter pattern if needed
3. Update all backend tests

**Phase 4: Aggregator Migration (Days 5-6)**
1. Update `TutorDexAggregator/` to use shared client
2. Delete `TutorDexAggregator/utils/supabase_client.py`
3. Update all aggregator tests

**Phase 5: Cleanup (Day 7)**
1. Delete duplicates
2. Update documentation
3. Run full test suite

**Success Criteria:**
- ✅ Single Supabase client used everywhere
- ✅ All tests pass
- ✅ No duplicate code

**Owner:** Senior Backend Engineer  
**Due Date:** January 24, 2026 (1 week)

---

### Priority 5: Replace Runtime Singletons (1 week)

**Problem:** Global mutable state makes testing hard, causes import order bugs

**Current State:**
```python
# TutorDexBackend/runtime.py
store = RedisStore(...)  # Global singleton
sb = SupabaseStore(...)  # Initialized at import time
cfg = load_backend_config()  # Env vars read at import
```

**Action Plan:**

**Phase 1: Create DI Container (Days 1-2)**
```python
# TutorDexBackend/container.py
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    config = providers.Singleton(load_backend_config)
    
    redis_store = providers.Singleton(
        RedisStore,
        config=config.provided.redis
    )
    
    supabase_store = providers.Singleton(
        SupabaseStore,
        config=config.provided.supabase
    )
    
    auth_service = providers.Factory(
        AuthService,
        config=config
    )
```

**Phase 2: Update Routes (Days 3-5)**
```python
# TutorDexBackend/routes/assignments_routes.py
from fastapi import Depends
from TutorDexBackend.container import Container

container = Container()

@router.get("/assignments")
async def list_assignments(
    store: SupabaseStore = Depends(container.supabase_store)
):
    # Use injected store instead of global
    pass
```

**Phase 3: Update Tests (Days 6-7)**
```python
# tests/test_backend_api.py
def test_list_assignments():
    container = Container()
    container.supabase_store.override(Mock())  # Easy mocking
    
    client = TestClient(app)
    response = client.get("/assignments")
    assert response.status_code == 200
```

**Success Criteria:**
- ✅ No global singletons
- ✅ All tests use dependency injection
- ✅ No import order dependencies

**Owner:** Senior Backend Engineer  
**Due Date:** January 31, 2026 (2 weeks)

---

### Priority 6: Fix Silent Failures (1 week)

**Problem:** 120+ `except Exception: pass` hide production issues

**Action Plan:**

**Phase 1: Audit (Day 1)**
1. Find all swallowed exceptions:
   ```bash
   grep -r "except Exception:" TutorDexBackend TutorDexAggregator shared | wc -l
   ```
2. Categorize by severity (critical path vs logging)
3. Prioritize files with most violations

**Phase 2: Define Error Strategy (Day 1)**
```python
# shared/exceptions.py
class TutorDexError(Exception):
    """Base exception for all TutorDex errors"""
    pass

class DataAccessError(TutorDexError):
    """Database/API access failures"""
    pass

class ValidationError(TutorDexError):
    """Data validation failures"""
    pass

class ExternalServiceError(TutorDexError):
    """External API failures (LLM, Telegram, etc.)"""
    pass
```

**Phase 3: Replace Broad Catches (Days 2-6)**

**High-Priority Files:**
1. `TutorDexBackend/supabase_store.py` (15+ violations)
2. `TutorDexAggregator/supabase_persist_impl.py` (7+ violations)
3. `TutorDexAggregator/delivery/broadcast_client.py` (12+ violations)
4. `shared/supabase_client.py` (5+ violations)

**Pattern:**
```python
# BEFORE (silent failure)
try:
    result = client.get(...)
except Exception:
    return []  # Silent failure

# AFTER (explicit error handling)
try:
    result = client.get(...)
except RequestException as e:
    logger.error("Supabase GET failed", exc_info=e, extra={
        "table": "assignments",
        "request_id": request_id
    })
    raise DataAccessError(f"Failed to fetch assignments: {e}") from e
```

**Phase 4: Add Alerting (Day 7)**
```python
# observability_metrics.py
error_counter = Counter(
    "tutordex_errors_total",
    "Total errors by type",
    ["error_type", "component"]
)

# Usage
except DataAccessError as e:
    error_counter.labels(
        error_type="data_access",
        component="supabase_store"
    ).inc()
    raise
```

**Success Criteria:**
- ✅ No bare `except Exception:` without re-raise
- ✅ All errors logged with context
- ✅ Alerts configured for critical errors

**Owner:** Backend + Aggregator Engineers  
**Due Date:** January 31, 2026 (2 weeks)

---

## 🔵 Medium-Priority Actions (Next Month)

### Priority 7: Add Frontend Testing (1 week)

**Scope:** TutorDexWebsite (currently 0 tests)

**Actions:**
1. Set up Vitest + React Testing Library
2. Test auth flows (sign-in, sign-up, token refresh)
3. Test assignment filtering and display
4. Test profile management

**Estimated Lines of Test Code:** 1,500-2,000 lines  
**Owner:** Frontend Engineer  
**Due Date:** February 7, 2026

---

### Priority 8: Extract Business Logic (2 weeks)

**Scope:** Separate business logic from data access

**Files to Refactor:**
1. `TutorDexBackend/supabase_store.py` (649 lines → 300 lines)
2. `TutorDexAggregator/supabase_persist_impl.py` (416 lines → 200 lines)

**Owner:** Senior Engineer  
**Due Date:** February 14, 2026

---

### Priority 9: Add Missing Observability (1 week)

**Gaps:**
1. Matching algorithm detailed traces
2. DM delivery success/failure metrics
3. Frontend custom event tracking
4. Error correlation with request IDs

**Owner:** DevOps + Engineers  
**Due Date:** February 7, 2026

---

## 📊 Success Metrics

### Before (January 15, 2026)
- Feature delivery: 2-4 days (experienced dev)
- Incident resolution: 2-4 hours
- Test coverage: ~60% (critical paths missing)
- Known CVEs: 4+ (requests, json-repair, etc.)
- Security scanning: Manual only

### After (February 15, 2026)
- Feature delivery: 1-2 days (confidence from tests)
- Incident resolution: 30-60 minutes (error visibility)
- Test coverage: >80% (including matching, frontend)
- Known CVEs: 0 (automated scanning + Dependabot)
- Security scanning: Automated weekly

### ROI
- **5× faster incident resolution** (error context + observability)
- **3× fewer production bugs** (test coverage + explicit errors)
- **2× faster onboarding** (consolidated clients + DI)
- **50% less maintenance** (1 Supabase client instead of 3)

---

## 🎯 Tracking & Accountability

### Week 1 (Jan 15-19)
- [ ] Priority 1: Pin dependencies + security scan (Owner: ________)
- [ ] Priority 2: Add matching tests (Owner: ________)
- [ ] Priority 3: Enable Dependabot (Owner: ________)

### Week 2 (Jan 20-26)
- [ ] Priority 4: Consolidate Supabase clients (Owner: ________)

### Week 3 (Jan 27 - Feb 2)
- [ ] Priority 5: Replace runtime singletons (Owner: ________)
- [ ] Priority 6: Fix silent failures (Owner: ________)

### Week 4 (Feb 3-9)
- [ ] Priority 7: Add frontend testing (Owner: ________)
- [ ] Priority 9: Add observability (Owner: ________)

### Week 5-6 (Feb 10-16)
- [ ] Priority 8: Extract business logic (Owner: ________)

---

## 📝 Review Cadence

- **Daily standups:** Progress on weekly priorities
- **Weekly review:** Completed priorities, blockers, adjustments
- **Bi-weekly demo:** Show test coverage improvements, reduced errors
- **Monthly retrospective:** Audit progress, update action plan

---

## 🚨 Red Flags (Stop and Escalate)

If any of these occur, **stop work** and escalate:

1. **Test coverage drops** below 60%
2. **New CVE** discovered in production dependencies
3. **Production incident** caused by silent failure
4. **Supabase client divergence** causes integration failure
5. **CI/CD pipeline** breaks for >24 hours

---

## 📖 Resources

- **Full Audit Report:** [CODEBASE_QUALITY_AUDIT_2026-01-15.md](CODEBASE_QUALITY_AUDIT_2026-01-15.md)
- **Previous Audit:** [CODEBASE_QUALITY_AUDIT_2026-01.md](CODEBASE_QUALITY_AUDIT_2026-01.md)
- **Completed Priorities:** [AUDIT_CHECKLIST.md](AUDIT_CHECKLIST.md)
- **System Architecture:** [SYSTEM_INTERNAL.md](SYSTEM_INTERNAL.md)

---

**Last Updated:** January 15, 2026  
**Next Review:** January 22, 2026 (weekly)
