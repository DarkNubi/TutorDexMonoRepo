# Duplicate Detection Implementation - Remaining Phases

## Completed Phases

### ✅ Phase 0: Validation (COMPLETE)
- Production database validated (3,840 assignments)
- Algorithm weights finalized
- Documentation complete (7 docs, 165KB+)

### ✅ Phase 1: Backend Detection (COMPLETE)
- Database schema with 3 tables
- Detection module with validated algorithm
- Aggregator integration (async, non-blocking)
- Migration SQL ready to deploy

### ✅ Phase 2: API Layer (COMPLETE)
- Duplicate endpoints (`/assignments/{id}/duplicates`, `/duplicate-groups/{id}`)
- Filtering parameter (`show_duplicates`)
- SQL RPC updated
- Backend ready for frontend integration

## Remaining Phases

### Phase 3: Website UI (Week 3)

#### 3.1 Duplicate Badges
**File**: `TutorDexWebsite/src/components/AssignmentCard.jsx`

Add badge to assignment cards showing duplicate status:
```jsx
// Add to AssignmentCard component
{assignment.duplicate_group_id && (
  <div className="duplicate-badge">
    <AlertCircle size={16} />
    <span>Also posted by {assignment.duplicate_count - 1} other agencies</span>
    <button onClick={() => openDuplicateModal(assignment.id)}>
      View All
    </button>
  </div>
)}
```

**CSS** (`TutorDexWebsite/src/styles/duplicates.css`):
```css
.duplicate-badge {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem;
  background: #fff3cd;
  border-left: 3px solid #ffc107;
  border-radius: 4px;
  font-size: 0.875rem;
  color: #856404;
}
```

#### 3.2 Duplicate Group Modal
**File**: `TutorDexWebsite/src/components/DuplicateModal.jsx`

Create modal component showing all versions side-by-side:
```jsx
import { useState, useEffect } from 'react';
import { X } from 'lucide-react';

export function DuplicateModal({ assignmentId, isOpen, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  
  useEffect(() => {
    if (isOpen && assignmentId) {
      fetchDuplicates();
    }
  }, [isOpen, assignmentId]);
  
  const fetchDuplicates = async () => {
    setLoading(true);
    try {
      const response = await fetch(`/api/assignments/${assignmentId}/duplicates`);
      const data = await response.json();
      setData(data);
    } finally {
      setLoading(false);
    }
  };
  
  if (!isOpen) return null;
  
  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal-content" onClick={e => e.stopPropagation()}>
        <div className="modal-header">
          <h2>Duplicate Assignments ({data?.duplicates?.length || 0})</h2>
          <button onClick={onClose}><X /></button>
        </div>
        
        <div className="duplicates-grid">
          {data?.duplicates?.map(assignment => (
            <div key={assignment.id} className={assignment.is_primary_in_group ? 'primary' : ''}>
              <h3>{assignment.agency_name}</h3>
              <div className="badge">{assignment.is_primary_in_group ? 'Primary' : 'Duplicate'}</div>
              <p>Code: {assignment.assignment_code}</p>
              <p>Posted: {new Date(assignment.published_at).toLocaleDateString()}</p>
              <p>Match: {assignment.duplicate_confidence_score?.toFixed(1)}%</p>
              <a href={assignment.message_link} target="_blank">View Original</a>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
```

#### 3.3 User Preference Toggle
**File**: `TutorDexWebsite/src/components/FilterPanel.jsx`

Add checkbox to filter duplicates:
```jsx
// Add to filter panel
<label className="filter-option">
  <input
    type="checkbox"
    checked={filters.showDuplicates}
    onChange={e => setFilters({...filters, showDuplicates: e.target.checked})}
  />
  Show duplicate assignments
</label>
```

**API Integration** (`TutorDexWebsite/src/api/assignments.js`):
```javascript
export async function fetchAssignments(filters = {}) {
  const params = new URLSearchParams({
    limit: filters.limit || 50,
    show_duplicates: filters.showDuplicates !== false ? 'true' : 'false',
    // ... other filters
  });
  
  const response = await fetch(`/api/assignments?${params}`);
  return response.json();
}
```

#### 3.4 Duplicate Count in Summary
**File**: `TutorDexWebsite/src/pages/HomePage.jsx`

Show duplicate statistics:
```jsx
<div className="stats-summary">
  <div className="stat">
    <span className="label">Total Assignments</span>
    <span className="value">{stats.total}</span>
  </div>
  <div className="stat">
    <span className="label">Unique Assignments</span>
    <span className="value">{stats.unique}</span>
  </div>
  <div className="stat">
    <span className="label">Duplicates Hidden</span>
    <span className="value">{stats.total - stats.unique}</span>
  </div>
</div>
```

### Phase 4: Telegram Distribution (Week 4)

#### 4.1 DM Filtering
**File**: `TutorDexAggregator/dm_assignments.py`

Update DM logic to skip non-primary duplicates:
```python
def should_send_dm(assignment: Dict[str, Any], tutor_chat_id: int) -> bool:
    """
    Check if DM should be sent for this assignment
    
    Returns False if:
    - Assignment is non-primary duplicate AND tutor already got primary
    - Assignment belongs to duplicate group already sent
    """
    # Skip non-primary duplicates
    if not assignment.get("is_primary_in_group", True):
        duplicate_group_id = assignment.get("duplicate_group_id")
        if duplicate_group_id:
            # Check if tutor already received primary from this group
            if has_received_from_group(tutor_chat_id, duplicate_group_id):
                logger.info(
                    f"Skipping DM for tutor {tutor_chat_id}: duplicate of already sent assignment",
                    extra={
                        "tutor_chat_id": tutor_chat_id,
                        "assignment_id": assignment["id"],
                        "duplicate_group_id": duplicate_group_id
                    }
                )
                return False
    
    return True


def has_received_from_group(tutor_chat_id: int, group_id: int) -> bool:
    """Check if tutor already received an assignment from this duplicate group"""
    # Query Redis or database for sent DM history
    # Implementation depends on DM tracking system
    pass


def format_dm_with_duplicate_info(assignment: Dict[str, Any]) -> str:
    """Add duplicate information to DM message"""
    message = format_standard_dm(assignment)
    
    # If assignment has duplicates, add note
    if assignment.get("duplicate_group_id"):
        # Fetch other agencies in group
        duplicates = get_duplicate_agencies(assignment["duplicate_group_id"])
        if duplicates:
            other_agencies = [d["agency_name"] for d in duplicates if d["id"] != assignment["id"]]
            if other_agencies:
                message += f"\n\n📌 Also available from: {', '.join(other_agencies)}"
                message += f"\n🔗 View all versions: {website_url}/assignments/{assignment['id']}/duplicates"
    
    return message
```

**Environment Variable**:
```bash
# In .env
DM_SKIP_DUPLICATES=true  # Enable duplicate filtering
DM_SHOW_DUPLICATE_NOTE=true  # Show "also available from" note
```

#### 4.2 Broadcast Filtering
**File**: `TutorDexAggregator/broadcast_assignments.py`

Add configurable broadcast modes:
```python
def get_broadcast_mode() -> str:
    """
    Get broadcast duplicate handling mode
    
    Modes:
    - 'all': Broadcast all assignments including duplicates
    - 'primary_only': Only broadcast primary from each group
    - 'primary_with_note': Broadcast primary with note about other agencies
    """
    return os.environ.get("BROADCAST_DUPLICATE_MODE", "primary_with_note")


def should_broadcast(assignment: Dict[str, Any]) -> bool:
    """Check if assignment should be broadcasted"""
    mode = get_broadcast_mode()
    
    if mode == "all":
        return True
    
    if mode in ("primary_only", "primary_with_note"):
        # Only broadcast primary assignments from duplicate groups
        return assignment.get("is_primary_in_group", True)
    
    return True


def format_broadcast_message(assignment: Dict[str, Any]) -> str:
    """Format broadcast message with duplicate info"""
    message = format_standard_broadcast(assignment)
    
    mode = get_broadcast_mode()
    if mode == "primary_with_note" and assignment.get("duplicate_group_id"):
        # Add note about other agencies
        duplicates = get_duplicate_agencies(assignment["duplicate_group_id"])
        if duplicates:
            other_agencies = [d["agency_name"] for d in duplicates if d["id"] != assignment["id"]]
            if other_agencies:
                message += f"\n\n🔄 Also posted by: {', '.join(other_agencies[:3])}"
                if len(other_agencies) > 3:
                    message += f" (+{len(other_agencies) - 3} more)"
    
    return message
```

**Environment Variable**:
```bash
# In .env
BROADCAST_DUPLICATE_MODE=primary_with_note  # Options: all, primary_only, primary_with_note
```

### Phase 5: Monitoring & Analytics (Week 5+)

#### 5.1 Prometheus Metrics
**File**: `TutorDexAggregator/observability_metrics.py`

Add duplicate detection metrics:
```python
from prometheus_client import Counter, Histogram, Gauge

# Detection metrics
duplicate_detected_total = Counter(
    'tutordex_duplicate_detected_total',
    'Total duplicates detected',
    ['confidence_level']  # high, medium, low
)

duplicate_group_size = Histogram(
    'tutordex_duplicate_group_size',
    'Size of duplicate groups',
    buckets=[2, 3, 4, 5, 10, 20]
)

duplicate_detection_seconds = Histogram(
    'tutordex_duplicate_detection_seconds',
    'Time taken for duplicate detection',
    buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0]
)

# DM/Broadcast metrics
dm_skipped_duplicate_total = Counter(
    'tutordex_dm_skipped_duplicate_total',
    'DMs skipped due to duplicate detection'
)

broadcast_skipped_duplicate_total = Counter(
    'tutordex_broadcast_skipped_duplicate_total',
    'Broadcast messages skipped due to duplicate detection'
)

# User interaction metrics
duplicate_modal_opened_total = Counter(
    'tutordex_duplicate_modal_opened_total',
    'Times duplicate modal was opened'
)

duplicate_filter_toggled_total = Counter(
    'tutordex_duplicate_filter_toggled_total',
    'Times duplicate filter was toggled',
    ['action']  # enabled, disabled
)
```

#### 5.2 Grafana Dashboard
**File**: `observability/grafana/dashboards/duplicate_detection.json`

Create dashboard with panels:
- Duplicate detection rate over time
- Duplicate group size distribution
- DM/broadcast reduction impact
- User preference distribution (show vs hide)
- Top agency pairs (who shares with whom)
- Detection performance (latency, errors)

**Sample Panel Config**:
```json
{
  "title": "Duplicate Detection Rate",
  "targets": [{
    "expr": "rate(tutordex_duplicate_detected_total[5m])",
    "legendFormat": "{{ confidence_level }}"
  }],
  "type": "graph"
}
```

#### 5.3 Alert Rules
**File**: `observability/prometheus/rules/duplicate_detection.yml`

```yaml
groups:
  - name: duplicate_detection
    interval: 1m
    rules:
      - alert: HighDuplicateRate
        expr: |
          sum(rate(tutordex_duplicate_detected_total[15m])) 
          / sum(rate(tutordex_assignment_persisted_total[15m])) > 0.5
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "High duplicate detection rate (>50%)"
          description: "{{ $value | humanizePercentage }} of assignments are duplicates"
      
      - alert: DuplicateDetectionSlow
        expr: |
          histogram_quantile(0.95, 
            rate(tutordex_duplicate_detection_seconds_bucket[5m])
          ) > 0.5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Duplicate detection is slow (p95 >500ms)"
          description: "p95 latency: {{ $value }}s"
      
      - alert: DuplicateDetectionFailing
        expr: |
          rate(tutordex_duplicate_detection_errors_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Duplicate detection failure rate >5%"
```

#### 5.4 Admin Tools
**File**: `TutorDexBackend/admin_routes.py`

Add admin endpoints for duplicate management:
```python
@app.post("/admin/duplicate-groups/{group_id}/merge")
def merge_duplicate_groups(request: Request, group_id: int, other_group_id: int):
    """Manually merge two duplicate groups"""
    _require_admin(request)
    # Implementation: merge groups and update assignments
    pass

@app.post("/admin/duplicate-groups/{group_id}/split")
def split_duplicate_group(request: Request, group_id: int, assignment_ids: List[int]):
    """Manually split assignments from a duplicate group"""
    _require_admin(request)
    # Implementation: create new group or mark as non-duplicate
    pass

@app.patch("/admin/duplicate-detection/config")
def update_detection_config(request: Request, config: Dict[str, Any]):
    """Update detection algorithm configuration"""
    _require_admin(request)
    # Update thresholds, weights, time window, etc.
    pass

@app.get("/admin/duplicate-detection/stats")
def get_detection_stats(request: Request):
    """Get duplicate detection statistics"""
    _require_admin(request)
    return {
        "total_groups": ...,
        "avg_group_size": ...,
        "detection_rate": ...,
        "top_agency_pairs": ...,
    }
```

## Summary of Remaining Work

### Estimated Effort
- **Phase 3 (Website)**: 2-3 days
- **Phase 4 (Telegram)**: 1-2 days
- **Phase 5 (Monitoring)**: 1-2 days
- **Total**: ~1 week of development

### Files to Create/Modify
- Website: 4-5 React components, 1 CSS file
- Telegram: 2 Python files (dm_assignments.py, broadcast_assignments.py)
- Monitoring: 1 metrics file, 1 dashboard JSON, 1 alert rules YAML
- Backend: 1 admin routes file

### Testing Required
- Manual UI testing (badges, modal, filters)
- DM/broadcast integration testing
- Performance testing (detection latency)
- End-to-end duplicate flow testing

## Deployment Checklist

### Prerequisites
- ✅ Database migration applied
- ✅ `DUPLICATE_DETECTION_ENABLED=true` set
- ✅ Services restarted

### Phase 3 Deployment
- [ ] Deploy website changes
- [ ] Test duplicate badges appear
- [ ] Test modal opens and shows correct data
- [ ] Test filter toggle works

### Phase 4 Deployment
- [ ] Set `DM_SKIP_DUPLICATES=true`
- [ ] Set `BROADCAST_DUPLICATE_MODE=primary_with_note`
- [ ] Monitor DM/broadcast volume reduction
- [ ] Verify tutors not receiving duplicate DMs

### Phase 5 Deployment
- [ ] Deploy Grafana dashboard
- [ ] Enable Prometheus alert rules
- [ ] Monitor dashboard for anomalies
- [ ] Set up alert notification channels

## Success Criteria

### Quantitative
- ✅ Detection accuracy >90%
- ✅ False positive rate <5%
- ✅ Detection latency p95 <100ms
- ⏳ DM reduction 20-40% (Phase 4)
- ⏳ User satisfaction 80%+ prefer hide duplicates (Phase 5)

### Qualitative
- ✅ Algorithm validated against production data
- ✅ Non-breaking implementation (backward compatible)
- ✅ Configurable parameters (database + environment)
- ⏳ Clean UI showing duplicate relationships (Phase 3)
- ⏳ Reduced tutor notification spam (Phase 4)
- ⏳ Observable system behavior (Phase 5)
