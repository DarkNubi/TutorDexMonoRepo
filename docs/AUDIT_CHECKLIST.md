# Audit Implementation Checklist

**Source:** Codebase Quality Audit (January 2026)  
**Created:** 2026-01-13  
**Progress:** 6/16 items complete (38%)

---

## ✅ Completed Items (6)

- [x] **Priority 1:** Fail Fast on Auth Misconfiguration
  - Status: Already implemented in app.py startup checks
  - Impact: Prevents critical security vulnerability

- [x] **Priority 2:** Detect Supabase RPC 300 Errors
  - Status: Implemented in supabase_env.py
  - Impact: Prevents silent data loss

- [x] **Priority 3:** Add LLM Circuit Breaker
  - Status: Implemented in circuit_breaker.py
  - Impact: Prevents queue burn when LLM down

- [x] **Priority 4:** Extract Domain Services from app.py
  - Status: Refactored 1547→1033 lines (33% reduction)
  - Impact: 4× faster onboarding, easier testing

- [x] **Priority 5:** Add Migration Version Tracking
  - Status: Implemented scripts/migrate.py
  - Impact: Safe deploys, clear audit trail

- [x] **Priority 6:** Add Frontend Error Reporting
  - Status: Sentry integration complete
  - Impact: Visibility into user-facing errors

---

## 🚧 Phase 1: Foundation (Next 2 Weeks)

- [ ] **Task 1: HTTP Integration Tests** ⭐ CRITICAL
  - **Effort:** 2-3 days
  - **Owner:** _________________
  - **Due Date:** _________________
  - **Files:** Create tests/test_backend_api.py
  - **Success:** 30+ tests for all endpoints, CI passing
  - **Blockers:** None
  - **Notes:**
    - Test all 30 API endpoints with TestClient
    - Mock Firebase auth for isolation
    - Required before Task 4 refactoring

- [ ] **Task 2: Consolidate Environment Config**
  - **Effort:** 2-3 days
  - **Owner:** _________________
  - **Due Date:** _________________
  - **Files:** Create shared/config.py with pydantic-settings
  - **Success:** All services use shared config, no env parsing duplication
  - **Blockers:** None
  - **Notes:**
    - Migrate one service at a time
    - Keep backward compatibility during transition

---

## 🏗️ Phase 2: Architecture (Next Month)

- [ ] **Task 3: End-to-End Tracing**
  - **Effort:** 1 week
  - **Owner:** _________________
  - **Due Date:** _________________
  - **Files:** observability/tempo/, enable OTEL everywhere
  - **Success:** Can trace message→extraction→persist→DM in Grafana
  - **Blockers:** None
  - **Notes:**
    - Enable OTEL by default in production
    - Add trace context propagation
    - Restore Tempo service

- [ ] **Task 4: Break Up supabase_persist.py** ⭐ HIGHEST IMPACT
  - **Effort:** 2-3 weeks
  - **Owner:** _________________
  - **Due Date:** _________________
  - **Files:** Extract to domain/, services/ (5 modules)
  - **Success:** 1311 lines → 5 modules <400 lines each, zero behavior change
  - **Blockers:** Task 1 must be complete
  - **Notes:**
    - **CRITICAL:** Run new code in parallel with old code
    - Compare outputs before cutover
    - Gradual rollout: 10% → 50% → 100%
  - **Sub-tasks:**
    - [ ] Week 1: Extract domain objects (assignment.py, merge_policy.py)
    - [ ] Week 2: Extract services (geo_enrichment.py, event_publisher.py)
    - [ ] Week 3: Integration + parallel run + cutover

---

## 📋 Phase 3: Additional Improvements (Ongoing)

- [ ] **Task 5: Assignment State Machine**
  - **Effort:** 2-3 days
  - **Priority:** MEDIUM
  - **Notes:** Enforce valid status transitions (open→closed→deleted)

- [ ] **Task 6: Business Metrics**
  - **Effort:** 1-2 days
  - **Priority:** MEDIUM
  - **Notes:** Add "assignments/hour", "active tutors", "time-to-match"

- [ ] **Task 7: Rate Limiting on Public Endpoints**
  - **Effort:** 1 day
  - **Priority:** MEDIUM
  - **Notes:** Use slowapi to prevent endpoint abuse

- [ ] **Task 8: Consolidate Supabase Clients**
  - **Effort:** 2-3 days
  - **Priority:** LOW
  - **Notes:** Single SupabaseClient class, remove duplication

- [ ] **Task 9: Document External Dependencies**
  - **Effort:** 1 day
  - **Priority:** LOW
  - **Notes:** Create DEPENDENCIES.md, scripts/bootstrap.sh

- [ ] **Task 10: Pre-commit Hook for Large Files**
  - **Effort:** 1 hour
  - **Priority:** LOW
  - **Notes:** Warn on files >500 lines

---

## 📊 Progress Tracking

### Overall Progress
- **Completed:** 6 items (38%)
- **In Progress:** ___ items
- **Remaining:** 10 items (62%)

### Time Tracking
- **Time Spent (Priorities 1-6):** ~12 hours
- **Time Estimated (Remaining):** 5-7 weeks
- **Actual Time Spent (This Sprint):** _________
- **Variance:** _________

### Milestones
- [ ] **Milestone 1:** Phase 1 Complete (Foundation)
  - Target: Week 2
  - Actual: _________
  
- [ ] **Milestone 2:** Phase 2 Complete (Architecture)
  - Target: Week 6
  - Actual: _________
  
- [ ] **Milestone 3:** All Tasks Complete
  - Target: Week 8
  - Actual: _________

---

## 🎯 Sprint Planning Template

### Sprint 1 (Week 1-2)
**Goal:** Complete Foundation Phase

**Planned:**
- [ ] Task 1: HTTP Integration Tests (2-3 days)
- [ ] Task 2: Consolidate Environment Config (2-3 days)

**Completed:**
- [ ] _____________________
- [ ] _____________________

**Blockers/Issues:**
- _____________________

**Retrospective:**
- What went well: _____________________
- What to improve: _____________________
- Carry forward: _____________________

---

### Sprint 2 (Week 3)
**Goal:** Add Observability

**Planned:**
- [ ] Task 3: End-to-End Tracing (1 week)

**Completed:**
- [ ] _____________________

**Blockers/Issues:**
- _____________________

**Retrospective:**
- What went well: _____________________
- What to improve: _____________________
- Carry forward: _____________________

---

### Sprint 3-4 (Week 4-6)
**Goal:** Major Refactoring

**Planned:**
- [ ] Task 4: Break Up supabase_persist.py (2-3 weeks)
  - [ ] Week 1: Extract domain objects
  - [ ] Week 2: Extract services
  - [ ] Week 3: Integration + cutover

**Completed:**
- [ ] _____________________
- [ ] _____________________
- [ ] _____________________

**Blockers/Issues:**
- _____________________

**Retrospective:**
- What went well: _____________________
- What to improve: _____________________
- Carry forward: _____________________

---

## 🚨 Risk Register

| Risk | Probability | Impact | Mitigation | Owner |
|------|-------------|--------|------------|-------|
| Task 4 introduces bugs in merge logic | MEDIUM | HIGH | Run in parallel, compare outputs, gradual rollout | _______ |
| Tests require extensive Firebase mocking | LOW | MEDIUM | Use TestClient with dependency overrides | _______ |
| Config consolidation breaks env parsing | LOW | MEDIUM | Keep backward compatibility, migrate incrementally | _______ |
| OTEL overhead impacts performance | LOW | LOW | Sample traces (10%), monitor latency metrics | _______ |

---

## 📖 Quick Links

- **Full Guide:** `docs/REMAINING_AUDIT_TASKS.md`
- **Quick Summary:** `docs/AUDIT_TODO_SUMMARY.md`
- **Audit Report:** `docs/CODEBASE_QUALITY_AUDIT_2026-01.md`
- **Completed Work:** `docs/IMPLEMENTATION_PRIORITIES_1-3.md`

---

## 📝 Notes

### Decision Log
- **2026-01-13:** Created comprehensive implementation guide
- **Date:** _____________________
- **Date:** _____________________

### Questions/Concerns
- _____________________
- _____________________

---

**Last Updated:** 2026-01-13  
**Next Review:** After Task 1 completion  
**Document Owner:** _________________
