# Outstanding Tasks - TutorDex MonoRepo

**Generated:** January 16, 2026  
**Source:** Comprehensive review of all documentation in `docs/`  
**Status:** Active planning document

---

## Executive Summary

Based on analysis of all planning documents, there are **3 major implementation tracks** with varying priority levels:

1. **Phase B: Critical Risk Mitigation** (2-3 weeks) - HIGH PRIORITY
2. **Phase C: Legacy Cleanup** (1 week) - MEDIUM PRIORITY  
3. **Phase A/E: Documentation & Validation** (3-4 days) - ONGOING

**Key Insight:** The audit checklist shows 16/16 priorities complete from the previous audit cycle. However, the January 15, 2026 audit identified 3 new critical risks that require immediate attention.

## Status Update (2026-01-16)

This task list was generated from planning docs; parts of it have since been implemented in the repo:

- ✅ **B1 Supabase client consolidation**: unified under `shared/supabase_client.py` and removed duplicate client wrappers.
- ✅ **C1 Legacy file removal**: removed `TutorDexAggregator/monitor_message_edits.py`, `TutorDexAggregator/setup_service/`, and backup artifacts (see `docs/REMOVED_FILES.md`).
- ✅ **C2 Backend DI**: added `TutorDexBackend/app_context.py`, updated backend routes/app to use it, and marked `TutorDexBackend/runtime.py` deprecated.
- ✅ **C3 Import linting**: added `.import-linter.ini`, CI workflow, and documentation (`docs/IMPORT_BOUNDARIES.md`).

---

## High Priority: Critical Risk Mitigation (Phase B)

**Source:** `docs/PHASE_B_ROADMAP.md`, `docs/AUDIT_ACTION_PLAN_2026-01-15.md`  
**Status:** ⏳ READY FOR IMPLEMENTATION  
**Total Effort:** 2-3 weeks (parallel) or 6 weeks (sequential)

### Task B1: Consolidate Supabase Client Implementations ⚠️ CRITICAL

**Problem:** Three incompatible Supabase client implementations causing 3× maintenance burden

**Current State (as of 2026-01-16):**
- `shared/supabase_client.py` - Unified implementation
- Duplicate wrappers removed from Aggregator and Backend

**Status:** ✅ COMPLETE  
**Artifacts:**
- ADR: `docs/ADR-0001-SUPABASE-CLIENT-CONSOLIDATION.md`

**Success Criteria:**
- ✅ Only one Supabase client implementation exists
- ✅ All 70+ existing tests pass
- ✅ No production regressions
- ✅ ADR document created

**Estimated Effort:** 9 days (~2 weeks)

---

### Task B2: Fix Silent Failure Epidemic ⚠️ HIGH

**Problem:** 120+ instances of `except Exception: pass` hiding production issues

**Status (as of 2026-01-16):** ✅ MOSTLY COMPLETE  
No `except Exception: pass` occurrences remain in non-doc code paths; remaining references are in documentation.

**Categories:**
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

**Actions Required:**
1. Create inventory of all silent failures (1 day)
2. Fix critical path failures - log + raise (3 days)
3. Fix side effect failures - log + fallback (2 days)
4. Fix metric recording failures - log warning (2 days)
5. Add error visibility dashboard (1 day)

**Success Criteria:**
- ✅ Zero `except Exception: pass` in critical paths
- ✅ All errors logged with context
- ✅ Error visibility dashboard created
- ✅ Error rate alerts configured

**Estimated Effort:** 9 days (~2 weeks)

---

### Task B3: Add Tests for Critical Business Logic ⚠️ HIGH

**Problem:** Key business logic has zero test coverage

**Untested Components:**
1. **Matching Algorithm** (`TutorDexBackend/matching.py`) - ✅ tests exist (`tests/test_matching.py`)
2. **Worker Orchestration** (`TutorDexAggregator/workers/extract_worker_main.py`) - ✅ initial orchestration tests added (`tests/test_extract_worker_orchestration.py`)
3. **Frontend** (`TutorDexWebsite/`) - ✅ basic test infrastructure exists (Mocha; see `TutorDexWebsite/test/`)

**Actions Required:**

#### Subtask B3.1: Matching Algorithm Tests (1 week)
- Create `tests/test_matching_comprehensive.py`
- 25+ test cases covering:
  - Subject/level matching (8 tests)
  - Distance filtering (5 tests)
  - Rate range validation (4 tests)
  - DM recipient limiting (3 tests)
  - Score calculation (3 tests)
  - Edge cases (2 tests)
- Target: 80% coverage for `matching.py`

#### Subtask B3.2: Worker Orchestration Tests (3 days)
- Create `tests/test_extract_worker_orchestration.py`
- Initial test coverage added (expand to full 15+ cases as needed):
  - Job claiming / oneshot exit
  - Health handler wiring
  - Max-jobs termination
- Target: 70% coverage for orchestration

#### Subtask B3.3: Frontend Test Infrastructure (2 days)
- Set up Vitest + React Testing Library
- Create `vitest.config.js`
- Add 10 basic tests for utility functions
- Document testing approach

**Success Criteria:**
- ✅ 40+ new tests added
- ✅ All tests passing
- ✅ Code coverage >80% for matching.py
- ✅ Frontend test infrastructure documented

**Estimated Effort:** 10 days (~2 weeks)

---

## Medium Priority: Legacy Cleanup (Phase C)

**Source:** `docs/PHASE_C_ROADMAP.md`  
**Status:** ⏳ READY FOR IMPLEMENTATION  
**Total Effort:** 2.5 days (~1 week with buffer)

### Task C1: Remove Unused Legacy Files

**Files to Remove:**
1. `TutorDexAggregator/monitor_message_edits.py` (749 lines)
2. `TutorDexAggregator/setup_service/` directory
3. Any `*.backup`, `*.bak`, `*~` files

**Actions Required:**
1. Verify no imports exist (30 min)
2. Check git history for recent usage (15 min)
3. Create `docs/REMOVED_FILES.md` (30 min)
4. Remove files (15 min)
5. Update documentation references (30 min)
6. Validate all tests pass (1 hour)

**Success Criteria:**
- ✅ Legacy files removed
- ✅ `docs/REMOVED_FILES.md` created
- ✅ `.gitignore` updated
- ✅ All tests pass
- ✅ Docker Compose services start successfully

**Status:** ✅ COMPLETE  
**Docs:** `docs/REMOVED_FILES.md`

---

### Task C2: Fix Circular Import Risks

**Problem:** `runtime.py` singleton pattern creates import fragility

**Actions Required:**
1. Create `TutorDexBackend/app_context.py` with DI container (2 hours)
2. Update FastAPI app.py to use AppContext (1 hour)
3. Update all 8 route files to use DI (3 hours)
4. Add deprecation warning to runtime.py (30 min)
5. Update all backend tests (2 hours)
6. Validation (1 hour)

**Success Criteria:**
- ✅ `app_context.py` created with dependency injection
- ✅ All 8 route files updated
- ✅ `runtime.py` marked deprecated
- ✅ All backend tests updated and passing
- ✅ No circular import errors

**Status:** ✅ COMPLETE (backend now uses `TutorDexBackend/app_context.py`; `TutorDexBackend/runtime.py` deprecated)

---

### Task C3: Add Import Linting

**Actions Required:**
1. Install `import-linter` (15 min)
2. Create `.import-linter.ini` with 5 contracts (30 min)
3. Add pre-commit hook (15 min)
4. Create CI workflow (30 min)
5. Create `docs/IMPORT_BOUNDARIES.md` (30 min)
6. Validation (30 min)

**Success Criteria:**
- ✅ Import linter installed
- ✅ Configuration created
- ✅ CI workflow active
- ✅ Documentation complete
- ✅ Import linter passes on current codebase

**Status:** ✅ COMPLETE  
**Config:** `.import-linter.ini`  
**CI:** `.github/workflows/import-lint.yml`  
**Docs:** `docs/IMPORT_BOUNDARIES.md`

---

## Ongoing: Documentation Consolidation & Validation

**Source:** `docs/CONSOLIDATION_PLAN.md`, `docs/PHASE_E_ROADMAP.md`  
**Status:** PARTIALLY COMPLETE

### Task A: Documentation Consolidation

**Status (as of 2026-01-16):** ✅ COMPLETE

**Remaining Actions:**
1. Execute file moves to archive directories (30 min)
2. Create README files for each archive directory (1 hour)
3. Update `docs/README.md` with archive references (30 min)
4. Update `DUPLICATE_DETECTION_INDEX.md` (30 min)

**Note:** Archive directories and READMEs exist under `docs/archive/` and `docs/README.md` links to them.

**Success Criteria:**
- ✅ 28 files moved to archive directories
- ✅ Archive READMEs created
- ✅ Main docs/README.md updated
- ✅ Active docs reduced from 52 → ~30 files

**Estimated Effort:** 2.5 hours

---

### Task E: Final Validation & Completion

**Actions Required:**

#### E1: End-to-End Smoke Testing (4 hours)
- Create smoke test scripts:
  - `scripts/smoke_test_backend.bat`
  - `scripts/smoke_test_aggregator.bat`
  - `scripts/smoke_test_observability.bat`
  - `scripts/smoke_test_integration.bat`
  - `scripts/smoke_test_all.bat`
- Run full test suite
- Validate all services healthy

**Status (as of 2026-01-16):** ✅ COMPLETE (scripts created and validated on a running stack via `scripts\\smoke_test_all.bat`)

#### E2: Update System Documentation (3 hours)
- Update `docs/SYSTEM_INTERNAL.md` with recent changes
- Update `.github/copilot-instructions.md`
- Create `docs/MIGRATION_GUIDE_2026-01.md`
- Update component READMEs

**Status (as of 2026-01-16):** ⏳ Partially complete
**Notes:** Unit tests require `pytest-asyncio` for `@pytest.mark.asyncio` tests (install with `py -3.12 -m pip install pytest-asyncio`).

#### E3: Create Completion Report (4 hours)
- Create `docs/IMPLEMENTATION_COMPLETION_REPORT_2026-01.md`
- Document all changes and metrics
- Provide deployment checklist
- Document rollback procedures

**Status (as of 2026-01-16):** ✅ COMPLETE (updated after smoke tests + full pytest pass)

**Success Criteria:**
- ✅ All smoke tests passing
- ✅ Documentation fully updated
- ✅ Completion report finalized
- ✅ Production readiness confirmed

**Estimated Effort:** 11 hours (1.5 days)

---

## Validation Checklists from AGENT_HANDOVER

**Source:** `docs/AGENT_HANDOVER_COMPLETE_REFACTORING.md`

These are outstanding validation tasks that should be completed after refactoring work:

### Backend Validation (Partially Complete)
- [ ] Worker starts without errors
- [ ] Jobs are claimed successfully
- [ ] LLM extraction works
- [ ] Enrichment pipeline executes
- [ ] Validation catches bad data
- [ ] Persistence succeeds
- [ ] Metrics are recorded
- [ ] No production regressions

### Frontend Validation (Outstanding)
- [ ] Load page → see assignment list
- [ ] Select subject → list filters correctly
- [ ] Select level → list filters correctly
- [ ] Enter rate range → list filters correctly
- [ ] Enter location → list filters correctly
- [ ] Enter search text → list filters correctly
- [ ] Toggle view mode → UI changes
- [ ] No JavaScript errors in console
- [ ] Performance acceptable (no lag)
- [ ] Mobile responsive
- [ ] Accessibility maintained

### Collector Validation (Outstanding)
- [ ] Messages collected successfully
- [ ] Filtering works correctly
- [ ] Deduplication works
- [ ] Storage successful
- [ ] Extraction jobs enqueued
- [ ] Broadcast delivers correctly
- [ ] DMs send successfully (test mode)
- [ ] No Telegram API errors
- [ ] Metrics recorded

**Note:** These validations should be incorporated into the smoke test suite (Task E1).

---

## Security & Maintenance Tasks

**Source:** `docs/AUDIT_ACTION_PLAN_2026-01-15.md`

### Completed (Already Validated) ✅
- **Priority 1:** Pin dependencies & fix CVEs - COMPLETE
- **Priority 3:** Enable automated security scanning - COMPLETE

### Outstanding
- **Continuous:** Monitor Dependabot PRs weekly
- **Continuous:** Review security scan results
- **Continuous:** Keep dependencies up to date

---

## Summary by Priority

### 🔴 Critical (Start Immediately)
1. **Task B1:** Consolidate Supabase clients (2 weeks)
2. **Task B2:** Fix silent failures (2 weeks)
3. **Task B3:** Add critical tests (2 weeks)

**Total Critical Path:** 6 weeks (sequential) or 2-3 weeks (parallel with 3 devs)

### 🟡 High (Start After Critical)
1. **Task C1:** Remove legacy files (0.5 days)
2. **Task C2:** Fix circular imports (1.5 days)
3. **Task C3:** Add import linting (0.5 days)

**Total High Priority:** 2.5 days

### 🟢 Medium (Ongoing/Final)
1. **Task A:** Documentation consolidation (2.5 hours)
2. **Task E:** Final validation & reports (1.5 days)

**Total Medium Priority:** 2 days

---

## Recommended Execution Order

### Week 1-2: Critical Risk Mitigation (Parallel Execution)
- **Developer 1:** Task B1 (Supabase consolidation)
- **Developer 2:** Task B2 (Silent failures)
- **Developer 3:** Task B3.1 (Matching tests)

### Week 3: Complete Critical + Start Cleanup
- **All Devs:** Complete B1, B2, B3.1
- **Developer 1:** Task B3.2 (Worker tests)
- **Developer 2:** Task B3.3 (Frontend tests)
- **Developer 3:** Task C1, C2, C3 (Legacy cleanup)

### Week 4: Final Validation
- **All Devs:** Tasks A & E (Documentation + validation)
- Run full smoke test suite
- Create completion report

---

## Dependencies & Blockers

### Task Dependencies
- **C2 (Circular imports)** should be done after **B1 (Supabase consolidation)**
- **E (Final validation)** requires all other tasks complete
- **B3 (Testing)** can run in parallel with B1 & B2

### External Dependencies
- LLM API availability (for extraction worker testing)
- Supabase instance (for integration testing)
- Firebase Auth (for frontend testing)

---

## Success Metrics

**Before (Current State):**
- Supabase implementations: 3
- Silent failures in critical paths: 120+
- Test coverage for matching.py: 0%
- Active documentation files: 52
- Circular import risk: HIGH

**After (Target State):**
- Supabase implementations: 1 (-67%)
- Silent failures in critical paths: <10 (-92%)
- Test coverage for matching.py: >80%
- Active documentation files: ~30 (-42%)
- Circular import risk: ZERO

---

## Risk Assessment

### High Risk Tasks
1. **B1 (Supabase consolidation)** - Could break production if not careful
   - **Mitigation:** Implement in phases, maintain backward compatibility
   
2. **B2 (Silent failures)** - Removing exception handlers could expose new failures
   - **Mitigation:** Review each instance, add proper logging and fallbacks
   
3. **C2 (Circular imports)** - Refactoring could introduce new import issues
   - **Mitigation:** Add import linting (C3) immediately after

### Medium Risk Tasks
1. **B3 (Testing)** - Tests might reveal existing bugs
   - **Mitigation:** Document bugs, prioritize critical fixes only
   
2. **C1 (Legacy removal)** - Might break undocumented dependencies
   - **Mitigation:** Thorough grep verification, archive files first

---

## Open Questions

1. **Deployment Strategy:** Should changes be deployed incrementally or all at once?
   - **Recommendation:** Deploy after each phase (B, C, E) to isolate issues

2. **Testing Time Investment:** What code coverage target?
   - **Recommendation:** 80% critical paths, 50% non-critical

3. **Frontend Testing Scope:** Full suite or just infrastructure?
   - **Recommendation:** Start with infrastructure + 10 basic tests

4. **Legacy File Removal:** Confirm `monitor_message_edits.py` is truly unused?
   - **Recommendation:** Verify via grep, check git history

---

## Next Actions

**Immediate (This Week):**
1. Get stakeholder approval for Phase B implementation
2. Assign developers to parallel tracks (B1, B2, B3)
3. Set up weekly progress reviews

**Short Term (Next 2 Weeks):**
1. Complete Task B1 (Supabase consolidation)
2. Complete Task B2 (Silent failures)
3. Complete Task B3.1 (Matching tests)

**Medium Term (Next 3-4 Weeks):**
1. Complete remaining Phase B tasks
2. Execute Phase C (Legacy cleanup)
3. Execute Phase E (Final validation)

---

## Resources & References

**Key Documents:**
- Implementation Plan: `docs/IMPLEMENTATION_PLAN_2026-01-16.md`
- Audit Action Plan: `docs/AUDIT_ACTION_PLAN_2026-01-15.md`
- Phase B Roadmap: `docs/PHASE_B_ROADMAP.md`
- Phase C Roadmap: `docs/PHASE_C_ROADMAP.md`
- Phase E Roadmap: `docs/PHASE_E_ROADMAP.md`
- Consolidation Plan: `docs/CONSOLIDATION_PLAN.md`
- Latest Audit: `docs/CODEBASE_QUALITY_AUDIT_2026-01-15.md`

**Progress Tracking:**
- Audit Checklist: `docs/AUDIT_CHECKLIST.md` (16/16 complete from previous cycle)

---

**Document Status:** ✅ COMPLETE  
**Last Updated:** January 16, 2026  
**Next Review:** After Phase B completion
