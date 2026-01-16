# Phase C — Legacy Cleanup — Implementation Roadmap

**Date:** January 16, 2026  
**Status:** ⏳ READY FOR IMPLEMENTATION  
**Estimated Effort:** 1 week  
**Prerequisites:** Phases D, A, and B roadmap complete ✅

---

## Executive Summary

Phase C addresses technical debt and structural issues that create maintenance burden:
1. **Legacy file removal** - Remove unused code (monitor_message_edits.py, setup_service/)
2. **Circular import fixes** - Refactor runtime.py singleton pattern
3. **Import boundary enforcement** - Add import-linter to prevent future issues

This phase improves code maintainability and prevents architectural degradation.

---

## Task C1: Remove Unused Legacy Files

### Current State Analysis

**Legacy Files Identified:**

1. **`TutorDexAggregator/monitor_message_edits.py`** (749 lines)
   - **Purpose**: Historical script for monitoring Telegram message edits
   - **Status**: Not referenced in docker-compose.yml
   - **Usage**: Need to verify no imports

2. **`TutorDexAggregator/setup_service/`** directory
   - **Purpose**: Legacy service setup scripts
   - **Status**: Appears unused

3. **Backup files** (if any)
   - Pattern: `*.backup`, `*.bak`, `*~`

### Verification Steps

#### Step 1: Check for Imports (30 minutes)

**Commands**:
```bash
# Check monitor_message_edits.py usage
grep -r "import.*monitor_message_edits\|from.*monitor_message_edits" --include="*.py" .
grep -r "monitor_message_edits" docker-compose.yml docker-compose*.yml
grep -r "monitor_message_edits" docs/

# Check setup_service/ usage
grep -r "setup_service" --include="*.py" .
grep -r "setup_service" docker-compose.yml docker-compose*.yml
```

**Expected Results**:
- No imports found
- No docker-compose references
- May have doc references (update docs)

#### Step 2: Check Git History (15 minutes)

**Commands**:
```bash
# Check last modification date
git log -1 --format="%ai" -- TutorDexAggregator/monitor_message_edits.py
git log -1 --format="%ai" -- TutorDexAggregator/setup_service/

# Check commit activity
git log --oneline --since="6 months ago" -- TutorDexAggregator/monitor_message_edits.py
```

**Decision Criteria**:
- Not modified in 6+ months → safe to remove
- No recent commits → confirms unused status

#### Step 3: Verify Functionality Still Works (1 hour)

**Actions**:
1. Start docker-compose services:
   ```bash
   docker-compose up -d
   ```

2. Check all services healthy:
   ```bash
   docker-compose ps
   curl http://localhost:8000/health
   ```

3. Run test suite:
   ```bash
   pytest tests/
   ```

**Validation**: All services start, all tests pass

### Implementation Plan

#### Action 1: Create Removal Documentation (30 minutes)

**Create**: `docs/REMOVED_FILES.md`

**Content**:
```markdown
# Removed Legacy Files

**Date**: January 16, 2026  
**Reason**: Cleanup of unused legacy code

## Files Removed

### TutorDexAggregator/monitor_message_edits.py
- **Size**: 749 lines
- **Last Modified**: [Date from git log]
- **Reason**: Not used in current architecture
- **Functionality**: Monitored Telegram message edits
- **Replacement**: Functionality moved to main collector pipeline
- **Git Reference**: Available in history at commit [hash]

### TutorDexAggregator/setup_service/
- **Reason**: Legacy service setup directory no longer used
- **Replacement**: Docker Compose handles service orchestration
- **Git Reference**: Available in history

## Verification Steps Taken

- ✅ Checked for imports across codebase (0 found)
- ✅ Verified not referenced in docker-compose
- ✅ Verified not referenced in documentation
- ✅ Confirmed no recent git activity (6+ months)
- ✅ All tests pass after removal
- ✅ All services start successfully

## Recovery Instructions

If needed, these files can be recovered from git history:
```bash
# Restore monitor_message_edits.py
git checkout <commit-before-removal> -- TutorDexAggregator/monitor_message_edits.py

# Restore setup_service/
git checkout <commit-before-removal> -- TutorDexAggregator/setup_service/
```

## Impact Assessment

- **Risk**: LOW - Files confirmed unused
- **Breaking Changes**: None
- **Migration Required**: No
```

#### Action 2: Remove Files (15 minutes)

**Commands**:
```bash
cd /home/runner/work/TutorDexMonoRepo/TutorDexMonoRepo

# Remove monitor_message_edits.py
git rm TutorDexAggregator/monitor_message_edits.py

# Remove setup_service/ directory
git rm -r TutorDexAggregator/setup_service/

# Find and remove any backup files
find . -name "*.backup" -o -name "*.bak" -o -name "*~" | xargs git rm

# Update .gitignore to prevent future backup files
echo "" >> .gitignore
echo "# Backup files" >> .gitignore
echo "*.backup" >> .gitignore
echo "*.bak" >> .gitignore
echo "*~" >> .gitignore
```

#### Action 3: Update Documentation References (30 minutes)

**Files to Check**:
- `docs/SYSTEM_INTERNAL.md`
- `TutorDexAggregator/README.md`
- Any monitoring guides

**Actions**:
1. Search for references: `grep -r "monitor_message_edits" docs/`
2. Remove or update any references
3. Add note about functionality moving to main collector

#### Action 4: Validate (1 hour)

**Validation Steps**:
```bash
# 1. Run all tests
pytest tests/ -v

# 2. Check Python imports
python -m py_compile TutorDexAggregator/*.py
python -m py_compile TutorDexBackend/*.py

# 3. Start services
docker-compose up -d
sleep 10
docker-compose ps

# 4. Check health
curl http://localhost:8000/health

# 5. Stop services
docker-compose down
```

**Expected Results**:
- ✅ All tests pass
- ✅ No import errors
- ✅ All services start successfully
- ✅ Health checks pass

### Acceptance Criteria

- ✅ `TutorDexAggregator/monitor_message_edits.py` removed
- ✅ `TutorDexAggregator/setup_service/` removed
- ✅ `docs/REMOVED_FILES.md` created with full documentation
- ✅ `.gitignore` updated to prevent backup files
- ✅ All tests pass (70+ existing tests)
- ✅ Docker Compose services start successfully
- ✅ No import errors or broken references

### Estimated Effort

- **Verification**: 2 hours
- **Documentation**: 1 hour
- **Removal**: 30 minutes
- **Validation**: 1 hour
- **Total**: ~4.5 hours (half day)

---

## Task C2: Fix Circular Import Risks

### Current State Analysis

**Problem**: `runtime.py` uses module-level singleton pattern that creates import fragility

**Current Architecture**:
```python
# TutorDexBackend/runtime.py (simplified)
from TutorDexBackend.services.auth_service import AuthService
from TutorDexBackend.supabase_store import SupabaseStore
# ... more imports

# Module-level singletons
cfg = load_backend_config()
store = SupabaseStore()
auth_service = AuthService(cfg)
# ... more singletons

# Used everywhere like:
# from TutorDexBackend.runtime import auth_service, store
```

**Issues**:
1. Import order matters - runtime.py must be imported after dependencies
2. Hard to test - singletons are global state
3. Circular import risk - if any service imports from runtime
4. No dependency injection - tight coupling

**Usage Sites** (found 8 files):
- `routes/user_routes.py`
- `routes/duplicates_routes.py`
- `routes/telegram_routes.py`
- `routes/health_routes.py`
- `routes/assignments_routes.py`
- `routes/analytics_routes.py`
- `routes/admin_routes.py`
- `app.py`

### Solution Design

**Approach**: Refactor to dependency injection pattern with lazy initialization

**Design Pattern**: Application Context + Dependency Injection

**Benefits**:
- ✅ No circular imports possible
- ✅ Testable (inject mocks)
- ✅ Clear dependency graph
- ✅ Explicit over implicit

### Implementation Plan

#### Step 1: Create Application Context (2 hours)

**Create**: `TutorDexBackend/app_context.py`

**Content**:
```python
"""
Application Context - Dependency Injection Container

Manages service lifecycle and dependencies.
Replaces runtime.py singleton pattern with proper DI.
"""
import logging
from typing import Optional
from dataclasses import dataclass

from shared.config import load_backend_config
from TutorDexBackend.services.auth_service import AuthService
from TutorDexBackend.services.health_service import HealthService
from TutorDexBackend.services.cache_service import CacheService
from TutorDexBackend.services.telegram_service import TelegramService
from TutorDexBackend.services.analytics_service import AnalyticsService
from TutorDexBackend.supabase_store import SupabaseStore

logger = logging.getLogger("app_context")


@dataclass
class AppContext:
    """
    Application context holding all services.
    
    This is the single source of truth for service instances.
    Created once at application startup and passed to routes.
    """
    # Config
    cfg: object
    
    # Core services
    auth_service: AuthService
    health_service: HealthService
    cache_service: CacheService
    telegram_service: TelegramService
    analytics_service: AnalyticsService
    
    # Data stores
    sb: SupabaseStore  # Keep 'sb' name for compatibility
    store: SupabaseStore  # Alias
    
    # Logger
    logger: logging.Logger


def create_app_context() -> AppContext:
    """
    Create and initialize application context.
    
    Called once at application startup.
    All services are initialized here with proper dependency order.
    
    Returns:
        AppContext with all services initialized
    """
    logger.info("Initializing application context...")
    
    # Load config first
    cfg = load_backend_config()
    
    # Initialize data stores
    sb = SupabaseStore()
    
    # Initialize services (with dependencies)
    auth_service = AuthService(cfg)
    health_service = HealthService(supabase_store=sb)
    cache_service = CacheService(cfg)
    telegram_service = TelegramService(cfg)
    analytics_service = AnalyticsService(sb)
    
    # Create context
    ctx = AppContext(
        cfg=cfg,
        auth_service=auth_service,
        health_service=health_service,
        cache_service=cache_service,
        telegram_service=telegram_service,
        analytics_service=analytics_service,
        sb=sb,
        store=sb,  # Alias
        logger=logger
    )
    
    logger.info("Application context initialized successfully")
    return ctx
```

#### Step 2: Update FastAPI App (1 hour)

**Update**: `TutorDexBackend/app.py`

**Changes**:
```python
# OLD
from TutorDexBackend.runtime import auth_service, cfg, logger, sb, store

# NEW
from TutorDexBackend.app_context import create_app_context, AppContext

# Create context at startup
ctx: AppContext = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager."""
    global ctx
    ctx = create_app_context()
    yield
    # Cleanup if needed
    logger.info("Shutting down...")

app = FastAPI(lifespan=lifespan)

# Store context in app state for route access
@app.middleware("http")
async def inject_context(request: Request, call_next):
    request.state.ctx = ctx
    response = await call_next(request)
    return response
```

#### Step 3: Update All Routes (3 hours)

**Pattern for Each Route File**:

**OLD**:
```python
from TutorDexBackend.runtime import auth_service, store

@router.get("/users/me")
async def get_current_user(uid: str = Depends(auth_service.require_uid)):
    user = store.get_user(uid)
    return user
```

**NEW**:
```python
from fastapi import Depends, Request
from TutorDexBackend.app_context import AppContext

def get_context(request: Request) -> AppContext:
    """Dependency to extract context from request."""
    return request.state.ctx

@router.get("/users/me")
async def get_current_user(
    request: Request,
    ctx: AppContext = Depends(get_context)
):
    uid = await ctx.auth_service.require_uid(request)
    user = ctx.store.get_user(uid)
    return user
```

**Files to Update** (8 files):
1. `routes/user_routes.py`
2. `routes/duplicates_routes.py`
3. `routes/telegram_routes.py`
4. `routes/health_routes.py`
5. `routes/assignments_routes.py`
6. `routes/analytics_routes.py`
7. `routes/admin_routes.py`
8. `app.py` (main file)

#### Step 4: Add Deprecation Warning to runtime.py (30 minutes)

**Update**: `TutorDexBackend/runtime.py`

**Add at top**:
```python
"""
DEPRECATED: This module is being phased out.

Use TutorDexBackend.app_context instead.

This file is kept temporarily for backward compatibility but will be removed.
All new code should use dependency injection via AppContext.
"""
import warnings

warnings.warn(
    "TutorDexBackend.runtime is deprecated. Use app_context instead.",
    DeprecationWarning,
    stacklevel=2
)

# Keep existing code for now (for any external scripts)
# ... existing code ...
```

#### Step 5: Update Tests (2 hours)

**Pattern**:

**OLD**:
```python
from TutorDexBackend.runtime import auth_service, store

def test_get_user():
    user = store.get_user("test-uid")
    assert user is not None
```

**NEW**:
```python
from unittest.mock import Mock
from TutorDexBackend.app_context import AppContext

def test_get_user():
    # Create mock context
    mock_store = Mock()
    mock_store.get_user.return_value = {"uid": "test-uid"}
    
    ctx = AppContext(
        cfg=Mock(),
        auth_service=Mock(),
        health_service=Mock(),
        cache_service=Mock(),
        telegram_service=Mock(),
        analytics_service=Mock(),
        sb=mock_store,
        store=mock_store,
        logger=Mock()
    )
    
    # Test with mocked context
    user = ctx.store.get_user("test-uid")
    assert user["uid"] == "test-uid"
```

**Test Files to Update**:
- `tests/test_backend_api.py`
- `tests/test_backend_auth.py`
- `tests/test_backend_admin.py`
- All route tests

#### Step 6: Validation (1 hour)

**Validation Steps**:
```bash
# 1. Run all backend tests
pytest tests/test_backend*.py -v

# 2. Check for import errors
python -c "from TutorDexBackend.app_context import create_app_context; ctx = create_app_context(); print('OK')"

# 3. Start server and test endpoints
uvicorn TutorDexBackend.app:app --host 0.0.0.0 --port 8000 &
sleep 5
curl http://localhost:8000/health
curl http://localhost:8000/docs
kill %1

# 4. Check for circular imports
python -c "import TutorDexBackend.app; print('No circular imports')"
```

### Acceptance Criteria

- ✅ `app_context.py` created with dependency injection
- ✅ All 8 route files updated to use AppContext
- ✅ `runtime.py` marked deprecated with warning
- ✅ All backend tests updated and passing
- ✅ No circular import errors
- ✅ Services testable in isolation
- ✅ Deprecation warnings appear in logs

### Estimated Effort

- **Context Creation**: 2 hours
- **App Update**: 1 hour
- **Route Updates**: 3 hours
- **Deprecation**: 30 minutes
- **Test Updates**: 2 hours
- **Validation**: 1 hour
- **Total**: ~9.5 hours (1-2 days)

---

## Task C3: Add Import Linting

### Purpose

Prevent future circular imports and enforce architectural boundaries.

### Tool Selection

**Tool**: `import-linter`
- Enforces import rules via configuration
- CI-friendly
- Well-maintained

### Implementation Plan

#### Step 1: Install Import Linter (15 minutes)

**Update**: `TutorDexBackend/requirements.txt` and `TutorDexAggregator/requirements-dev.txt`

**Add**:
```
import-linter>=2.0,<3.0
```

**Install**:
```bash
pip install import-linter
```

#### Step 2: Create Configuration (30 minutes)

**Create**: `.import-linter.ini`

**Content**:
```ini
[importlinter]
root_packages =
    TutorDexAggregator
    TutorDexBackend
    TutorDexWebsite
    shared

[importlinter:contract:backend-independence]
name = Backend should not import from Aggregator or Website
type = forbidden
source_modules =
    TutorDexBackend
forbidden_modules =
    TutorDexAggregator
    TutorDexWebsite

[importlinter:contract:aggregator-independence]
name = Aggregator should not import from Backend or Website
type = forbidden
source_modules =
    TutorDexAggregator
forbidden_modules =
    TutorDexBackend
    TutorDexWebsite

[importlinter:contract:shared-no-app-imports]
name = Shared should not import from application code
type = forbidden
source_modules =
    shared
forbidden_modules =
    TutorDexAggregator
    TutorDexBackend
    TutorDexWebsite

[importlinter:contract:no-circular-backend]
name = No circular imports within Backend
type = layers
layers =
    TutorDexBackend.routes
    TutorDexBackend.services
    TutorDexBackend.utils

[importlinter:contract:no-circular-aggregator]
name = No circular imports within Aggregator
type = layers
layers =
    TutorDexAggregator.workers
    TutorDexAggregator.services
    TutorDexAggregator.extractors
    TutorDexAggregator.utils
```

#### Step 3: Add Pre-commit Hook (15 minutes)

**Update**: `.githooks/pre-commit`

**Add**:
```bash
# Import linting
echo "Running import-linter..."
if ! lint-imports; then
    echo "❌ Import linting failed"
    echo "Fix import violations or run with --no-verify to skip"
    exit 1
fi
echo "✅ Import linting passed"
```

#### Step 4: Add CI Check (30 minutes)

**Create**: `.github/workflows/import-lint.yml`

**Content**:
```yaml
name: Import Linting

on:
  push:
    branches: [ main, copilot/** ]
  pull_request:
    branches: [ main ]

jobs:
  import-lint:
    name: Check Import Boundaries
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout code
        uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          pip install import-linter
      
      - name: Run import-linter
        run: |
          lint-imports
      
      - name: Report results
        if: failure()
        run: |
          echo "❌ Import boundary violations detected"
          echo "See import-linter output above for details"
          exit 1
```

#### Step 5: Create Documentation (30 minutes)

**Create**: `docs/IMPORT_BOUNDARIES.md`

**Content**:
```markdown
# Import Boundaries and Architecture Rules

## Overview

This project enforces architectural boundaries via import-linter.
Violations will fail CI builds.

## Rules

### 1. Component Independence
- **Backend** cannot import from Aggregator or Website
- **Aggregator** cannot import from Backend or Website
- **Website** cannot import from Backend or Aggregator

### 2. Shared Module Purity
- **shared/** cannot import from any application code
- shared/ is for common utilities only

### 3. Layered Architecture

**Backend Layers** (higher can import lower, not reverse):
1. Routes (top)
2. Services (middle)
3. Utils (bottom)

**Aggregator Layers** (higher can import lower, not reverse):
1. Workers (top)
2. Services (middle)
3. Extractors (middle)
4. Utils (bottom)

## Checking Locally

```bash
# Run import linter
lint-imports

# Check specific contract
lint-imports --contract backend-independence
```

## Fixing Violations

### Common Violations

**1. Cross-component import**
```python
# ❌ BAD
from TutorDexBackend.some_module import something

# ✅ GOOD
from shared.some_module import something
```

**2. Layer violation**
```python
# ❌ BAD (service importing from route)
from TutorDexBackend.routes.user_routes import some_function

# ✅ GOOD (route importing from service)
from TutorDexBackend.services.user_service import some_function
```

**3. Circular import**
```python
# ❌ BAD (A imports B, B imports A)
# module_a.py
from module_b import something

# module_b.py  
from module_a import something_else

# ✅ GOOD (extract common code to utils)
# utils.py
def shared_function(): ...

# module_a.py
from utils import shared_function

# module_b.py
from utils import shared_function
```

## CI Integration

Import linting runs automatically on:
- Every push to main
- Every pull request
- Pre-commit hook (if installed)

## Disabling (Emergency Only)

If you must bypass import linting (emergency only):
```bash
git commit --no-verify
```

**Note**: This should be rare and requires justification in PR.
```

#### Step 6: Validate (30 minutes)

**Validation Steps**:
```bash
# 1. Run import-linter
lint-imports

# 2. Test pre-commit hook
.githooks/pre-commit

# 3. Verify CI workflow syntax
cat .github/workflows/import-lint.yml | python -c "import yaml, sys; yaml.safe_load(sys.stdin)"

# 4. Test example violation (should fail)
echo "from TutorDexAggregator import something" >> TutorDexBackend/test_violation.py
lint-imports  # Should fail
rm TutorDexBackend/test_violation.py
```

### Acceptance Criteria

- ✅ `import-linter` installed in dev dependencies
- ✅ `.import-linter.ini` created with 5 contracts
- ✅ Pre-commit hook updated
- ✅ CI workflow created
- ✅ Documentation created (IMPORT_BOUNDARIES.md)
- ✅ Import linter passes on current codebase
- ✅ Test violation properly detected

### Estimated Effort

- **Installation**: 15 minutes
- **Configuration**: 30 minutes
- **Pre-commit**: 15 minutes
- **CI Setup**: 30 minutes
- **Documentation**: 30 minutes
- **Validation**: 30 minutes
- **Total**: ~2.5 hours (half day)

---

## Phase C Summary

### Total Effort Estimate

| Task | Effort | Complexity |
|------|--------|------------|
| C1: Remove Legacy Files | 0.5 days | Low |
| C2: Fix Circular Imports | 1.5 days | Medium |
| C3: Add Import Linting | 0.5 days | Low |
| **Total** | **2.5 days** | |

**With buffer**: 3-4 days (1 week)

### Acceptance Criteria (Phase C Complete)

- ✅ Legacy files removed with documentation
- ✅ Circular import risks eliminated
- ✅ Import linting enforced in CI
- ✅ All 70+ tests still passing
- ✅ Docker Compose services start successfully
- ✅ No breaking changes to production workflows

### Validation Gates

Before completing Phase C:
- ✅ All tests pass
- ✅ Import linter passes
- ✅ No deprecation warnings (except from runtime.py)
- ✅ Services start and respond to health checks
- ✅ Documentation complete and accurate

### Risks & Mitigation

**Risk 1: Breaking existing code**
- **Mitigation**: Thorough grep verification before deletion
- **Mitigation**: Keep runtime.py with deprecation warning
- **Mitigation**: Comprehensive testing after each change

**Risk 2: Import linter too strict**
- **Mitigation**: Start with clear violations only
- **Mitigation**: Document exceptions if needed
- **Mitigation**: Can adjust rules based on feedback

**Risk 3: Test update effort underestimated**
- **Mitigation**: Update tests incrementally
- **Mitigation**: Use helper functions for common mock patterns
- **Mitigation**: Budget extra time if needed

---

## Next Steps

1. **Execute Task C1**: Remove legacy files (0.5 days)
2. **Execute Task C2**: Fix circular imports (1.5 days)
3. **Execute Task C3**: Add import linting (0.5 days)
4. **Validation**: Run full test suite and smoke tests (0.5 days)
5. **Proceed to Phase E**: Final validation and completion report

---

**Status**: ⏳ READY FOR IMPLEMENTATION  
**Prerequisites**: ✅ Phases D, A, B roadmap complete  
**Estimated Duration**: 3-4 days (1 week with buffer)  
**Last Updated**: January 16, 2026
