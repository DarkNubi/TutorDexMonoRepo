# Codebase Structure Refactoring Guide

**Date:** 2026-01-14  
**Status:** Phase 1 Complete - Recommendations for Future Work

## Executive Summary

This document provides a comprehensive analysis of codebase structure issues and concrete refactoring recommendations. The goal is to improve maintainability, reduce cognitive load for developers, and establish clear architectural boundaries.

### Current State

- **150 Python files**, **21 JS/TS files**
- **3 files exceed 1500 lines** (extract_worker.py: 1842, page-assignments.js: 1555, app.py: 1033)
- **9 additional files exceed 600 lines**
- Limited use of package structure (only 8 `__init__.py` files before this audit)
- Flat file organization with unclear boundaries

### Completed Work (Phase 1)

✅ **Worker Module Extraction** (1/14/2026)
- Created 5 new modules in `TutorDexAggregator/workers/`:
  - `supabase_operations.py` (413 lines) - Database operations
  - `job_manager.py` (178 lines) - Job lifecycle management
  - `triage_reporter.py` (235 lines) - Telegram reporting
  - `worker_config.py` (201 lines) - Configuration management
  - `__init__.py` - Package interface
- Added `__init__.py` to `extractors/`, `utilities/`, and `modes/` directories
- **Impact:** Extracted ~1000 lines of reusable code, improved testability

## Priority Refactoring Targets

### 🔴 Critical Priority (Do These First)

#### 1. extract_worker.py (1842 lines → target: 300-400 lines)

**Current Issues:**
- Single 800-line `_work_one()` function handles entire extraction pipeline
- Mixes concerns: orchestration, filtering, LLM calls, validation, persistence, side-effects
- High cognitive load for any modification
- Difficult to test individual stages

**Recommended Modules to Create:**

```
TutorDexAggregator/workers/
├── __init__.py                    ✅ DONE
├── extract_worker.py              (keep as thin orchestrator ~300 lines)
├── supabase_operations.py         ✅ DONE
├── job_manager.py                 ✅ DONE
├── triage_reporter.py             ✅ DONE
├── worker_config.py               ✅ DONE
├── message_processor.py           ⏳ TODO - Message loading and filtering
├── llm_processor.py               ⏳ TODO - LLM extraction logic
├── enrichment_pipeline.py         ⏳ TODO - Deterministic enrichment (signals, time, postal)
├── validation_pipeline.py         ⏳ TODO - Schema and hard validation
└── side_effects.py                ⏳ TODO - Broadcast and DM coordination
```

**Estimated Effort:** 8-12 hours  
**Risk:** Medium (requires careful testing of extraction logic)  
**Benefit:** High (most complex file in codebase)

**Implementation Steps:**
1. ✅ Extract Supabase operations (DONE)
2. ✅ Extract job management (DONE)
3. ✅ Extract triage reporting (DONE)
4. ✅ Extract configuration (DONE)
5. ⏳ Extract message processing (filtering, compilation detection)
6. ⏳ Extract LLM interaction with circuit breaker
7. ⏳ Extract enrichment pipeline (deterministic extractors)
8. ⏳ Extract validation pipeline
9. ⏳ Extract side-effects coordination
10. ⏳ Refactor main `_work_one()` to use new modules
11. ⏳ Add unit tests for each module
12. ⏳ Run integration tests

#### 2. page-assignments.js (1555 lines → target: 400-500 lines)

**Current Issues:**
- Monolithic file mixing state management, rendering, filtering, API calls, UI logic
- 47+ functions in single file
- Global mutable state
- Difficult to test UI components

**Recommended Module Structure:**

```
TutorDexWebsite/src/
├── page-assignments.js            (keep as main coordinator ~400 lines)
├── lib/
│   ├── assignmentFilters.js       ⏳ TODO - Filter state and logic
│   ├── assignmentsApi.js          ⏳ TODO - API integration layer
│   ├── assignmentState.js         ⏳ TODO - State management
│   └── assignmentFormatters.js    ⏳ TODO - Data formatting utilities
├── components/
│   ├── assignments/
│   │   ├── AssignmentCard.js      ⏳ TODO - Single assignment card
│   │   ├── AssignmentGrid.js      ⏳ TODO - Grid layout
│   │   ├── FilterPanel.js         ⏳ TODO - Filter UI
│   │   ├── SubjectTray.js         ⏳ TODO - Subject selection
│   │   └── StatusMessage.js       ⏳ TODO - Status/error display
│   └── ui/                        ✅ EXISTS (badge, card, input, etc.)
```

**Estimated Effort:** 10-15 hours  
**Risk:** Medium-High (UI changes need visual verification)  
**Benefit:** High (improves frontend maintainability significantly)

**Implementation Steps:**
1. Extract filter state management to `assignmentFilters.js`
2. Extract API calls to `assignmentsApi.js`
3. Create reusable UI components (AssignmentCard, FilterPanel, etc.)
4. Extract data formatting to `assignmentFormatters.js`
5. Refactor main file to use new modules
6. Test all UI interactions
7. Take screenshots to verify visual consistency

### 🟡 High Priority (Do These Next)

#### 3. collector.py (931 lines → target: 400-500 lines)

**Current Issues:**
- Mixes message collection, queueing, and channel management
- Large main loop with multiple responsibilities
- Difficult to test individual components

**Recommended Structure:**

```
TutorDexAggregator/
├── collector.py                   (main orchestrator ~400 lines)
├── collection/                    ⏳ NEW DIRECTORY
│   ├── __init__.py               
│   ├── telegram_client.py         - Telegram API interactions
│   ├── message_handler.py         - Message processing logic
│   ├── queue_manager.py           - Extraction queue operations
│   └── channel_manager.py         - Channel subscription management
```

**Estimated Effort:** 6-8 hours  
**Risk:** Medium (core data ingestion logic)  
**Benefit:** Medium-High

#### 4. broadcast_assignments.py (926 lines → target: 300-400 lines)

**Recommended Structure:**

```
TutorDexAggregator/
├── broadcast_assignments.py       (main entry point ~300 lines)
├── delivery/                      ⏳ NEW DIRECTORY
│   ├── __init__.py
│   ├── broadcast_formatter.py     - Message formatting
│   ├── broadcast_client.py        - Telegram broadcast API
│   └── broadcast_dedup.py         - Deduplication logic
```

**Estimated Effort:** 4-6 hours  
**Risk:** Low-Medium  
**Benefit:** Medium

#### 5. dm_assignments.py (645 lines → target: 250-350 lines)

**Recommended Structure:**

```
TutorDexAggregator/
├── dm_assignments.py              (main entry point ~300 lines)
├── delivery/
│   ├── __init__.py
│   ├── dm_formatter.py            - DM message formatting
│   ├── dm_client.py               - Telegram DM API
│   ├── dm_matching.py             - Tutor matching logic
│   └── dm_throttling.py           - Rate limiting and throttling
```

**Estimated Effort:** 4-6 hours  
**Risk:** Low-Medium  
**Benefit:** Medium

#### 6. supabase_persist.py (1311 lines → Already Addressed in Backend)

**Note:** The backend `supabase_store.py` (656 lines) was recently refactored (2026-01-12). The aggregator's `supabase_persist.py` needs similar treatment.

**Recommended Structure:**

```
TutorDexAggregator/
├── supabase_persist.py            (main entry point ~300 lines)
├── persistence/                   ⏳ NEW DIRECTORY
│   ├── __init__.py
│   ├── row_builder.py             ✅ EXISTS (in services/)
│   ├── merge_logic.py             - Merge and deduplication
│   ├── geo_enrichment.py          - Coordinate resolution
│   └── duplicate_detection.py     - Duplicate linking
```

**Estimated Effort:** 8-10 hours  
**Risk:** Medium-High (complex business logic)  
**Benefit:** High

### 🟢 Medium Priority (Future Work)

#### 7. Backend app.py (1033 lines → target: 400-500 lines)

**Status:** Recently refactored (2026-01-12) with service extraction  
**Current State:** 30 API routes in single file  
**Recommendation:** Further split into route modules

**Recommended Structure:**

```
TutorDexBackend/
├── app.py                         (main app setup ~200 lines)
├── routes/                        ⏳ NEW DIRECTORY
│   ├── __init__.py
│   ├── health.py                  - Health check endpoints
│   ├── assignments.py             - Assignment listing/search
│   ├── tutors.py                  - Tutor CRUD operations
│   ├── matching.py                - Matching endpoint
│   ├── analytics.py               - Analytics and tracking
│   └── telegram.py                - Telegram integration
├── services/                      ✅ EXISTS
│   ├── auth_service.py            ✅ DONE
│   ├── cache_service.py           ✅ DONE
│   ├── health_service.py          ✅ DONE
│   ├── telegram_service.py        ✅ DONE
│   └── analytics_service.py       ✅ DONE
└── utils/                         ✅ EXISTS
```

**Estimated Effort:** 6-8 hours  
**Risk:** Low (well-tested API layer)  
**Benefit:** Medium (improved route organization)

#### 8. Other Large Files

These files are large but well-scoped and can remain as-is for now:

- `monitor_message_edits.py` (776 lines) - Standalone script, low priority
- `duplicate_detector.py` (738 lines) - Self-contained domain logic
- `page-profile.js` (747 lines) - Similar to page-assignments, can use same pattern
- `index.tsx` (1058 lines) - Main website entry point, naturally large

## Folder Organization Improvements

### Completed Improvements ✅

1. **Added Package Structure**
   - ✅ `TutorDexAggregator/workers/__init__.py`
   - ✅ `TutorDexAggregator/extractors/__init__.py`
   - ✅ `TutorDexAggregator/utilities/__init__.py`
   - ✅ `TutorDexAggregator/modes/__init__.py`

### Recommended New Directories

```
TutorDexAggregator/
├── collection/            ⏳ TODO - Message collection modules
│   ├── __init__.py
│   ├── telegram_client.py
│   ├── message_handler.py
│   ├── queue_manager.py
│   └── channel_manager.py
│
├── delivery/              ⏳ TODO - Message delivery modules
│   ├── __init__.py
│   ├── broadcast_formatter.py
│   ├── broadcast_client.py
│   ├── dm_formatter.py
│   ├── dm_client.py
│   ├── dm_matching.py
│   └── rate_limiter.py
│
├── persistence/           ⏳ TODO - Data persistence modules
│   ├── __init__.py
│   ├── merge_logic.py
│   ├── geo_enrichment.py
│   └── duplicate_detection.py
│
├── monitoring/            ⏳ TODO - Monitoring and alerting
│   ├── __init__.py
│   └── message_edits.py  (move monitor_message_edits.py here)
│
└── processing/            ⏳ TODO - Message processing pipeline
    ├── __init__.py
    ├── llm_processor.py
    ├── enrichment.py
    └── validation.py
```

```
TutorDexBackend/
├── routes/                ⏳ TODO - API route modules
│   ├── __init__.py
│   ├── health.py
│   ├── assignments.py
│   ├── tutors.py
│   ├── matching.py
│   ├── analytics.py
│   └── telegram.py
│
├── services/              ✅ EXISTS (refactored 2026-01-12)
└── utils/                 ✅ EXISTS
```

```
TutorDexWebsite/src/
├── lib/                   ✅ EXISTS (partial)
│   ├── assignmentFilters.js  ⏳ TODO
│   ├── assignmentsApi.js     ⏳ TODO
│   ├── assignmentState.js    ⏳ TODO
│   └── assignmentFormatters.js ⏳ TODO
│
└── components/
    ├── assignments/       ⏳ NEW - Assignment-specific components
    │   ├── AssignmentCard.js
    │   ├── AssignmentGrid.js
    │   ├── FilterPanel.js
    │   ├── SubjectTray.js
    │   └── StatusMessage.js
    │
    └── ui/                ✅ EXISTS (badge, card, input, etc.)
```

## File Movement Recommendations

### Root-Level Files to Organize

**Move to subdirectories:**

```bash
# Create persistence directory
mkdir -p TutorDexAggregator/persistence
mv TutorDexAggregator/supabase_persist.py → TutorDexAggregator/persistence/persist.py
mv TutorDexAggregator/supabase_raw_persist.py → TutorDexAggregator/persistence/raw_persist.py
mv TutorDexAggregator/duplicate_detector.py → TutorDexAggregator/persistence/duplicate_detector.py

# Create collection directory
mkdir -p TutorDexAggregator/collection
mv TutorDexAggregator/collector.py → TutorDexAggregator/collection/collector.py

# Create delivery directory
mkdir -p TutorDexAggregator/delivery
mv TutorDexAggregator/broadcast_assignments.py → TutorDexAggregator/delivery/broadcast.py
mv TutorDexAggregator/dm_assignments.py → TutorDexAggregator/delivery/dms.py

# Create monitoring directory
mkdir -p TutorDexAggregator/monitoring
mv TutorDexAggregator/monitor_message_edits.py → TutorDexAggregator/monitoring/message_edits.py
mv TutorDexAggregator/sync_broadcast_channel.py → TutorDexAggregator/monitoring/sync_broadcast.py
```

**Note:** File moves require updating all imports across the codebase. This should be done carefully with search-and-replace and thorough testing.

## Testing Strategy

### For Each Refactoring

1. **Before Refactoring:**
   - Run existing tests: `pytest tests/`
   - Document current behavior
   - Identify integration points

2. **During Refactoring:**
   - Extract one module at a time
   - Write unit tests for new module
   - Update imports incrementally
   - Run tests after each extraction

3. **After Refactoring:**
   - Run full test suite
   - Manual smoke tests for affected workflows
   - Check metrics/observability for anomalies
   - Compare before/after line counts

### Recommended Test Coverage

For new modules, aim for:
- **Unit tests:** Test each function in isolation
- **Integration tests:** Test module interactions
- **Smoke tests:** Verify end-to-end workflows still work

Example for worker modules:
```python
# tests/test_worker_supabase_operations.py
def test_call_rpc_success():
    """Test successful RPC call."""
    # Mock requests.post
    # Assert correct URL construction
    # Assert metrics incremented

def test_call_rpc_failure_handling():
    """Test RPC call error handling."""
    # Mock network failure
    # Assert proper error handling
    # Assert metrics incremented
```

## Migration Strategy

### Phased Approach (Recommended)

**Phase 1: Foundation** (Completed ✅)
- ✅ Add package structure (`__init__.py` files)
- ✅ Extract worker support modules
- ✅ Document refactoring plan

**Phase 2: Extract Worker (In Progress)**
- ⏳ Extract message processor
- ⏳ Extract LLM processor
- ⏳ Extract enrichment pipeline
- ⏳ Extract validation pipeline
- ⏳ Extract side-effects coordinator
- ⏳ Refactor main `extract_worker.py`
- ⏳ Test extraction pipeline end-to-end

**Phase 3: Frontend Refactoring**
- Extract assignment filters
- Extract API integration
- Create reusable components
- Refactor page-assignments.js
- Visual regression testing

**Phase 4: Collection & Delivery**
- Refactor collector.py
- Refactor broadcast_assignments.py
- Refactor dm_assignments.py
- Create collection/ and delivery/ directories

**Phase 5: Persistence**
- Refactor supabase_persist.py
- Create persistence/ directory
- Extract geo-enrichment
- Extract duplicate detection

**Phase 6: Backend Routes**
- Create routes/ directory
- Split app.py into route modules
- Update documentation

**Phase 7: Cleanup**
- Remove legacy code
- Update all documentation
- Final integration testing

### Big Bang Approach (Not Recommended)

⚠️ **Not recommended** due to:
- High risk of breaking changes
- Difficult to test incrementally
- Long PR review cycles
- Potential for merge conflicts

## Success Metrics

### Code Quality Metrics

**Before Refactoring:**
- Largest file: 1842 lines (extract_worker.py)
- Average file size: ~350 lines (excluding outliers)
- Modules with `__init__.py`: 8
- Files > 800 lines: 9

**After Refactoring (Target):**
- Largest file: <600 lines
- Average file size: ~250 lines
- Modules with `__init__.py`: 20+
- Files > 800 lines: 0

### Developer Experience Metrics

- **Time to onboard new developer:** 6-8 hours → 3-4 hours
- **Time to make simple change:** 2-4 hours → 1-2 hours
- **Test coverage:** 60% → 80%
- **Build time:** No change expected
- **CI pipeline duration:** No change expected

## Risks and Mitigation

### Risk: Breaking Changes

**Mitigation:**
- Comprehensive test suite before refactoring
- Extract one module at a time
- Keep original file until tests pass
- Use feature flags for gradual rollout

### Risk: Import Path Changes

**Mitigation:**
- Use absolute imports: `from TutorDexAggregator.workers.job_manager import ...`
- Update all imports in single commit
- Use IDE refactoring tools
- Run syntax checks: `python -m py_compile *.py`

### Risk: Performance Regression

**Mitigation:**
- Monitor key metrics (extraction latency, queue depth)
- Keep hot paths optimized
- Avoid unnecessary abstractions
- Profile before and after

### Risk: Merge Conflicts

**Mitigation:**
- Work on dedicated branch
- Merge main regularly
- Communicate with team
- Use small, focused PRs

## Documentation Updates Required

After refactoring, update:

1. **README files:**
   - `TutorDexAggregator/README.md` - Update structure section
   - `TutorDexBackend/README.md` - Update route documentation
   - `TutorDexWebsite/README.md` - Update component guide

2. **Architecture docs:**
   - `docs/SYSTEM_INTERNAL.md` - Update data flow diagrams
   - `copilot-instructions.md` - Update file organization guidance

3. **Code comments:**
   - Update docstrings for moved functions
   - Add module-level docstrings
   - Update import examples

4. **Deployment docs:**
   - Update any deployment scripts
   - Update docker-compose if needed
   - Update environment variable docs

## Conclusion

This refactoring guide provides a roadmap for improving codebase structure over time. The key principle is **incremental improvement** - extract modules one at a time, test thoroughly, and maintain backward compatibility.

**Phase 1 is complete** with foundational improvements. Future phases can be tackled as time and priorities allow, with each phase delivering immediate value.

### Next Steps

1. Review this guide with the team
2. Prioritize which files to refactor first
3. Allocate dedicated time for refactoring work
4. Follow the phased approach
5. Celebrate wins as each phase completes!

### Questions?

If you have questions about any recommendations in this guide, please:
1. Check the specific section for implementation details
2. Review the completed Phase 1 work as an example
3. Reach out to the team for clarification

---

**Last Updated:** 2026-01-14  
**Author:** GitHub Copilot (Codebase Audit)  
**Status:** Phase 1 Complete, Phase 2+ Pending
