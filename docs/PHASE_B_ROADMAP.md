# Phase B — Critical Risk Mitigation — Implementation Roadmap

**Date:** January 16, 2026  
**Status:** ⏳ READY FOR IMPLEMENTATION  
**Estimated Effort:** 2-3 weeks  
**Prerequisites:** Phases D and A complete ✅

---

## Executive Summary

Phase B addresses the 3 critical risks identified in the January 15, 2026 audit:
1. **Supabase client triplication** (3 incompatible implementations)
2. **Silent failure epidemic** (120+ `except Exception: pass` instances)
3. **Untested critical business logic** (matching algorithm, worker orchestration, frontend)

This document provides a detailed implementation roadmap with specific file-level actions, acceptance criteria, and validation steps.

---

## Decision Record

Based on user approval (comment #3669069302), proceeding with recommended answers:

**Question 1: API Breaking Changes for Supabase Consolidation**
- **Decision**: Maintain backward compatibility via wrapper methods
- **Rationale**: Minimizes migration risk, allows gradual rollout
- **Approach**: Keep existing APIs, deprecate old methods with warnings

**Question 2: Code Coverage Targets**
- **Decision**: 80% critical paths, 50% non-critical
- **Rationale**: Balances test investment with practical coverage
- **Critical paths**: matching.py, worker orchestration, persistence operations
- **Non-critical**: utility functions, formatters, helper methods

**Question 3: Frontend Testing Scope**
- **Decision**: Infrastructure + 10 basic tests
- **Rationale**: Establishes foundation without over-investing initially
- **Scope**: Test setup, utility functions, basic component rendering
- **Future**: Expand as needed based on bug patterns

---

## Task B1: Consolidate Supabase Client Implementations

### Current State Analysis

**Three Implementations Found:**

1. **`shared/supabase_client.py`** (450 lines)
   - ✅ Most complete: RPC 300 detection, retry logic, connection pooling
   - ✅ Error handling with custom exceptions
   - ✅ Proper timeout configuration
   - ✅ Session management
   - **Status**: Target consolidation point

2. **`TutorDexAggregator/utils/supabase_client.py`** (114 lines)
   - ❌ No retry logic
   - ❌ No RPC 300 detection
   - ✅ Simple REST client with GET/POST/PATCH
   - ✅ Has `coerce_rows()` helper function
   - **Status**: Should be removed, migrate to shared

3. **`TutorDexBackend/supabase_store.py`** (649 lines)
   - ❌ Embedded client (lines 33-76)
   - ✅ Has `extra_headers` support
   - ✅ High-level `SupabaseStore` wrapper with business methods
   - **Status**: Keep wrapper, migrate client to shared

**Usage Analysis:**
```bash
# Aggregator imports (4 files)
TutorDexAggregator/services/persistence_operations.py
TutorDexAggregator/services/event_publisher.py  
TutorDexAggregator/supabase_persist_impl.py

# Backend usage
TutorDexBackend/supabase_store.py (embedded client)
TutorDexBackend/runtime.py (creates SupabaseStore instance)
```

### Implementation Plan

#### Step 1: Extend Shared Client (2 days)

**File**: `shared/supabase_client.py`

**Actions**:
1. Add `extra_headers` parameter to all request methods (for Backend compatibility)
2. Add `coerce_rows()` helper function (from Aggregator client)
3. Ensure `prefer` parameter works correctly
4. Add compatibility methods for any missing Aggregator/Backend methods

**Example Changes**:
```python
# Add to SupabaseClient class
def get(self, path: str, *, timeout: int = None, prefer: Optional[str] = None, 
        extra_headers: Optional[Dict[str, str]] = None) -> requests.Response:
    """Execute GET request with optional extra headers."""
    headers = self._headers(extra_headers)
    if prefer:
        headers["Prefer"] = prefer
    timeout = timeout or self.config.timeout
    return self.session.get(self._url(path), headers=headers, timeout=timeout)

# Add helper function at module level
def coerce_rows(resp: requests.Response) -> List[Dict[str, Any]]:
    """Extract list of rows from Supabase REST response."""
    try:
        data = resp.json()
    except Exception:
        return []
    return data if isinstance(data, list) else []
```

**Validation**:
- All existing tests pass
- New methods have docstrings
- No breaking changes to existing shared client users

#### Step 2: Update Aggregator Imports (2 days)

**Files to Modify**:
1. `TutorDexAggregator/services/persistence_operations.py`
2. `TutorDexAggregator/services/event_publisher.py`
3. `TutorDexAggregator/supabase_persist_impl.py`

**Changes**:
```python
# OLD
from utils.supabase_client import SupabaseRestClient, coerce_rows
from TutorDexAggregator.utils.supabase_client import SupabaseRestClient, coerce_rows

# NEW
from shared.supabase_client import SupabaseClient as SupabaseRestClient, coerce_rows
```

**Compatibility Shim** (if needed):
```python
# In TutorDexAggregator/utils/supabase_client.py (before removal)
# Add deprecation warning
import warnings
warnings.warn(
    "TutorDexAggregator.utils.supabase_client is deprecated. "
    "Use shared.supabase_client instead.",
    DeprecationWarning,
    stacklevel=2
)

# Re-export from shared
from shared.supabase_client import SupabaseClient as SupabaseRestClient, coerce_rows
```

**Validation**:
- All Aggregator tests pass
- No import errors
- Deprecation warnings appear in logs

#### Step 3: Refactor Backend Store (3 days)

**File**: `TutorDexBackend/supabase_store.py`

**Approach**: Keep `SupabaseStore` wrapper, delegate to shared client

**Changes**:
```python
# At top of file
from shared.supabase_client import SupabaseClient, SupabaseConfig as SharedSupabaseConfig, coerce_rows

# Remove embedded SupabaseRestClient class (lines 33-76)

# Update SupabaseStore.__init__
class SupabaseStore:
    def __init__(self, cfg: Optional[SupabaseConfig] = None):
        self.cfg = cfg or load_supabase_config()
        
        # Create shared client with compatible config
        if self.cfg.enabled:
            shared_cfg = SharedSupabaseConfig(
                url=self.cfg.url,
                key=self.cfg.key,
                timeout=30,
                max_retries=3,
                enabled=True
            )
            self.client = SupabaseClient(shared_cfg)
        else:
            self.client = None
    
    # Update all methods to use shared client
    # Example:
    def _get(self, path: str, **kwargs) -> requests.Response:
        if not self.client:
            raise ValueError("Supabase not enabled")
        return self.client.get(path, **kwargs)
```

**Validation**:
- All backend tests pass
- Backend API endpoints work
- Health checks pass

#### Step 4: Remove Duplicate Client (1 day)

**File to Remove**: `TutorDexAggregator/utils/supabase_client.py`

**Prerequisites**:
- All imports updated
- All tests passing
- No references to old client

**Actions**:
1. Search for any remaining imports: `grep -r "TutorDexAggregator.utils.supabase_client\|from utils.supabase_client"`
2. Update any found imports
3. Delete `TutorDexAggregator/utils/supabase_client.py`
4. Run full test suite

**Validation**:
- No import errors
- All 70+ tests pass
- No references to deleted file

#### Step 5: Documentation & ADR (1 day)

**Files to Create/Update**:
1. Create `docs/ADR-0001-SUPABASE-CLIENT-CONSOLIDATION.md`
2. Update `docs/SYSTEM_INTERNAL.md` (mention single client)
3. Update `.github/copilot-instructions.md`

**ADR Template**:
```markdown
# ADR-0001: Consolidate Supabase Client Implementations

**Date**: 2026-01-16
**Status**: Implemented

## Context
Three incompatible Supabase client implementations existed, causing:
- 3× maintenance burden for bug fixes
- Inconsistent error handling across services
- Divergent retry/timeout behavior

## Decision
Consolidate into single `shared/supabase_client.py` with:
- RPC 300 detection (audit Priority 2)
- Retry logic with exponential backoff
- Connection pooling
- Consistent error handling

## Consequences
**Positive**:
- Single source of truth
- Consistent behavior across services
- Easier to maintain and enhance

**Negative**:
- Migration effort (2-3 days per service)
- Temporary import complexity during transition

## Implementation
- Week 1: Extend shared client, add compatibility methods
- Week 2: Migrate Aggregator and Backend
- Week 3: Remove duplicates, validate, document
```

### Acceptance Criteria

- ✅ Only one Supabase client implementation exists (`shared/supabase_client.py`)
- ✅ All 70+ existing tests pass
- ✅ No import errors across codebase
- ✅ ADR document created
- ✅ Documentation updated
- ✅ No production regressions

### Estimated Effort

- **API Audit**: 0.5 days (completed in this analysis)
- **Extend Shared Client**: 2 days
- **Migrate Aggregator**: 2 days
- **Migrate Backend**: 3 days
- **Remove Duplicate**: 1 day
- **Documentation**: 1 day
- **Total**: 9.5 days (~2 weeks)

---

## Task B2: Fix Silent Failure Epidemic

### Current State Analysis

**Grep Results**:
```bash
grep -r "except.*:.*pass" --include="*.py" | wc -l
# Estimated: 120+ instances
```

**Categories**:
1. **Critical Path** (highest priority)
   - Supabase RPC calls
   - Persistence operations
   - Extraction pipeline steps
   - Validation logic

2. **Side Effects** (medium priority)
   - Broadcast delivery
   - DM sending
   - Click tracking
   - Analytics events

3. **Metric Recording** (lowest priority)
   - Prometheus counter increments
   - Timer recordings
   - Gauge updates

### Implementation Plan

#### Step 1: Inventory (1 day)

**Create**: `docs/SILENT_FAILURES_INVENTORY.md`

**Actions**:
1. Run: `grep -rn "except.*:.*pass" --include="*.py" TutorDexAggregator/ TutorDexBackend/ > silent_failures.txt`
2. Categorize each by severity
3. Identify proper fix for each

**Template**:
```markdown
| File | Line | Category | Current Code | Proposed Fix | Priority |
|------|------|----------|--------------|--------------|----------|
| supabase_persist_impl.py | 123 | Critical | except: pass | log + raise | HIGH |
| broadcast_assignments.py | 456 | Side-effect | except: pass | log + fallback | MEDIUM |
| metrics.py | 789 | Metric | except: pass | log warning | LOW |
```

#### Step 2: Fix Critical Paths (3 days)

**Pattern 1: Supabase RPC Failures**
```python
# BEFORE
try:
    result = client.rpc("some_function", {})
except Exception:
    pass  # Silent failure

# AFTER
try:
    result = client.rpc("some_function", {})
except Exception as e:
    logger.error(f"RPC some_function failed: {e}", exc_info=True)
    raise  # Re-raise for caller to handle
```

**Pattern 2: Persistence Failures**
```python
# BEFORE
try:
    persist_to_db(record)
except Exception:
    pass

# AFTER
try:
    persist_to_db(record)
except Exception as e:
    logger.error(f"Persistence failed for record {record.id}: {e}", exc_info=True)
    # Mark for retry or dead-letter queue
    mark_for_retry(record)
```

**Files to Fix** (Priority Order):
1. `TutorDexAggregator/supabase_persist_impl.py`
2. `TutorDexAggregator/workers/extract_worker_main.py`
3. `TutorDexBackend/supabase_store.py`
4. `TutorDexAggregator/hard_validator.py`

#### Step 3: Fix Side Effects (2 days)

**Pattern: Broadcast/DM Failures**
```python
# BEFORE
try:
    send_broadcast(message)
except Exception:
    pass

# AFTER
try:
    send_broadcast(message)
except Exception as e:
    logger.warning(f"Broadcast failed: {e}, writing to fallback", exc_info=True)
    write_to_fallback_file(message)
```

**Files to Fix**:
1. `TutorDexAggregator/broadcast_assignments_impl.py`
2. `TutorDexAggregator/dm_assignments_impl.py`
3. `TutorDexBackend/routes/track_routes.py`

#### Step 4: Fix Metric Recording (2 days)

**Pattern: Metric Failures**
```python
# BEFORE
try:
    metric_counter.inc()
except Exception:
    pass

# AFTER
try:
    metric_counter.inc()
except Exception as e:
    # Log at WARNING level (metrics shouldn't break app)
    logger.warning(f"Metric recording failed: {e}")
    # Optional: Track metric failures themselves
    if hasattr(self, '_metric_failure_counter'):
        try:
            self._metric_failure_counter.inc()
        except:
            pass  # Don't fail on failure tracking
```

**Files to Fix**:
- All files in `TutorDexAggregator/` and `TutorDexBackend/` with metric code

### Acceptance Criteria

- ✅ Zero `except Exception: pass` in critical paths
- ✅ All errors logged with context (file, line, error message)
- ✅ Fallback mechanisms in place for side effects
- ✅ Metric failures logged at WARNING level
- ✅ Error rate monitoring dashboard created
- ✅ All existing tests still pass

### Estimated Effort

- **Inventory**: 1 day
- **Fix Critical**: 3 days
- **Fix Side Effects**: 2 days
- **Fix Metrics**: 2 days
- **Dashboard**: 1 day
- **Total**: 9 days (~2 weeks)

---

## Task B3: Add Tests for Critical Business Logic

### Current State Analysis

**Untested Critical Paths**:
1. `TutorDexBackend/matching.py` (293 lines) - **0 tests**
2. `TutorDexAggregator/workers/extract_worker_main.py` - **0 orchestration tests**
3. `TutorDexWebsite/src/` - **No test infrastructure**

### Implementation Plan

#### Subtask 1: Matching Algorithm Tests (1 week)

**Create**: `tests/test_matching_comprehensive.py`

**Test Categories** (25+ tests):

1. **Subject/Level Matching** (8 tests)
   - Exact match (Primary Math → Primary Math)
   - Fuzzy match (Sec Math → Secondary Mathematics)
   - No match (Primary English → Secondary Math)
   - Missing subject handling
   - Missing level handling
   - Multiple subjects
   - Multiple levels
   - Case sensitivity

2. **Distance Filtering** (5 tests)
   - Within 5km radius
   - Outside 5km radius
   - Missing tutor postal code
   - Missing assignment postal code
   - Invalid postal code format

3. **Rate Range Validation** (4 tests)
   - Rate within range
   - Rate below range
   - Rate above range
   - Missing rate information

4. **DM Recipient Limiting** (3 tests)
   - Under limit (10 matches, limit 50)
   - Over limit (100 matches, limit 50)
   - Exactly at limit

5. **Score Calculation** (3 tests)
   - Perfect match score
   - Partial match score
   - Minimum match score

6. **Edge Cases** (2 tests)
   - Empty preferences
   - Malformed input

**Example Test**:
```python
import pytest
from unittest.mock import Mock, patch
from TutorDexBackend.matching import match_from_payload

class TestMatchingAlgorithm:
    def test_exact_subject_level_match_returns_high_score(self):
        """Tutor preferring Primary Math should match Primary Math assignment."""
        # Mock Redis store with tutor preferences
        mock_store = Mock()
        mock_store.get_all_tutors.return_value = [
            {
                "tutor_id": "alice",
                "chat_id": "123",
                "subjects": ["Mathematics"],
                "levels": ["Primary"],
                "postal_code": "123456"
            }
        ]
        
        # Assignment payload
        payload = {
            "parsed": {
                "learning_mode": {"mode": "Face-to-Face"},
            },
            "meta": {
                "signals": {
                    "ok": True,
                    "signals": {
                        "subjects": ["Mathematics"],
                        "levels": ["Primary"]
                    }
                }
            }
        }
        
        with patch('TutorDexBackend.matching.redis_store', mock_store):
            matches = match_from_payload(payload)
        
        assert len(matches) == 1
        assert matches[0]["tutor_id"] == "alice"
        assert matches[0]["score"] >= 5  # High score for exact match
    
    def test_distance_filter_excludes_tutors_beyond_5km(self):
        """Tutors more than 5km away should not match."""
        # ... test implementation
```

**Coverage Target**: 80% of `matching.py`

**Estimated Effort**: 5 days

#### Subtask 2: Worker Orchestration Tests (3 days)

**Create**: `tests/test_extract_worker_orchestration.py`

**Test Categories** (15+ tests):

1. **Job Claiming** (3 tests)
   - Successful claim
   - No jobs available
   - Concurrent claim handling

2. **Pipeline Execution** (4 tests)
   - Happy path (all steps succeed)
   - LLM failure fallback
   - Validation failure handling
   - Persistence failure retry

3. **Error Handling** (3 tests)
   - Transient errors (retry)
   - Permanent errors (mark failed)
   - Timeout handling

4. **Side Effects** (3 tests)
   - Broadcast triggered
   - DM triggered
   - Analytics recorded

5. **Oneshot Mode** (2 tests)
   - Oneshot enabled
   - Oneshot disabled

**Coverage Target**: 70% of worker orchestration

**Estimated Effort**: 3 days

#### Subtask 3: Frontend Test Infrastructure (2 days)

**Setup Vitest**:

1. **Install Dependencies**:
```bash
cd TutorDexWebsite
npm install --save-dev vitest @vitest/ui jsdom @testing-library/react @testing-library/jest-dom
```

2. **Create**: `TutorDexWebsite/vitest.config.js`
```javascript
import { defineConfig } from 'vitest/config'

export default defineConfig({
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './test/setup.js',
  },
})
```

3. **Create**: `TutorDexWebsite/test/setup.js`
```javascript
import '@testing-library/jest-dom'
```

4. **Update**: `TutorDexWebsite/package.json`
```json
{
  "scripts": {
    "test": "vitest",
    "test:ui": "vitest --ui",
    "test:coverage": "vitest --coverage"
  }
}
```

**Basic Tests** (10 tests):

**Create**: `TutorDexWebsite/test/formatters.test.js`
```javascript
import { describe, it, expect } from 'vitest'
import { formatRate, formatDistance, formatDate } from '../src/lib/assignmentFormatters'

describe('Assignment Formatters', () => {
  it('formats rate correctly', () => {
    expect(formatRate(50)).toBe('$50/hr')
    expect(formatRate(null)).toBe('N/A')
  })
  
  it('formats distance correctly', () => {
    expect(formatDistance(1.5)).toBe('1.5 km')
    expect(formatDistance(null)).toBe('-')
  })
  
  // ... more tests
})
```

**Coverage Target**: 50% of utility functions

**Estimated Effort**: 2 days

### Acceptance Criteria

- ✅ 40+ new tests added (25 matching + 15 worker + 10 frontend)
- ✅ All new tests pass
- ✅ Code coverage: matching.py >80%, worker >70%, frontend utilities >50%
- ✅ Frontend test infrastructure documented
- ✅ Tests integrated into CI/CD

### Estimated Effort

- **Matching Tests**: 5 days
- **Worker Tests**: 3 days
- **Frontend Setup**: 2 days
- **Total**: 10 days (~2 weeks)

---

## Phase B Total Effort Summary

| Task | Estimated Effort | Priority |
|------|------------------|----------|
| B1: Supabase Consolidation | 2 weeks | CRITICAL |
| B2: Fix Silent Failures | 2 weeks | HIGH |
| B3: Add Tests | 2 weeks | HIGH |
| **Total** | **6 weeks** | |

**Note**: Tasks can be parallelized if multiple developers available.

**Sequential Estimate**: 6 weeks  
**Parallel Estimate (3 devs)**: 2-3 weeks

---

## Validation Gates

Before completing Phase B, verify:

- ✅ Only one Supabase client implementation
- ✅ Zero `except Exception: pass` in critical paths
- ✅ 40+ new tests added and passing
- ✅ All existing tests still pass (70+ tests)
- ✅ Code coverage meets targets (80% critical, 50% non-critical)
- ✅ Documentation updated
- ✅ ADR created for Supabase consolidation
- ✅ No production regressions

---

## Next Steps

1. **Immediate**: Get approval to proceed with implementation
2. **Week 1-2**: Task B1 (Supabase consolidation)
3. **Week 3-4**: Task B2 (Silent failures)
4. **Week 5-6**: Task B3 (Testing)
5. **After B**: Proceed to Phase C (Legacy cleanup)

---

**Status**: ⏳ AWAITING IMPLEMENTATION  
**Prerequisites**: ✅ Phase D and A complete  
**Estimated Duration**: 6 weeks (sequential) or 2-3 weeks (parallel)  
**Last Updated**: January 16, 2026
