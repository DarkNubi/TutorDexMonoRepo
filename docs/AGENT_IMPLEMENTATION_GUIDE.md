# Complete Refactoring Implementation Guide for Agent

**Target:** Complete all remaining codebase quality audit priorities  
**Environment:** Host machine with full deployment environment access  
**Prerequisites:** Docker, Python 3.11+, Node.js 18+, access to Supabase/Redis/LLM API

---

## Executive Summary

You have access to the full deployment environment. Your task is to complete Priorities 4, 5, and remaining Priority 6 work from the audit. All changes MUST be tested against the real environment before committing.

**Critical Success Criteria:**
1. All existing tests must continue to pass
2. All new functionality must have comprehensive tests
3. Code must work in real deployment environment
4. No breaking changes to existing APIs
5. All changes must be validated incrementally

---

## Environment Setup

### 1. Verify Environment
```bash
# Navigate to repo
cd /home/runner/work/TutorDexMonoRepo/TutorDexMonoRepo

# Install all dependencies
pip install -r TutorDexBackend/requirements.txt
pip install -r TutorDexAggregator/requirements.txt
cd TutorDexWebsite && npm ci && cd ..

# Start services (Docker Compose)
docker-compose up -d

# Wait for services to be ready
sleep 10

# Run existing tests to establish baseline
python -m pytest tests/ -v --tb=short
```

**Expected Result:** All existing tests pass. If not, STOP and report issues.

---

## Priority 4: Consolidate Supabase Clients (1 week)

### Problem
Three incompatible Supabase client implementations:
- `shared/supabase_client.py` (450 lines) - "official" unified client
- `TutorDexAggregator/utils/supabase_client.py` (100+ lines) - duplicate
- `TutorDexBackend/supabase_store.py` (649 lines) - most used, incompatible

### Objective
Consolidate to single implementation in `shared/supabase_client.py`.

### Phase 1: Audit and Design (Day 1)

**Task 1.1: Document all method signatures**
```bash
# Create audit document
cat > /tmp/supabase_client_audit.md << 'EOF'
# Supabase Client Method Audit

## shared/supabase_client.py
- select(table, filters, columns, limit, offset, order_by)
- insert(table, data)
- upsert(table, data, on_conflict)
- update(table, data, filters)
- delete(table, filters)
- rpc(function_name, params)
- count(table, filters)

## TutorDexAggregator/utils/supabase_client.py
[List all methods with signatures]

## TutorDexBackend/supabase_store.py
[List all methods with signatures]

## Differences
[Document incompatibilities]
EOF

# Read each file and document
```

**Task 1.2: Find all usage locations**
```bash
# Find all imports
grep -r "from.*supabase" --include="*.py" TutorDexBackend TutorDexAggregator shared | grep -v test | grep -v __pycache__

# Document each usage pattern
```

**Task 1.3: Design unified API**
```python
# shared/supabase_client.py (enhanced)
class SupabaseClient:
    """Unified Supabase REST client for all services"""
    
    # Add any missing methods from Backend/Aggregator implementations
    # Ensure backward compatibility
    
    def select(self, table, filters=None, columns="*", limit=None, offset=None, order_by=None):
        """SELECT with full feature set"""
        pass
    
    def post(self, path, json_body, timeout=15, prefer=None, extra_headers=None):
        """Raw POST for custom operations (Backend compatibility)"""
        pass
    
    def patch(self, path, json_body, timeout=15, prefer=None):
        """Raw PATCH for custom operations (Backend compatibility)"""
        pass
```

### Phase 2: Backend Migration (Days 2-4)

**Task 2.1: Create adapter for backward compatibility**
```python
# TutorDexBackend/supabase_adapter.py (new file)
"""
Backward-compatible adapter wrapping shared SupabaseClient.

Provides SupabaseStore interface using shared client underneath.
"""
from shared.supabase_client import SupabaseClient, SupabaseConfig
from shared.config import load_backend_config

class SupabaseStore:
    """Adapter maintaining Backend API compatibility"""
    
    def __init__(self, cfg=None):
        backend_cfg = cfg or load_backend_config()
        supabase_cfg = SupabaseConfig(
            url=backend_cfg.supabase_rest_url,
            key=backend_cfg.supabase_auth_key,
            timeout=backend_cfg.supabase_timeout or 15
        )
        self.client = SupabaseClient(supabase_cfg)
        self.cfg = backend_cfg
    
    def enabled(self):
        return self.client is not None
    
    # Wrap all existing methods to use shared client
    def upsert_user(self, **kwargs):
        # Implementation using self.client
        pass
```

**Task 2.2: Update imports gradually**
```bash
# Start with one file
# TutorDexBackend/routes/user_routes.py

# Change:
# from TutorDexBackend.supabase_store import SupabaseStore
# To:
# from TutorDexBackend.supabase_adapter import SupabaseStore

# Test that file's routes
python -m pytest tests/test_backend_api.py::TestUserEndpoints -v

# If pass, continue to next file
```

**Task 2.3: Migrate all Backend files**
```bash
# Files to migrate:
# - TutorDexBackend/runtime.py
# - TutorDexBackend/routes/*.py
# - Any other imports

# For each file:
# 1. Change import
# 2. Run relevant tests
# 3. If fail, revert and debug
# 4. If pass, commit

git add TutorDexBackend/supabase_adapter.py
git commit -m "feat: add backward-compatible Supabase adapter for Backend"

# Continue file by file...
```

**Task 2.4: Delete old implementation**
```bash
# Only after ALL Backend tests pass
git rm TutorDexBackend/supabase_store.py
git commit -m "refactor: remove old SupabaseStore, now using shared client"
```

### Phase 3: Aggregator Migration (Days 5-6)

**Task 3.1: Create Aggregator adapter if needed**
```python
# TutorDexAggregator/supabase_adapter.py (if needed)
# Similar to Backend adapter
```

**Task 3.2: Migrate Aggregator files**
```bash
# Files to migrate:
# - TutorDexAggregator/supabase_persist_impl.py
# - TutorDexAggregator/supabase_raw_persist.py
# - TutorDexAggregator/workers/*.py
# - Any other imports

# Test worker functionality
python -m pytest tests/test_supabase_persist*.py -v

# Test in real environment
docker-compose logs -f tutordex-aggregator &
# Trigger a test message, verify processing works
```

**Task 3.3: Delete old implementation**
```bash
git rm TutorDexAggregator/utils/supabase_client.py
git commit -m "refactor: remove duplicate Supabase client from Aggregator"
```

### Phase 4: Integration Testing (Day 7)

**Task 4.1: Run full test suite**
```bash
# Unit tests
python -m pytest tests/ -v

# Integration tests with real services
docker-compose up -d
sleep 10

# Test end-to-end flow
# 1. Send test message to Telegram
# 2. Verify extraction worker processes it
# 3. Verify persistence to Supabase
# 4. Verify Backend can read it
# 5. Verify matching works
# 6. Verify DM delivery (if enabled)

# Check logs for errors
docker-compose logs --tail=100 tutordex-backend
docker-compose logs --tail=100 tutordex-aggregator
```

**Task 4.2: Performance testing**
```bash
# Verify no performance regression
# Measure query times before/after
```

**Success Criteria:**
- ✅ All unit tests pass
- ✅ Integration tests pass
- ✅ End-to-end flow works
- ✅ No errors in logs
- ✅ Single Supabase client implementation
- ✅ Performance maintained or improved

---

## Priority 5: Replace Runtime Singletons (1 week)

### Problem
`TutorDexBackend/runtime.py` creates global singletons that make testing difficult:
```python
store = RedisStore(...)  # Global
sb = SupabaseStore(...)  # Global
cfg = load_backend_config()  # Global
```

### Objective
Replace with dependency injection for better testability.

### Phase 1: Create DI Container (Days 1-2)

**Task 1.1: Install dependency-injector**
```bash
# Add to TutorDexBackend/requirements.txt
echo "dependency-injector>=4.41.0,<5.0.0" >> TutorDexBackend/requirements.txt
pip install dependency-injector
```

**Task 1.2: Create container**
```python
# TutorDexBackend/container.py (new file)
"""
Dependency injection container for Backend services.
"""
from dependency_injector import containers, providers
from shared.config import load_backend_config
from TutorDexBackend.redis_store import RedisStore
from TutorDexBackend.supabase_adapter import SupabaseStore
from TutorDexBackend.services.auth_service import AuthService
from TutorDexBackend.services.cache_service import CacheService
from TutorDexBackend.services.health_service import HealthService
from TutorDexBackend.services.analytics_service import AnalyticsService
from TutorDexBackend.services.telegram_service import TelegramService


class Container(containers.DeclarativeContainer):
    """Application dependency injection container"""
    
    # Configuration
    config = providers.Singleton(load_backend_config)
    
    # Data stores
    redis_store = providers.Singleton(
        RedisStore,
        cfg=config.provided.redis
    )
    
    supabase_store = providers.Singleton(
        SupabaseStore,
        cfg=config
    )
    
    # Services
    auth_service = providers.Factory(
        AuthService
    )
    
    cache_service = providers.Factory(
        CacheService,
        store=redis_store
    )
    
    health_service = providers.Factory(
        HealthService,
        sb_store=supabase_store,
        redis_store=redis_store
    )
    
    analytics_service = providers.Factory(
        AnalyticsService,
        sb_store=supabase_store
    )
    
    telegram_service = providers.Factory(
        TelegramService,
        sb_store=supabase_store,
        redis_store=redis_store
    )
```

### Phase 2: Update Routes (Days 3-5)

**Task 2.1: Update app.py to use container**
```python
# TutorDexBackend/app.py
from TutorDexBackend.container import Container

# Create container
container = Container()

# Make container available to routes
app.state.container = container

# Update middleware to use container
@app.on_event("startup")
async def startup():
    # Initialize services from container
    auth_service = container.auth_service()
    auth_service.validate_production_config()
```

**Task 2.2: Update routes to use Depends**
```python
# TutorDexBackend/routes/assignments_routes.py
from fastapi import APIRouter, Depends
from TutorDexBackend.container import Container

router = APIRouter()

def get_container() -> Container:
    """Get container from app state"""
    from TutorDexBackend.app import app
    return app.state.container

@router.get("/assignments")
async def list_assignments(
    container: Container = Depends(get_container)
):
    # Get services from container
    sb_store = container.supabase_store()
    cache_service = container.cache_service()
    
    # Use services
    await cache_service.enforce_rate_limit(request, "assignments")
    results = sb_store.list_assignments_paged(...)
    return results
```

**Task 2.3: Migrate all routes gradually**
```bash
# For each route file:
# 1. Update to use Depends(get_container)
# 2. Get services from container
# 3. Test that route
# 4. Commit if pass

# Test each change
python -m pytest tests/test_backend_api.py -v
```

### Phase 3: Update Tests (Days 6-7)

**Task 3.1: Update test fixtures**
```python
# tests/conftest.py
import pytest
from TutorDexBackend.container import Container

@pytest.fixture
def container():
    """Create test container with mocked services"""
    container = Container()
    
    # Override with mocks
    container.redis_store.override(Mock())
    container.supabase_store.override(Mock())
    
    return container

@pytest.fixture
def test_app(container):
    """Create test app with container"""
    from TutorDexBackend.app import app
    app.state.container = container
    return app
```

**Task 3.2: Update all tests**
```bash
# Update tests to use new fixtures
# Run full test suite
python -m pytest tests/ -v
```

**Task 3.3: Delete runtime.py**
```bash
git rm TutorDexBackend/runtime.py
git commit -m "refactor: replace runtime singletons with dependency injection"
```

**Success Criteria:**
- ✅ All routes use dependency injection
- ✅ No global singletons
- ✅ All tests pass
- ✅ Tests can mock services easily
- ✅ Backend still works in production

---

## Priority 6: Fix Remaining Silent Failures (Ongoing)

### Problem
120+ instances of broad exception handling that hide errors.

### Objective
Replace with specific exceptions and proper error handling.

### Approach

**Task 1: Identify critical silent failures**
```bash
# Find all broad exception handlers
grep -r "except Exception:" --include="*.py" TutorDexBackend TutorDexAggregator | grep -v test > /tmp/exceptions.txt

# Prioritize by criticality:
# 1. Persistence operations (data loss risk)
# 2. API calls (silent failures affect users)
# 3. Metrics (observability loss)
# 4. Validation (type conversion is often legitimate)
```

**Task 2: Fix high-priority silent failures**

Example fix pattern:
```python
# BEFORE (silent failure)
try:
    result = supabase.insert("assignments", data)
except Exception:
    pass  # SILENT FAILURE

# AFTER (explicit error handling)
from shared.exceptions import DataAccessError

try:
    result = supabase.insert("assignments", data)
except requests.exceptions.RequestException as e:
    logger.error(
        "Failed to insert assignment",
        exc_info=e,
        extra={
            "table": "assignments",
            "data_size": len(str(data)),
            "request_id": request_id
        }
    )
    raise DataAccessError(f"Failed to persist assignment: {e}") from e
```

**Task 3: Add tests for error paths**
```python
# tests/test_error_handling.py
def test_persistence_failure_raises_explicit_error():
    """Test that persistence failures raise DataAccessError"""
    from shared.exceptions import DataAccessError
    
    # Mock Supabase to raise exception
    mock_client = Mock()
    mock_client.insert.side_effect = RequestException("Connection failed")
    
    # Should raise DataAccessError, not swallow
    with pytest.raises(DataAccessError):
        persist_assignment(mock_client, data)
```

**Task 4: Fix incrementally**
```bash
# Fix one file at a time
# Priority order:
# 1. TutorDexAggregator/supabase_persist_impl.py
# 2. TutorDexBackend/services/cache_service.py
# 3. TutorDexBackend/services/analytics_service.py
# 4. TutorDexAggregator/delivery/broadcast_client.py

# For each file:
# 1. Identify silent failures
# 2. Replace with specific exceptions
# 3. Add proper logging
# 4. Add tests for error path
# 5. Verify in real environment
# 6. Commit

git add <file>
git commit -m "fix: explicit error handling in <component>"
```

**Success Criteria:**
- ✅ Critical paths have explicit error handling
- ✅ Errors logged with context
- ✅ Tests verify error paths work
- ✅ Observability improved (errors visible in logs/metrics)
- ✅ No silent data loss

---

## Testing Strategy

### Unit Tests (Before Each Commit)
```bash
# Run specific test file
python -m pytest tests/test_<relevant>.py -v --tb=short

# Run all tests
python -m pytest tests/ -v
```

### Integration Tests (After Each Phase)
```bash
# Start all services
docker-compose up -d

# Wait for readiness
sleep 10

# Check service health
curl http://localhost:8000/health

# Run integration test suite
python scripts/smoke_test.py

# Check logs
docker-compose logs --tail=50 tutordex-backend
docker-compose logs --tail=50 tutordex-aggregator
```

### End-to-End Tests (After All Changes)
```bash
# Test complete flow:
# 1. Telegram message → raw persist
# 2. Extraction queue → process message
# 3. Parse → persist to assignments
# 4. Matching → find tutors
# 5. DM delivery (if enabled)

# Monitor all services
docker-compose logs -f

# Verify data in Supabase
# Verify matching works
# Verify no errors in logs
```

---

## Rollback Strategy

If anything breaks:

1. **Identify issue:**
   ```bash
   git log --oneline -10
   docker-compose logs --tail=100
   ```

2. **Revert specific commit:**
   ```bash
   git revert <commit-hash>
   git push origin copilot/audit-codebase-quality
   ```

3. **Or reset to last working state:**
   ```bash
   git reset --hard <last-working-commit>
   git push -f origin copilot/audit-codebase-quality
   ```

4. **Restart services:**
   ```bash
   docker-compose down
   docker-compose up -d
   ```

---

## Validation Checklist

Before marking work complete:

- [ ] All unit tests pass (48+ tests should still pass)
- [ ] All integration tests pass
- [ ] End-to-end flow works in real environment
- [ ] No errors in application logs
- [ ] No errors in worker logs
- [ ] Performance is maintained or improved
- [ ] All services start successfully
- [ ] Health endpoints return healthy
- [ ] Supabase operations work
- [ ] Redis operations work
- [ ] Telegram integration works (if testing)
- [ ] Matching algorithm works
- [ ] Code follows existing patterns
- [ ] All changes are documented
- [ ] No breaking API changes

---

## Success Metrics

**Priority 4 Complete When:**
- Single Supabase client implementation
- All Backend code uses shared client
- All Aggregator code uses shared client
- All tests pass
- Production deployment successful

**Priority 5 Complete When:**
- No global singletons in runtime.py
- All routes use dependency injection
- All services injected via container
- Tests use mocked dependencies
- All tests pass

**Priority 6 Complete When:**
- Critical silent failures fixed
- Errors logged with context
- Custom exceptions used
- Error paths tested
- Observability improved

---

## Support Information

**Existing Documentation:**
- `docs/AUDIT_ACTION_PLAN_2026-01-15.md` - Detailed action items
- `docs/AUDIT_IMPLEMENTATION_STATUS.md` - Progress tracking
- `docs/SYSTEM_INTERNAL.md` - Architecture reference
- `docs/signals.md` - Signal extraction docs
- `TutorDexBackend/README.md` - Backend setup
- `TutorDexAggregator/README.md` - Aggregator setup

**Key Files:**
- `docker-compose.yml` - Service orchestration
- `tests/conftest.py` - Test fixtures
- `shared/config.py` - Configuration management
- `shared/exceptions.py` - Custom exceptions (already created)

**Commands Reference:**
```bash
# Run backend locally
cd TutorDexBackend && uvicorn TutorDexBackend.app:app --reload

# Run tests
python -m pytest tests/ -v

# Check code
python -m py_compile <file>

# Start services
docker-compose up -d

# View logs
docker-compose logs -f <service>

# Stop services
docker-compose down
```

---

## Final Notes

- **Work incrementally:** Small changes, test frequently
- **Test in real environment:** Don't rely on mocks alone
- **Commit often:** Each working change should be committed
- **Document issues:** If blocked, document what and why
- **Maintain backward compatibility:** No breaking changes
- **Preserve existing tests:** All 48+ tests must continue passing

**This is critical work. Take your time. Test thoroughly. The goal is stability, not speed.**
