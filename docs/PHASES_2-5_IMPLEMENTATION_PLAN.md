# Phases 2-5 Implementation Plan

**Created:** January 14, 2026  
**Purpose:** Detailed, actionable plan for completing Phases 2-5

> **Status update (Jan 15, 2026):** This plan is now mostly a historical roadmap. Phases 2–4 were completed structurally via real modular splits:
> - Worker: `TutorDexAggregator/workers/extract_worker_*.py`
> - Collector: `TutorDexAggregator/collection/*`
> - Broadcast: `TutorDexAggregator/delivery/*`
> - Frontend: assignments page split into `TutorDexWebsite/src/page-assignments.{state,render,logic}.js` + tiny `page-assignments.impl.js`; landing moved under `TutorDexWebsite/src/landing/*` with `TutorDexWebsite/index.tsx` as a re-export.
> Remaining work is Phase 7 end-to-end verification (Telegram/Supabase/LLM + browser UI validation).

---

## Executive Summary

**Total Work Required:** ~31-41 hours (approximately 1 work week)

**Breakdown:**
- Phase 2 completion (100%): 5-7 hours
- Phase 3 completion (100%): 8-10 hours
- Phase 4 implementation (100%): 10-14 hours
- Phase 5 implementation (100%): 8-10 hours

**Current Status:**
- Phase 2: ✅ Structurally complete (worker split); needs Phase 7 verification
- Phase 3: ✅ Structurally complete (assignments + landing split); needs Phase 7 UI verification
- Phase 4: ✅ Structurally complete (collector + delivery split); needs Phase 7 verification
- Phase 5: 🟡 Optional deeper modularization (persistence) + Phase 7 verification

---

## Phase 2: Extract Worker Completion (5-7 hours)

### Current State
✅ **Done:**
- 6 modules created and tested
- utils.py, message_processor.py, llm_processor.py
- enrichment_pipeline.py, validation_pipeline.py, side_effects.py

⏳ **Remaining:**
- Refactor `_work_one()` function (800 lines → 150 lines)
- Remove 11 redundant helper functions
- Update imports throughout extract_worker.py
- End-to-end testing

### Implementation Steps

#### Step 1: Update Imports (30 min)
```python
# At top of extract_worker.py
from workers import (
    load_worker_config,
    claim_jobs,
    mark_job_status,
    fetch_raw_message,
    fetch_channel,
    call_rpc,
    try_report_triage_message,
)
from workers.utils import (
    _sha256,
    _ensure_text,
    _coerce_int,
    _extract_postal_from_text,
    build_message_link,
)
from workers.message_processor import (
    load_message_for_extraction,
    filter_message,
)
from workers.llm_processor import extract_with_llm
from workers.enrichment_pipeline import run_enrichment_pipeline
from workers.validation_pipeline import validate_schema, check_quality
from workers.side_effects import execute_side_effects
```

**Testing:** Verify imports resolve correctly

#### Step 2: Refactor _work_one() Function (2-3 hours)

**Before:** 800 lines with nested logic  
**After:** ~150 lines using extracted modules

```python
def _work_one(cfg: WorkerConfig, job: Dict[str, Any]) -> bool:
    """
    Process one extraction job.
    Returns True if job should be marked 'ok', False if 'failed'.
    """
    job_id = job.get("id")
    raw_id = job.get("raw_id")
    
    # 1. Load message
    msg_result = load_message_for_extraction(
        cfg.supabase_url, cfg.supabase_key, raw_id, job_id
    )
    if not msg_result["success"]:
        return False  # Already logged/reported
    
    raw_msg = msg_result["message"]
    channel_info = msg_result["channel"]
    
    # 2. Filter message
    filter_result = filter_message(raw_msg, channel_info)
    if filter_result["should_skip"]:
        # Report to triage if needed
        if filter_result.get("report_triage"):
            try_report_triage_message(
                cfg, raw_msg, channel_info, 
                filter_result["category"], 
                filter_result["reason"]
            )
        return True  # Job complete, just filtered
    
    # 3. Extract with LLM
    extraction_result = extract_with_llm(
        cfg, raw_msg, channel_info, job_id
    )
    if not extraction_result["success"]:
        return False  # Extraction failed
    
    canonical_json = extraction_result["data"]
    extraction_meta = extraction_result["meta"]
    
    # 4. Enrich
    enriched_result = run_enrichment_pipeline(
        cfg, canonical_json, raw_msg, extraction_meta
    )
    if not enriched_result["success"]:
        return False
    
    enriched_data = enriched_result["data"]
    enriched_meta = enriched_result["meta"]
    
    # 5. Validate
    validation_result = validate_schema(enriched_data)
    if not validation_result["valid"]:
        # Log validation errors
        return False
    
    quality_result = check_quality(enriched_data, enriched_meta)
    
    # 6. Persist (existing code - keep as is)
    persist_result = supabase_persist(
        cfg.supabase_url,
        cfg.supabase_key,
        raw_id,
        enriched_data,
        enriched_meta,
        quality_result["score"]
    )
    if not persist_result:
        return False
    
    # 7. Side effects (broadcast, DM)
    execute_side_effects(
        cfg, 
        enriched_data, 
        enriched_meta,
        persist_result.get("assignment_id")
    )
    
    return True
```

**Testing After Each Section:**
- Test with sample job from database
- Verify each step processes correctly
- Check metrics are recorded
- Verify error handling works

#### Step 3: Remove Redundant Functions (30 min)

Functions to remove (now in modules):
1. `_sha256()` → workers.utils
2. `_ensure_text()` → workers.utils
3. `_coerce_int()` → workers.utils
4. `_extract_postal_from_text()` → workers.utils
5. `build_message_link()` → workers.utils
6. All message loading logic → message_processor
7. All LLM extraction logic → llm_processor
8. All enrichment logic → enrichment_pipeline
9. All validation logic → validation_pipeline
10. All side-effects logic → side_effects

**Testing:** Verify no code references old functions

#### Step 4: End-to-End Testing (2-3 hours)

**Test Cases:**
1. **Normal extraction:** Valid message → successful extraction
2. **Filtered message:** Deleted/forwarded → skip with triage
3. **LLM failure:** Circuit breaker triggered → retry logic
4. **Validation failure:** Invalid data → proper error handling
5. **Side effects:** Broadcast and DM coordination
6. **Metrics:** All counters increment correctly

**Test Command:**
```bash
# Set test environment variables
export EXTRACTION_PIPELINE_VERSION="test_v1"
export EXTRACTION_WORKER_ONESHOT=1
export EXTRACTION_BROADCAST_ASSIGNMENTS=0
export EXTRACTION_DM_ASSIGNMENTS=0

# Run worker on test job
python TutorDexAggregator/workers/extract_worker.py
```

**Validation:**
- Check logs for errors
- Verify database updates
- Check metrics in Prometheus
- Verify no regressions

#### Step 5: Code Review (30 min)

Run automated code review:
```bash
python -m py_compile TutorDexAggregator/workers/extract_worker.py
```

**Checklist:**
- [ ] All imports resolve
- [ ] No undefined functions
- [ ] Error handling preserved
- [ ] Metrics instrumentation intact
- [ ] Type hints present
- [ ] Docstrings clear

---

## Phase 3: Frontend Completion (8-10 hours)

### Current State
✅ **Done:**
- 4 utility modules created
- assignmentFormatters.js, assignmentStorage.js
- domUtils.js, subjectUtils.js

⏳ **Remaining:**
- Extract rendering logic (~300 lines)
- Extract filter state management (~200 lines)
- Refactor main file to use modules
- UI testing

### Implementation Steps

#### Step 1: Create Additional Modules (3-4 hours)

**A. assignmentRenderer.js** (~250 lines)

Extract rendering functions:
- `renderAssignmentCard()`
- `renderCompactCard()`
- `renderSubjectChips()`
- `renderTimeAvailability()`
- `renderRateInfo()`

```javascript
// assignmentRenderer.js
import { formatRelativeTime, formatDistanceKm } from './assignmentFormatters.js';
import { subjectLabel } from './subjectUtils.js';
import { createElement } from './domUtils.js';

export function renderAssignmentCard(assignment, viewMode, options = {}) {
  const card = createElement('div', { 
    class: `assignment-card ${viewMode}` 
  });
  
  // Build card content using extracted formatters
  // ...
  
  return card;
}

export function renderSubjectChips(subjects, maxDisplay = 3) {
  // Extract and simplify subject chip rendering
  // ...
}
```

**B. filterManager.js** (~200 lines)

Extract filter state management:
- `initializeFilters()`
- `applyFilters(assignments, filters)`
- `updateFilterUI(filters)`
- `buildFilterQuery(filters)`

```javascript
// filterManager.js
export class FilterManager {
  constructor() {
    this.filters = {
      subjects: { general: [], canonical: [] },
      levels: [],
      minRate: null,
      maxRate: null,
      maxDistance: null,
      showNew: false
    };
  }
  
  applyFilters(assignments) {
    return assignments.filter(assignment => {
      // Apply all filter logic
      // ...
    });
  }
  
  // ... other methods
}
```

**Testing:** Verify modules export correctly

#### Step 2: Refactor page-assignments.js (3-4 hours)

**Target:** Reduce from 1555 → 400-500 lines

```javascript
// page-assignments.js
import { parseRate, toText, formatRelativeTime } from './lib/assignmentFormatters.js';
import { readViewMode, writeViewMode, readFilters, writeFilters } from './lib/assignmentStorage.js';
import { $id, setVisible, setText } from './lib/domUtils.js';
import { subjectKey, addSubjectSelection, removeSubjectSelection } from './lib/subjectUtils.js';
import { renderAssignmentCard } from './lib/assignmentRenderer.js';
import { FilterManager } from './lib/filterManager.js';

// Initialize
const filterManager = new FilterManager();
let allAssignments = [];

// Main functions become much simpler
async function loadAssignments(options = {}) {
  const filters = filterManager.getFilters();
  const query = filterManager.buildQuery();
  
  // Use existing backend.js for API calls
  const result = await listOpenAssignmentsPaged(query);
  
  // Render using extracted renderer
  renderAssignments(result.assignments);
}

function renderAssignments(assignments) {
  const grid = $id('assignments-grid');
  const viewMode = readViewMode();
  
  grid.replaceChildren(
    ...assignments.map(a => renderAssignmentCard(a, viewMode))
  );
}
```

**Testing:** Manual UI testing in browser

#### Step 3: UI Testing (2-3 hours)

**Test Scenarios:**
1. **Page load:** Verify assignments load correctly
2. **Filtering:** Test subject, level, rate filters
3. **View modes:** Toggle between full/compact
4. **Interactions:** Click cards, select subjects
5. **Persistence:** Filters saved to localStorage
6. **Responsiveness:** Mobile and desktop layouts

**Browser Testing:**
- Chrome
- Firefox
- Safari (if available)

**Validation Checklist:**
- [ ] No console errors
- [ ] All interactions work
- [ ] Filters apply correctly
- [ ] View mode persists
- [ ] Performance acceptable
- [ ] No visual regressions

#### Step 4: Code Review (30 min)

**Checklist:**
- [ ] All imports resolve
- [ ] No undefined functions
- [ ] Event handlers attached
- [ ] No memory leaks
- [ ] Clean console output

---

## Phase 4: Collection & Delivery (10-14 hours)

### Files to Refactor

1. **collector.py** (931 lines → 400-500 lines)
2. **broadcast_assignments.py** (926 lines → 300-400 lines)
3. **dm_assignments.py** (645 lines → 250-350 lines)

### Implementation Steps

#### Step 1: Create Collection Modules (4-5 hours)

**A. TutorDexAggregator/collection/telegram_client.py** (~200 lines)

Extract Telegram client management:
- Client initialization
- Connection handling
- Error recovery

```python
"""
Telegram client management for collector.
"""
from telethon import TelegramClient
from typing import Optional

class CollectorTelegramClient:
    """Manages Telegram client lifecycle for collector."""
    
    def __init__(self, api_id: int, api_hash: str, session_name: str):
        self.api_id = api_id
        self.api_hash = api_hash
        self.session_name = session_name
        self.client: Optional[TelegramClient] = None
    
    async def connect(self) -> bool:
        """Connect to Telegram. Returns True if successful."""
        # Implementation
        pass
    
    async def disconnect(self):
        """Disconnect from Telegram."""
        # Implementation
        pass
```

**B. TutorDexAggregator/collection/message_collector.py** (~250 lines)

Extract message collection logic:
- Channel iteration
- Message fetching
- Deduplication

**C. TutorDexAggregator/collection/queue_manager.py** (~200 lines)

Extract queue management:
- Job enqueueing
- Duplicate checking
- Batch operations

**Testing:** Unit tests for each module

#### Step 2: Refactor collector.py (2-3 hours)

Use new modules:
```python
from collection.telegram_client import CollectorTelegramClient
from collection.message_collector import MessageCollector
from collection.queue_manager import QueueManager

async def main():
    client = CollectorTelegramClient(api_id, api_hash, session)
    await client.connect()
    
    collector = MessageCollector(client, supabase_url, supabase_key)
    queue_mgr = QueueManager(supabase_url, supabase_key)
    
    for channel in channels:
        messages = await collector.collect_from_channel(channel)
        await queue_mgr.enqueue_batch(messages)
```

**Testing:** Run collector in test mode

#### Step 3: Create Delivery Modules (2-3 hours)

**A. TutorDexAggregator/delivery/broadcast_client.py** (~150 lines)

Extract broadcast logic:
- Channel posting
- Message formatting
- Error handling

**B. TutorDexAggregator/delivery/dm_client.py** (~200 lines)

Extract DM logic:
- Recipient selection
- Message personalization
- Rate limiting

**C. TutorDexAggregator/delivery/message_formatter.py** (~150 lines)

Extract message formatting:
- Template rendering
- Assignment formatting
- Link building

**Testing:** Unit tests for each module

#### Step 4: Refactor broadcast & dm files (2-3 hours)

Simplify using new modules.

**Testing:** End-to-end delivery testing

#### Step 5: Integration Testing (2-3 hours)

**Test full pipeline:**
1. Collector → Database
2. Extraction → Enrichment
3. Broadcast → Channel
4. DM → Recipients

**Validation:**
- No regressions
- All metrics working
- Error handling intact

---

## Phase 5: Persistence Layer (8-10 hours)

### Files to Refactor

1. **supabase_persist.py** (needs modularization)
2. **supabase_store.py** (backend, 656 lines)

### Implementation Steps

#### Step 1: Create Persistence Modules (4-5 hours)

**A. TutorDexAggregator/persistence/merge_logic.py** (~250 lines)

Extract merge logic:
- Conflict resolution
- Field prioritization
- Quality scoring

```python
"""
Assignment merge logic for persistence.
"""

def merge_assignments(existing: dict, incoming: dict, meta: dict) -> dict:
    """
    Merge incoming assignment with existing one.
    Returns merged assignment with conflict resolution.
    """
    # Conservative merge strategy
    # Prefer deterministic signals over LLM outputs
    # Use quality scores for tie-breaking
    pass
```

**B. TutorDexAggregator/persistence/deduplication.py** (~200 lines)

Extract deduplication:
- Fingerprint generation
- Similarity detection
- Duplicate handling

**C. TutorDexAggregator/persistence/data_mapper.py** (~150 lines)

Extract data mapping:
- Canonical JSON → DB schema
- Field validation
- Type conversion

**Testing:** Unit tests with sample data

#### Step 2: Refactor supabase_persist.py (2-3 hours)

Use new modules:
```python
from persistence.merge_logic import merge_assignments
from persistence.deduplication import find_duplicates
from persistence.data_mapper import map_to_db_schema

def supabase_persist(url, key, raw_id, canonical, meta, quality_score):
    # Map to DB schema
    db_data = map_to_db_schema(canonical, meta)
    
    # Check for duplicates
    duplicates = find_duplicates(url, key, db_data)
    
    if duplicates:
        # Merge with existing
        merged = merge_assignments(duplicates[0], db_data, meta)
        # Update
    else:
        # Insert new
        pass
```

**Testing:** Database integration tests

#### Step 3: Refactor Backend supabase_store.py (2-3 hours)

Extract backend database operations:
- Query builders
- Response formatters
- Pagination helpers

**Testing:** API integration tests

#### Step 4: Integration Testing (1-2 hours)

**Test scenarios:**
- New assignment insertion
- Duplicate detection
- Assignment updates
- Quality scoring

**Validation:**
- Data integrity maintained
- No duplicates created
- Merge logic correct

---

## Testing Strategy

### After Each Phase

1. **Unit Tests:** Test individual modules
2. **Integration Tests:** Test module interactions
3. **End-to-End Tests:** Test full pipeline
4. **Code Review:** Automated checks
5. **Manual Validation:** Verify behavior

### Test Commands

```bash
# Python syntax check
python -m py_compile <file>

# Run specific test
pytest tests/test_<module>.py

# End-to-end test
python scripts/smoke_test.py

# Check imports
python -c "from workers import *; print('OK')"
```

---

## Risk Management

### High Risk Areas

1. **Phase 2:** `_work_one()` refactor (core extraction logic)
2. **Phase 3:** UI interactions (user-facing changes)
3. **Phase 5:** Merge logic (data integrity)

### Mitigation

1. **Backup:** Keep original code until fully tested
2. **Incremental:** Make small, tested changes
3. **Rollback plan:** Document how to revert
4. **Feature flags:** Use environment variables to toggle new code
5. **Monitoring:** Watch metrics after deployment

---

## Success Criteria

### Phase 2 Complete When:
- [ ] extract_worker.py uses all 6 modules
- [ ] File reduced to ~900 lines
- [ ] All tests pass
- [ ] Extraction pipeline works end-to-end
- [ ] Metrics show no regressions

### Phase 3 Complete When:
- [ ] page-assignments.js uses all utility modules
- [ ] File reduced to ~500 lines
- [ ] All UI interactions work
- [ ] No console errors
- [ ] Visual regression tests pass

### Phase 4 Complete When:
- [ ] collector.py reduced to ~450 lines
- [ ] broadcast/dm files simplified
- [ ] Collection pipeline works
- [ ] Delivery works correctly

### Phase 5 Complete When:
- [ ] supabase_persist.py modularized
- [ ] Merge logic extracted
- [ ] Data integrity maintained
- [ ] No duplicate assignments created

---

## Timeline

**Realistic Schedule:**

- **Phase 2:** 1 day (5-7 hours)
- **Phase 3:** 1-2 days (8-10 hours)
- **Phase 4:** 2 days (10-14 hours)
- **Phase 5:** 1 day (8-10 hours)

**Total:** 5-6 work days

**Recommended:** 2 weeks to allow for:
- Proper testing
- Code reviews
- Documentation updates
- Buffer for unexpected issues

---

## Next Steps

1. **Review this plan** with team
2. **Allocate dedicated time** - block calendar
3. **Set up test environment** - separate from production
4. **Start with Phase 2** - proven pattern
5. **Track progress** - update documentation

---

**This plan provides:**
- ✅ Concrete steps for each phase
- ✅ Code examples and patterns
- ✅ Testing strategies
- ✅ Risk mitigation
- ✅ Realistic timelines
- ✅ Success criteria

**Ready to execute** with proper time allocation and resources.
