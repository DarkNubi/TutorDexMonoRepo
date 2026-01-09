# Duplicate Assignment Detection - Executive Summary

## Problem

Parents often apply to multiple tuition agencies simultaneously, or agencies share/repost each other's assignments. This creates:
- **Tutor confusion**: Same assignment appears multiple times
- **Duplicate DMs**: Tutors receive multiple notifications for the same opportunity
- **Inflated metrics**: Assignment counts don't reflect unique opportunities
- **Wasted effort**: Tutors may unknowingly apply multiple times

## Solution Overview

Implement automated duplicate detection that:
1. **Detects** similar assignments across agencies using multi-signal scoring
2. **Groups** duplicates together with primary/secondary designation
3. **Filters** duplicates from user-facing displays (optional, configurable)
4. **Prevents** duplicate DMs and broadcasts
5. **Shows** transparency via "Also posted by X agencies" badges

## Detection Algorithm

### Similarity Scoring (0-100 points)

| Signal | Weight | Description |
|--------|--------|-------------|
| **Postal Code** | 40 | Exact or fuzzy match (±1-2 digits) |
| **Assignment Code** | 40 | Exact match or prefix similarity |
| **Subjects** | 30 | Jaccard overlap of canonical subjects |
| **Levels** | 20 | Jaccard overlap of student levels |
| **Rate Range** | 10 | Overlapping min/max rates |
| **Time Availability** | 5 | Similar scheduling requirements |
| **Temporal Proximity** | 5 | Posted within 24-48 hours |

**Threshold**: Score ≥ 70 = Likely Duplicate
- High confidence: ≥ 85 (e.g., same postal + code + subjects)
- Medium confidence: 70-84 (e.g., same postal + subjects, no code)
- Review needed: 60-69 (potential false positive)

### Example Scenarios

**Scenario 1: High Confidence Duplicate**
```
Assignment A (Agency X):
  Postal: 123456, Code: D2388
  Subjects: [MATH.SEC_EMATH, PHYSICS]
  Levels: [Secondary, Sec 3]

Assignment B (Agency Y):
  Postal: 123456, Code: D2388
  Subjects: [MATH.SEC_EMATH, PHYSICS]
  Levels: [Secondary, Sec 3]

Score: 40 (postal) + 40 (code) + 30 (subjects) = 110 → 95/100 (cap)
Result: DUPLICATE ✅
```

**Scenario 2: Medium Confidence Duplicate**
```
Assignment A:
  Postal: 123456, Code: (none)
  Subjects: [MATH.SEC_EMATH]
  Levels: [Secondary, Sec 3]

Assignment B:
  Postal: 123457, Code: (none)
  Subjects: [MATH.SEC_EMATH]
  Levels: [Secondary]

Score: 35 (fuzzy postal) + 30 (subjects) + 10 (levels) + 5 (temporal) = 80
Result: DUPLICATE ✅
```

**Scenario 3: Not a Duplicate**
```
Assignment A:
  Postal: 123456, Subjects: [MATH]

Assignment B:
  Postal: 654321, Subjects: [ENGLISH]

Score: 0 (different districts)
Result: NOT DUPLICATE ❌
```

## Database Schema

### New Table: `assignment_duplicate_groups`
```sql
CREATE TABLE assignment_duplicate_groups (
    id BIGSERIAL PRIMARY KEY,
    primary_assignment_id BIGINT REFERENCES assignments(id),
    member_count INT NOT NULL DEFAULT 2,
    avg_confidence_score DECIMAL(5,2),
    status TEXT DEFAULT 'active',
    meta JSONB
);
```

### Modified Table: `assignments`
```sql
ALTER TABLE assignments 
    ADD COLUMN duplicate_group_id BIGINT,
    ADD COLUMN is_primary_in_group BOOLEAN DEFAULT TRUE,
    ADD COLUMN duplicate_confidence_score DECIMAL(5,2);
```

### Configuration Table: `duplicate_detection_config`
```sql
CREATE TABLE duplicate_detection_config (
    config_key TEXT PRIMARY KEY,
    config_value JSONB,
    updated_at TIMESTAMPTZ
);
```

## Integration Points

### 1. Aggregator (Detection)
**File**: `TutorDexAggregator/duplicate_detector.py` (new)
- Runs after assignment persistence in `supabase_persist.py`
- Non-blocking: detection failure doesn't break ingestion
- Configurable via `DUPLICATE_DETECTION_ENABLED` env var

### 2. Backend API (Exposure)
**New endpoints**:
- `GET /assignments?show_duplicates=false` - Filter duplicates in listing
- `GET /assignments/{id}/duplicates` - Get duplicate group details

**Updated endpoints**:
- `GET /assignments` - Include duplicate metadata in responses
- `POST /match/payload` - Skip duplicate DMs

### 3. Website (Display)
**Changes**:
- Duplicate badge on assignment cards: "Also posted by X agencies"
- Modal to view all versions when clicking badge
- User preference toggle: "Hide duplicates" (default on after beta)
- Filter: "Show duplicates" checkbox

### 4. Telegram DMs
**Logic**:
- Only send primary assignment per duplicate group
- Include note: "Also available from [Agency A, Agency B]"
- Skip duplicate if primary already sent to tutor

### 5. Telegram Broadcast
**Modes** (configurable via `BROADCAST_DUPLICATE_MODE`):
- `all`: Broadcast everything (current behavior)
- `primary_only`: Only broadcast primary from each group
- `primary_with_note`: Broadcast primary with agency list (recommended)

## Rollout Phases

### Phase 1: Backend Detection (Week 1)
- ✅ Add database schema
- ✅ Implement detection algorithm
- ✅ Integrate into persistence pipeline
- ✅ Add metrics and monitoring
- 🎯 **Goal**: Detection runs, no user impact yet

### Phase 2: API Layer (Week 2)
- ✅ Expose duplicate data in APIs
- ✅ Add Supabase RPCs
- 🎯 **Goal**: APIs support duplicate queries

### Phase 3: Website Display (Week 3)
- ✅ Add duplicate badges and modal
- ✅ Add user preference toggle
- ✅ Default: show all (preserve current UX)
- 🎯 **Goal**: Users see duplicate indicators

### Phase 4: Telegram Distribution (Week 4)
- ✅ Update DM logic
- ✅ Update broadcast logic
- 🎯 **Goal**: Reduce duplicate notifications by 20-40%

### Phase 5: Default Hide Duplicates (Week 5+)
- ✅ Change default to hide duplicates
- ✅ Monitor user engagement
- 🎯 **Goal**: Cleaner default UX

## Metrics & Monitoring

### Prometheus Metrics
```python
duplicate_detected_total           # Count of duplicates found
duplicate_group_size               # Histogram of group sizes
duplicate_detection_latency        # Detection performance
dm_skipped_duplicate_total         # DMs prevented
broadcast_skipped_duplicate_total  # Broadcasts prevented
```

### Grafana Dashboard
- Duplicate detection rate (% of assignments with duplicates)
- Top agency pairs (who duplicates with whom)
- DM reduction impact (notifications saved)
- User preferences (% hiding vs showing duplicates)
- Detection performance (p95 latency < 100ms target)

### Alerts
- `HighDuplicateRate`: >50% duplicates for 15+ minutes
- `DuplicateDetectionSlow`: p95 latency >500ms
- `DuplicateDetectionFailing`: Error rate >5%

## Configuration

### Environment Variables
```bash
# Detection
DUPLICATE_DETECTION_ENABLED=true
DUPLICATE_DETECTION_THRESHOLD=70
DUPLICATE_TIME_WINDOW_DAYS=7

# DM/Broadcast Behavior
BROADCAST_DUPLICATE_MODE=primary_with_note
DM_SKIP_DUPLICATES=true
```

### Tunable Parameters (in database)
```json
{
  "thresholds": {
    "high_confidence": 85,
    "medium_confidence": 70,
    "low_confidence": 60
  },
  "weights": {
    "postal": 40,
    "assignment_code": 40,
    "subjects": 30,
    "levels": 20,
    "rate": 10,
    "time": 5,
    "temporal": 5
  },
  "agency_partnerships": [
    {"agencies": ["Agency A", "Agency B"], "auto_group": true}
  ]
}
```

## User Experience

### Before Duplicate Detection
```
Assignment Feed:
1. Sec 3 Math @ 123456 - Agency A
2. Sec 3 Math @ 123456 - Agency B  [DUPLICATE]
3. Sec 3 Math @ 123456 - Agency C  [DUPLICATE]
4. Pri 5 Science @ 234567 - Agency A
5. Sec 3 Math @ 123456 - Agency D  [DUPLICATE]

Tutor receives 4 DMs for the same assignment 😞
```

### After Duplicate Detection
```
Assignment Feed:
1. Sec 3 Math @ 123456 - Agency A
   🔗 Also posted by 3 other agencies [click to view]
2. Pri 5 Science @ 234567 - Agency A

Tutor receives 1 DM for the unique assignment ✅
```

### Duplicate Group View
```
Same Assignment Posted by 4 Agencies

✓ Agency A (Recommended)
  Code: D2388
  Posted: 2 hours ago
  [Apply via Agency A]

  Agency B
  Code: TUT-2388
  Posted: 3 hours ago
  [Apply via Agency B]

  Agency C
  Code: (none)
  Posted: 4 hours ago
  [Apply via Agency C]

  Agency D
  Code: ASG2388
  Posted: 5 hours ago
  [Apply via Agency D]

💡 Tip: These agencies may be sharing the same parent request.
    You only need to apply once through your preferred agency.
```

## Edge Cases Handled

1. **3+ Duplicate Groups**: Supports N-way grouping, not just pairs
2. **Assignment Edits**: Re-runs detection, updates groups
3. **One Agency Closes**: Promotes next best to primary
4. **All Agencies Close**: Marks group as resolved
5. **Assignment Code Collisions**: Requires postal or subject match too
6. **Fuzzy Postal Matches**: Accounts for OCR/parsing errors (±1-2 digits)
7. **Legitimate Similar Assignments**: Lower threshold prevents false positives
8. **False Positives**: Admin review interface + user reporting

## Success Criteria

### Quantitative
- ✅ Duplicate detection accuracy >90%
- ✅ False positive rate <5%
- ✅ Detection latency p95 <100ms
- ✅ DM volume reduction: 20-40%
- ✅ User engagement: 80%+ prefer hide duplicates

### Qualitative
- ✅ Tutors find feed cleaner and less confusing
- ✅ Tutors understand agency relationships
- ✅ No complaints about missed opportunities
- ✅ Operators can investigate agency partnerships

## Admin Tools

### Manual Review Interface
- List low-confidence groups for review
- Side-by-side comparison of assignments
- Actions: confirm, split, merge, change primary

### Configuration Management
- Adjust detection thresholds
- Define agency partnerships (known duplicators)
- Exclude specific agencies from detection

### Analytics Dashboard
- Duplicate trends over time
- Agency partnership patterns
- Detection accuracy (requires manual labels)

## Testing Strategy

### Unit Tests
- Exact postal match → duplicate
- Fuzzy postal match → duplicate
- Different districts → not duplicate
- Assignment code match → duplicate
- No common subjects → not duplicate

### Integration Tests
- Persist two similar assignments → group created
- DM to tutor → only primary sent
- Broadcast → respects mode setting
- Edit assignment → group updated

### Manual Testing
- Create known duplicates
- Verify badges appear
- Test duplicate modal
- Toggle preference
- Check DM behavior
- Review metrics in Grafana

## Documentation

- **Full Spec**: `docs/DUPLICATE_DETECTION.md` (this file)
- **API Docs**: Update OpenAPI/Swagger with new endpoints
- **User Guide**: FAQ section on website
- **Runbook**: `observability/runbooks/duplicate_detection.md`

## Next Steps

1. ✅ Review and approve plan
2. 📋 Create implementation tickets for each phase
3. 🔨 Phase 1: Build detection backend (Week 1)
4. 🧪 Test detection accuracy with sample data
5. 📊 Set up Grafana dashboard and alerts
6. 🚀 Roll out phases 2-5 with monitoring

## Questions & Feedback

For questions or suggestions about duplicate detection:
- File an issue in the repository
- Contact the maintainer
- Review `docs/DUPLICATE_DETECTION.md` for full details

---

**Last Updated**: 2026-01-08  
**Status**: Planned - Implementation Pending  
**Owner**: TutorDex Engineering
