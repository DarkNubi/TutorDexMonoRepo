# Phase 2 Completion Guide - Final Refactoring Step

> **Status update (Jan 15, 2026):** This guide is now a historical plan. The worker refactor is structurally complete: `TutorDexAggregator/workers/extract_worker.py` is a thin entrypoint and the logic is split across `TutorDexAggregator/workers/extract_worker_*.py`. The remaining work is Phase 7 end-to-end verification with real Supabase + LLM + Telegram credentials.

## Status

**Completed:**
- ✅ Extracted 6 focused modules (~1,030 lines)
- ✅ All modules tested and validated
- ✅ Code review feedback addressed
- ✅ Clean module boundaries established

**Remaining:**
- ⏳ End-to-end testing (Phase 7) in a fully provisioned environment (Supabase + LLM + Telegram)

## Current State

**Current structure (post-refactor):**
- Entrypoint: `TutorDexAggregator/workers/extract_worker.py`
- Orchestration: `TutorDexAggregator/workers/extract_worker_main.py`
- Job processing: `TutorDexAggregator/workers/extract_worker_job.py`
- Compilation path: `TutorDexAggregator/workers/extract_worker_compilation.py`
- Standard path: `TutorDexAggregator/workers/extract_worker_standard.py` + `TutorDexAggregator/workers/extract_worker_standard_persist.py`
- Supporting modules: `TutorDexAggregator/workers/extract_worker_triage.py`, `TutorDexAggregator/workers/extract_worker_store.py`, `TutorDexAggregator/workers/extract_worker_enrich.py`, `TutorDexAggregator/workers/extract_worker_metrics.py`

## Target State

**Target state:** Achieved for repo structure/size; proceed to Phase 7 verification.

## Refactoring Pattern

### Before (Current)
```python
def _work_one(url: str, key: str, job: Dict[str, Any]) -> str:
    # 800 lines of mixed concerns:
    # - Message loading
    # - Filtering
    # - LLM extraction
    # - Enrichment
    # - Validation
    # - Persistence
    # - Side effects
    ...
```

### After (Target)
```python
def _work_one(url: str, key: str, job: Dict[str, Any]) -> str:
    # 1. Load and filter message
    context = message_processor.build_extraction_context(job, raw, ch_info)
    filter_result = message_processor.filter_message(raw, context["channel_link"], ch_info)
    if filter_result.should_skip:
        return handle_skip(...)
    
    # 2. Extract with LLM
    parsed, llm_error, llm_latency = llm_processor.extract_with_llm(...)
    if llm_error:
        return handle_extraction_error(...)
    
    # 3. Enrich
    parsed, enrich_meta = enrichment_pipeline.run_enrichment_pipeline(...)
    
    # 4. Validate
    ok, errors = validation_pipeline.validate_schema(parsed, validate_func)
    if not ok:
        return handle_validation_error(...)
    
    # 5. Persist
    persist_result = persist_assignment_to_supabase(payload)
    
    # 6. Side effects (best-effort)
    side_effects.execute_side_effects(payload, config, modules, cid)
    
    return "ok"
```

## Functions to Remove/Simplify

These functions are now in modules and can be removed from extract_worker.py:

### Can Remove Entirely (in modules now):
- `_sha256()` → `utils.sha256_hash()`
- `_extract_sg_postal_codes()` → `utils.extract_sg_postal_codes()`
- `_coerce_list_of_str()` → `utils.coerce_list_of_str()`
- `_build_message_link()` → `utils.build_message_link()`
- `_utc_now_iso()` → `utils.utc_now_iso()`
- `_llm_model_name()` → `llm_processor.get_llm_model_name()`
- `_classify_llm_error()` → `llm_processor.classify_llm_error()`
- `_fill_postal_code_from_text()` → `enrichment_pipeline.fill_postal_code_from_text()`
- `_inc_quality_missing()` → `validation_pipeline.increment_quality_missing()`
- `_inc_quality_inconsistency()` → `validation_pipeline.increment_quality_inconsistency()`
- `_quality_checks()` → `validation_pipeline.run_quality_checks()`

### Can Simplify:
- `_fetch_raw()` → Use `message_processor.load_raw_message()`
- `_fetch_channel()` → Use `message_processor.load_channel_info()`
- `_mark_extraction()` → Use `job_manager.mark_job_status()`

### Keep (specific to worker loop):
- `_hard_mode()` → Configuration helper
- `_signals_enabled()` → Configuration helper
- `_deterministic_time_enabled()` → Configuration helper
- `_postal_code_estimated_enabled()` → Configuration helper
- `_requeue_stale_processing()` → Use `job_manager.requeue_stale_jobs()`
- `_queue_counts()` → Use `supabase_operations.get_queue_counts()`
- `_oldest_created_age_s()` → Use `supabase_operations.get_oldest_created_age_seconds()`

### Keep (compilation handling - complex logic):
- All compilation-related functions (not yet refactored)
- `_try_report_triage_message()` → Use `triage_reporter.try_report_triage_message()`

## Implementation Steps

1. **Import new modules** at top of extract_worker.py
2. **Remove redundant functions** (listed above)
3. **Refactor `_work_one()`** to use new modules:
   - Extract message loading into message_processor calls
   - Extract LLM calls into llm_processor calls
   - Extract enrichment into enrichment_pipeline calls
   - Extract validation into validation_pipeline calls
   - Extract side effects into side_effects calls
4. **Update helper function calls** throughout
5. **Test** - Run syntax check, ensure imports work
6. **Manual validation** - Verify logic flow is preserved

## Testing Checklist

After refactoring:
- [ ] Python syntax check passes
- [ ] All imports resolve correctly
- [ ] No circular import issues
- [ ] Main loop logic preserved
- [ ] Error handling paths maintained
- [ ] Metrics instrumentation intact
- [ ] Circuit breaker integration works
- [ ] Configuration flags respected

## Estimated Effort

- Refactoring `_work_one()`: 3-4 hours
- Removing redundant functions: 1 hour
- Testing and validation: 1-2 hours
- **Total: 5-7 hours**

## Risk Mitigation

1. **Preserve behavior**: Keep original file as `.backup` until tested
2. **Incremental changes**: Refactor one section at a time
3. **Test frequently**: Run syntax checks after each change
4. **Document differences**: Note any behavior changes

## Success Criteria

- ✅ extract_worker.py reduced from 1842 to ~900 lines (50% reduction)
- ✅ `_work_one()` function reduced from ~800 to ~150 lines (81% reduction)
- ✅ All syntax checks pass
- ✅ Module boundaries clear
- ✅ Code more maintainable and testable
- ✅ Zero regressions in functionality

## Next Phase

After Phase 2 completion:
- **Phase 3:** Frontend refactoring (page-assignments.js: 1555 → 400-500 lines)
- **Phase 4:** Collection & delivery (3 files)
- **Phase 5:** Persistence layer
- **Phase 6:** Backend routes
- **Phase 7:** Cleanup
