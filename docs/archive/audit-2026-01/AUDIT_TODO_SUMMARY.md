# Audit TODO Summary - Quick Reference

**Source:** Codebase Quality Audit (January 2026)  
**Status:** 7 of 10 priorities complete  
**Last Updated:** 2026-01-13

---

## ✅ Completed (Priorities 1-7)

| Priority | Task | Status | Effort | Files |
|----------|------|--------|--------|-------|
| 1 | Fail Fast on Auth | ✅ Already Done | - | `app.py` (lines 58-70) |
| 2 | RPC 300 Detection | ✅ Implemented | 1h | `supabase_env.py` |
| 3 | LLM Circuit Breaker | ✅ Implemented | 2-3h | `circuit_breaker.py` (+151 lines) |
| 4 | Extract app.py Services | ✅ Refactored | 5h | 1547→1033 lines, 8 modules |
| 5 | Migration Tracking | ✅ Implemented | 2h | `scripts/migrate.py` |
| 6 | Frontend Error Reporting | ✅ Implemented | 2h | `errorReporter.js` + Sentry |
| 7 | Break Up supabase_persist.py | ✅ Refactored | - | 1311→416 lines, 6 service modules |

**Total Completed:** ~12 hours of implementation + supabase_persist refactor

**Note:** Priority 7 was discovered to be already complete on 2026-01-13. The file was refactored into 6 focused service modules.

---

## 🚧 Remaining High-Priority Tasks

### **Phase 1: Foundation (Next 2 Weeks)**

#### Task 1: HTTP Integration Tests ⭐ CRITICAL
- **Effort:** 2-3 days
- **Impact:** HIGH - Enables safe refactoring
- **Files:** Create `tests/test_backend_api.py`
- **What:** Test all 30 API endpoints with FastAPI TestClient
- **Why:** Catch breaking changes in CI, refactor with confidence

#### Task 2: Consolidate Environment Config
- **Effort:** 2-3 days
- **Impact:** MEDIUM - Reduces config errors
- **Files:** Create `shared/config.py` with pydantic-settings
- **What:** Single source of truth for all config across services
- **Why:** Type-safe defaults, easier to audit required vars

### **Phase 2: Observability (Next 1-2 Weeks)** ✅ **Task 4 Complete!**

#### Task 3: End-to-End Tracing
- **Effort:** 1 week
- **Impact:** MEDIUM - Better debugging
- **Files:** `observability/tempo/`, enable OTEL everywhere
- **What:** Trace message → extraction → persist → broadcast → DM
- **Why:** Understand end-to-end latency, debug multi-stage failures

#### ~~Task 4: Break Up supabase_persist.py~~ ✅ **COMPLETED**
- **Original Estimate:** 2-3 weeks
- **Status:** Already refactored (discovered 2026-01-13)
- **Result:** 1311 lines → 416 lines (68% reduction)
- **Extracted Modules:** 
  - `services/row_builder.py` (491 lines)
  - `services/merge_policy.py` (148 lines)
  - `services/geocoding_service.py` (101 lines)
  - `services/event_publisher.py` (71 lines)
  - `services/persistence_operations.py` (71 lines)

---

## 📋 Additional Improvements (Low Priority)

| Task | Effort | Impact | Description |
|------|--------|--------|-------------|
| 5. Assignment State Machine | 2-3 days | MEDIUM | Enforce valid status transitions |
| 6. Business Metrics | 1-2 days | MEDIUM | Add "assignments/hour", "active tutors" |
| 7. Rate Limiting | 1 day | MEDIUM | Protect public endpoints from abuse |
| 8. Consolidate Supabase Clients | 2-3 days | LOW | Single SupabaseClient class |
| 9. Document Dependencies | 1 day | LOW | Add DEPENDENCIES.md, bootstrap.sh |
| 10. Pre-commit Hook | 1 hour | LOW | Warn on files >500 lines |

---

## 📊 Effort Breakdown

### By Phase
- **Phase 1 (Foundation):** 4-6 days
- **Phase 2 (Observability):** 1 week (Task 4 complete)
- **Phase 3 (Improvements):** 1-2 weeks

**Total:** 2-4 weeks of focused work

**Update:** Original estimate was 5-7 weeks, but Priority 7 (Task 4: Break Up supabase_persist.py) was discovered to be already complete, reducing remaining work by ~3 weeks.

### By Priority
- **Critical (Must Do):** Task 1 = ~3 days
- **High Value (Should Do):** Task 2 + Task 3 = ~2 weeks
- **Nice to Have (Could Do):** Tasks 5-10 = ~2 weeks

---

## 🎯 Recommended Sequence

**Week 1-2:**
1. Task 1: HTTP Integration Tests (2-3 days)
   - *Critical for safe refactoring*
2. Task 2: Consolidate Config (2-3 days)
   - *Reduces operational errors*

**Week 3:**
3. Task 3: End-to-End Tracing (1 week)
   - *Better debugging and MTTR*

**Ongoing:**
4. Tasks 5-10 as time permits based on operational needs

**Note:** ~~Task 4 (Break Up supabase_persist.py)~~ has been completed, significantly reducing the remaining work.

---

## 🚨 Critical Success Factors

### For All Tasks:
- ✅ Follow recommended sequence (Tasks 1→2→3)
- ✅ Complete tests before any major refactoring
- ✅ Small, incremental changes
- ✅ Document as you implement

### Risk Mitigation:
- **Week 1 of Task 4:** Extract domain objects, don't integrate yet
- **Week 2 of Task 4:** Extract services with interfaces, add unit tests
- **Week 3 of Task 4:** Integration + parallel run + cutover

---

## 📖 References

- **Full Implementation Guide:** `docs/REMAINING_AUDIT_TASKS.md`
- **Full Audit Report:** `docs/CODEBASE_QUALITY_AUDIT_2026-01.md`
- **Quick Actions:** `docs/AUDIT_QUICK_ACTIONS.md`
- **Completed Work:** `docs/IMPLEMENTATION_PRIORITIES_1-3.md`

---

## 🎓 Key Learnings from Completed Work

**What Worked Well (Priorities 1-6):**
- ✅ Small, focused PRs (1-3 hours each for P1-P3)
- ✅ Comprehensive tests before integration
- ✅ Clear documentation and runbooks
- ✅ Backward compatible changes

**What to Carry Forward:**
- ✅ Same pattern for remaining tasks
- ✅ Test extensively before integration
- ✅ Document as you go
- ✅ Feature flags for risky changes

---

**Status:** Ready for implementation  
**Next Action:** Start Task 1 (HTTP Integration Tests)  
**Expected Completion:** 6-8 weeks for all remaining tasks
