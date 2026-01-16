# Outstanding Tasks - Quick Summary

**Generated:** January 16, 2026  
**Full Details:** See `OUTSTANDING_TASKS_2026-01-16.md`

---

## TL;DR

**Current Status:** 16/16 audit priorities from previous cycle complete ✅  
**New Status:** 3 critical risks identified in Jan 15, 2026 audit ⚠️  
**Status Update (2026-01-16):** Supabase client consolidation + Phase C cleanup/linting completed; see `docs/OUTSTANDING_TASKS_2026-01-16.md`

---

## Critical Tasks (Start Immediately)

### ✅ Task B1: Consolidate Supabase Clients
Completed: unified under `shared/supabase_client.py`, removed duplicate wrappers, and documented in `docs/ADR-0001-SUPABASE-CLIENT-CONSOLIDATION.md`.

---

### 🟡 Task B2: Fix Silent Failures
Status update: no `except Exception: pass` instances remain in non-doc code paths; remaining references are in documentation.

**Quick Action:**
```bash
# Find all silent failures:
grep -r "except Exception:" --include="*.py" TutorDexBackend TutorDexAggregator

# Priority order:
1. Critical path (Supabase, persistence, validation)
2. Side effects (broadcast, DM, tracking)
3. Metrics (Prometheus counters)
```

---

### 🟡 Task B3: Add Critical Tests
Status update: matching tests exist (`tests/test_matching.py`); frontend has Mocha tests (`TutorDexWebsite/test/`); remaining gap is orchestration-level tests for the extraction worker.

**Quick Action:**
```bash
# Create test files:
touch tests/test_matching_comprehensive.py       # 25+ tests
touch tests/test_extract_worker_orchestration.py # 15+ tests
touch TutorDexWebsite/vitest.config.js           # Infrastructure

# Coverage targets:
- matching.py: 80%
- Worker: 70%
- Frontend utils: 50%
```

---

## High Priority Tasks (After Critical)

### 🟡 Task C1: Remove Legacy Files (0.5 days)
**Files to Remove:**
- `TutorDexAggregator/monitor_message_edits.py` (749 lines)
- `TutorDexAggregator/setup_service/` directory
- `*.backup`, `*.bak`, `*~` files

**Quick Action:**
```bash
# Verify not in use:
grep -r "monitor_message_edits" .
grep -r "setup_service" .

# Remove if clear:
git rm TutorDexAggregator/monitor_message_edits.py
git rm -r TutorDexAggregator/setup_service/
```

---

### 🟡 Task C2: Fix Circular Imports (1.5 days)
**Problem:** `runtime.py` singleton pattern creates import fragility  
**Solution:** Replace with dependency injection via `app_context.py`

**Quick Action:**
```bash
# Create new DI container:
touch TutorDexBackend/app_context.py

# Update 8 route files to use DI
# Deprecate runtime.py with warning
```

---

### 🟡 Task C3: Add Import Linting (0.5 days)
**Goal:** Prevent future circular imports and enforce boundaries

**Quick Action:**
```bash
# Install and configure:
pip install import-linter
touch .import-linter.ini

# Add to CI:
touch .github/workflows/import-lint.yml

# Test:
lint-imports
```

---

## Ongoing Tasks

### 🟢 Task A: Documentation Consolidation (2.5 hours)
**Goal:** Reduce active docs from 52 → ~30 files

**Quick Action:**
```bash
# Move to archive:
git mv docs/AUDIT_TODO_SUMMARY.md docs/archive/audit-2026-01/
git mv docs/REMAINING_AUDIT_TASKS.md docs/archive/audit-2026-01/
# ... (28 files total to move)

# Update main index:
vim docs/README.md
```

---

### 🟢 Task E: Final Validation (1.5 days)
**Includes:**
- Create smoke test suite (4 hours)
- Update documentation (3 hours)
- Create completion report (4 hours)

**Quick Action:**
```bash
# Create test scripts:
touch scripts/smoke_test_backend.bat
touch scripts/smoke_test_aggregator.bat
touch scripts/smoke_test_observability.bat
touch scripts/smoke_test_integration.bat
touch scripts/smoke_test_all.bat

# Run full validation:
scripts\\smoke_test_all.bat
```

---

## Recommended Timeline

### Week 1-2: Critical (Parallel)
- **Dev 1:** B1 (Supabase)
- **Dev 2:** B2 (Silent failures)
- **Dev 3:** B3.1 (Matching tests)

### Week 3: Complete Critical + Cleanup
- **Dev 1:** B3.2 (Worker tests)
- **Dev 2:** B3.3 (Frontend tests)
- **Dev 3:** C1, C2, C3 (Cleanup)

### Week 4: Final Validation
- **All:** A & E (Docs + validation)

---

## Success Metrics

| Metric | Before | Target | Change |
|--------|--------|--------|--------|
| Supabase implementations | 3 | 1 | -67% |
| Silent failures (critical) | 120+ | <10 | -92% |
| Test coverage (matching.py) | 0% | 80% | +80% |
| Active documentation files | 52 | ~30 | -42% |
| Circular import risk | HIGH | ZERO | ✅ |

---

## Priority Matrix

```
High Impact, High Urgency:
┌─────────────────────────┐
│ B1: Supabase (2 weeks)  │ ← START HERE
│ B2: Silent Fails (2w)   │ ← CRITICAL
│ B3: Tests (2 weeks)     │ ← CRITICAL
└─────────────────────────┘

High Impact, Medium Urgency:
┌─────────────────────────┐
│ C1: Legacy (0.5 days)   │
│ C2: Circular (1.5 days) │
│ C3: Import Lint (0.5d)  │
└─────────────────────────┘

Medium Impact, Low Urgency:
┌─────────────────────────┐
│ A: Docs (2.5 hours)     │
│ E: Validation (1.5 days)│
└─────────────────────────┘
```

---

## Quick Start Commands

```bash
# 1. Review full details
cat docs/OUTSTANDING_TASKS_2026-01-16.md

# 2. Start with Phase B (Critical)
cat docs/PHASE_B_ROADMAP.md

# 3. Review audit findings
cat docs/CODEBASE_QUALITY_AUDIT_2026-01-15.md

# 4. Check completed work
cat docs/AUDIT_CHECKLIST.md  # 16/16 complete ✅

# 5. See implementation plan
cat docs/IMPLEMENTATION_PLAN_2026-01-16.md
```

---

## Key Contacts & Resources

**Documentation:**
- Full details: `docs/OUTSTANDING_TASKS_2026-01-16.md`
- Implementation plan: `docs/IMPLEMENTATION_PLAN_2026-01-16.md`
- Latest audit: `docs/CODEBASE_QUALITY_AUDIT_2026-01-15.md`

**Phase Roadmaps:**
- Phase B (Critical): `docs/PHASE_B_ROADMAP.md`
- Phase C (Cleanup): `docs/PHASE_C_ROADMAP.md`
- Phase E (Validation): `docs/PHASE_E_ROADMAP.md`

---

## Risk Level: MEDIUM ⚠️

**Why Medium:**
- Previous audit cycle complete (16/16) ✅
- New critical risks identified but well-documented ⚠️
- Clear implementation roadmap exists ✅
- Production system currently stable ✅

**Risk increases to HIGH if:**
- Critical tasks delayed >1 month
- System scales 2× without addressing risks
- Multiple production incidents occur

---

**Last Updated:** January 16, 2026  
**Review Frequency:** Weekly during Phase B execution  
**Status:** Ready for execution
