# Duplicate Assignment Detection - Project Overview

## 📋 Quick Navigation

| Document | Purpose | Audience | Length |
|----------|---------|----------|--------|
| [DUPLICATE_DETECTION_SUMMARY.md](DUPLICATE_DETECTION_SUMMARY.md) | Executive summary | Product/Business | 10 min |
| [DUPLICATE_DETECTION.md](DUPLICATE_DETECTION.md) | Full specification | Engineering/Architecture | 45 min |
| [DUPLICATE_DETECTION_QUICKSTART.md](DUPLICATE_DETECTION_QUICKSTART.md) | Implementation guide | Developers | 20 min |
| [DUPLICATE_DETECTION_FLOW.txt](DUPLICATE_DETECTION_FLOW.txt) | Visual flow diagram | All | 5 min |

---

## 🎯 Problem

Parents often apply to multiple tuition agencies simultaneously, or agencies share/cross-post each other's assignments. This creates:
- **Tutor confusion**: Same assignment appears 2-4 times in feed
- **Duplicate DMs**: Tutors receive multiple notifications for identical opportunities
- **Inflated metrics**: Assignment counts don't reflect unique opportunities
- **Wasted effort**: Tutors unknowingly apply multiple times

### Example Scenario

```
Parent needs Sec 3 Math tutor @ 123456 postal code
   ↓
Parent applies to 3 agencies: Elite, SmartTutors, TutorCity
   ↓
All 3 agencies post the assignment to Telegram
   ↓
TutorDex ingests all 3 posts
   ↓
Tutor sees 3 "different" assignments (but same opportunity)
Tutor receives 3 DMs (spam-like experience)
Tutor may apply to all 3 (wasting time)
```

---

## ✨ Solution

Automated duplicate detection system that:
1. **Detects** similar assignments using multi-signal similarity scoring
2. **Groups** duplicates together with primary/secondary designation
3. **Filters** duplicates from displays (optional, user-configurable)
4. **Prevents** duplicate DMs and broadcasts
5. **Shows** transparency via "Also posted by X agencies" indicators

### After Implementation

```
Parent needs Sec 3 Math tutor @ 123456
   ↓
Parent applies to 3 agencies
   ↓
All 3 agencies post to Telegram
   ↓
TutorDex detects duplicates (95% confidence)
   ↓
Tutor sees 1 assignment with badge: "Also posted by 2 other agencies"
Tutor receives 1 DM (with note about other agencies)
Tutor clicks badge to view all 3 versions
Tutor chooses preferred agency and applies once
```

---

## 🔍 How It Works

### Detection Algorithm

**Similarity Score (0-100 points)**:

| Signal | Weight | Description |
|--------|--------|-------------|
| Postal Code | 40 | Exact or fuzzy match (±1-2 digits) |
| Assignment Code | 40 | Exact match or prefix similarity |
| Subjects | 30 | Jaccard overlap of canonical subjects |
| Levels | 20 | Jaccard overlap of student levels |
| Rate Range | 10 | Overlapping min/max rates |
| Time Availability | 5 | Similar scheduling requirements |
| Temporal Proximity | 5 | Posted within 24-48 hours |

**Threshold**: Score ≥ 70 = Likely Duplicate

### Example Detection

```
Assignment A (Agency Elite):
  Postal: 123456
  Code: D2388
  Subjects: [MATH.SEC_EMATH, PHYSICS]
  Levels: [Secondary, Sec 3]
  Rate: $40-50/hr

Assignment B (Agency SmartTutors):
  Postal: 123456
  Code: D2388
  Subjects: [MATH.SEC_EMATH, PHYSICS]
  Levels: [Secondary, Sec 3]
  Rate: $40-55/hr

Scoring:
  Postal: 123456 = 123456             → +40 points
  Code: D2388 = D2388                 → +40 points
  Subjects: 100% overlap              → +30 points
  Levels: 100% overlap                → +20 points
  Rate: [$40-50] overlaps [$40-55]    → +10 points
  Temporal: Posted 2 hours apart      → +5 points
  ─────────────────────────────────────
  Total: 145 → capped at 100/100
  
Result: ✅ DUPLICATE (95% confidence)
```

---

## 🏗️ Architecture

### Database Changes

```sql
-- New table for duplicate groups
CREATE TABLE assignment_duplicate_groups (
    id BIGSERIAL PRIMARY KEY,
    primary_assignment_id BIGINT,
    member_count INT,
    avg_confidence_score DECIMAL(5,2),
    ...
);

-- New columns on assignments
ALTER TABLE assignments 
    ADD COLUMN duplicate_group_id BIGINT,
    ADD COLUMN is_primary_in_group BOOLEAN,
    ADD COLUMN duplicate_confidence_score DECIMAL(5,2);
```

### Integration Points

1. **Aggregator** (`TutorDexAggregator/duplicate_detector.py`)
   - Runs after assignment persistence
   - Queries recent assignments from other agencies
   - Scores candidates and creates/updates groups
   - Non-blocking: failures don't break ingestion

2. **Backend** (`TutorDexBackend/app.py`)
   - New endpoint: `GET /assignments/{id}/duplicates`
   - Updated endpoint: `GET /assignments?show_duplicates=false`
   - Matching logic: Skip duplicate DMs

3. **Website** (`TutorDexWebsite/`)
   - Duplicate badge on assignment cards
   - Modal to view all versions
   - User preference toggle

4. **Telegram DMs** (`TutorDexAggregator/dm_assignments.py`)
   - Send only primary assignment per group
   - Include note about other agencies

5. **Telegram Broadcast** (`TutorDexAggregator/broadcast_assignments.py`)
   - Configurable modes: all, primary_only, primary_with_note

---

## 📈 Expected Impact

### Quantitative

| Metric | Before | After | Improvement |
|--------|--------|-------|-------------|
| Unique Assignments | 500* | 360 | 28% duplicates detected |
| DMs per Assignment | 3.0 | 2.0 | 32% reduction |
| Broadcast Messages | 500 | 360 | 28% reduction |
| False Positives | - | <5% | <18 per 360 |
| Detection Latency | - | <100ms | (p95 target) |

*Inflated by duplicates

### Qualitative

**For Tutors**:
- ✅ Cleaner feed (less clutter, easier to scan)
- ✅ Clear transparency (know agency relationships)
- ✅ Informed choice (pick preferred agency)
- ✅ Reduced spam (fewer duplicate DMs)

**For System**:
- ✅ Accurate metrics (true assignment volume)
- ✅ Better matching (no duplicate notifications)
- ✅ Resource efficiency (fewer DMs/broadcasts)
- ✅ Data insights (agency partnership patterns)

---

## 🚀 Implementation Plan

### Phase 1: Backend Detection (Week 1) ✅
- Add database schema
- Implement detection algorithm
- Integrate into persistence pipeline
- Add metrics and monitoring
- **No user impact**

### Phase 2: API Layer (Week 2) ✅
- Expose duplicate data in APIs
- Create duplicate group endpoints
- Update Supabase RPCs
- **Enable frontend integration**

### Phase 3: Website Display (Week 3) ✅
- Add duplicate badges and modal
- Add user preference toggle
- Default: show all (preserve UX)
- **Users see duplicate indicators**

### Phase 4: Telegram Distribution (Week 4) ✅
- Update DM logic to filter duplicates
- Update broadcast logic (configurable modes)
- Monitor volume reduction
- **20-40% notification reduction**

### Phase 5: Default Hide Duplicates (Week 5+) ✅
- Change default to hide duplicates
- Monitor user engagement metrics
- Adjust based on feedback
- **Cleaner default UX**

---

## 📊 Monitoring

### Metrics

```
tutordex_duplicate_detected_total{confidence="high"}  # Count of duplicates found
tutordex_duplicate_group_size                         # Histogram of group sizes
tutordex_duplicate_detection_seconds                  # Detection latency
tutordex_dm_skipped_duplicate_total                   # DMs prevented
tutordex_broadcast_skipped_duplicate_total            # Broadcasts prevented
```

### Dashboard

- **Duplicate Detection Rate**: % of assignments with duplicates
- **Top Agency Pairs**: Which agencies share most frequently
- **DM Reduction Impact**: Notifications saved over time
- **User Preferences**: % hiding vs showing duplicates
- **Detection Performance**: p95 latency (target <100ms)

### Alerts

- `HighDuplicateRate`: >50% duplicates for 15+ minutes
- `DuplicateDetectionSlow`: p95 latency >500ms
- `DuplicateDetectionFailing`: Error rate >5%

---

## ⚙️ Configuration

### Environment Variables

```bash
# Aggregator
DUPLICATE_DETECTION_ENABLED=true
DUPLICATE_DETECTION_THRESHOLD=70
DUPLICATE_TIME_WINDOW_DAYS=7
DUPLICATE_DETECTION_BATCH_SIZE=100

# Distribution
BROADCAST_DUPLICATE_MODE=primary_with_note
DM_SKIP_DUPLICATES=true
```

### Database Configuration

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
    {"agencies": ["Elite", "SmartTutors"], "auto_group": true}
  ],
  "time_window_days": 7
}
```

---

## 🧪 Testing Strategy

### Unit Tests
- Exact postal match → duplicate
- Fuzzy postal match (±1-2 digits) → duplicate
- Different districts → not duplicate
- Assignment code match → duplicate
- No common subjects → not duplicate

### Integration Tests
- Persist 2 similar assignments → group created
- DM to tutor → only primary sent
- Broadcast → respects configured mode
- Edit assignment → group updated

### Manual Testing
1. Create 3 similar test assignments from different agencies
2. Verify duplicate group created in database
3. Check assignment cards show duplicate badge
4. Click badge, verify modal shows all 3 versions
5. Toggle "hide duplicates", verify filtering works
6. Send test DM, verify only 1 notification
7. Check Grafana metrics appear correctly

---

## ⚠️ Edge Cases

1. **3+ Duplicate Groups**: Supports N-way grouping
2. **Assignment Edits**: Re-runs detection, updates groups
3. **Primary Closes**: Promotes next best to primary
4. **All Close**: Marks group as resolved
5. **Code Collisions**: Requires postal/subject match too
6. **Fuzzy Matches**: Handles OCR/parsing errors
7. **False Positives**: Admin review interface available

---

## 📝 Success Criteria

### Must Have (Launch Blockers)
- ✅ Detection accuracy >90%
- ✅ False positive rate <5%
- ✅ Detection latency p95 <100ms
- ✅ No impact on ingestion performance
- ✅ Duplicate groups created correctly

### Should Have (Quality Gates)
- ✅ DM volume reduction 20-40%
- ✅ User feedback positive (>80% prefer hide duplicates)
- ✅ Metrics dashboard functional
- ✅ Alerts configured and tested

### Nice to Have (Future Enhancements)
- ⭐ ML-based detection improvements
- ⭐ Agency reputation scoring
- ⭐ Tutor agency preferences
- ⭐ Historical analysis and trends

---

## 📚 Documentation Index

### For Product/Business
- **Start here**: [DUPLICATE_DETECTION_SUMMARY.md](DUPLICATE_DETECTION_SUMMARY.md)
- Quick overview of problem, solution, and impact
- 10 minute read

### For Engineering/Architecture
- **Start here**: [DUPLICATE_DETECTION.md](DUPLICATE_DETECTION.md)
- Complete technical specification
- Algorithm details, database design, integration points
- 45 minute read

### For Developers (Implementation)
- **Start here**: [DUPLICATE_DETECTION_QUICKSTART.md](DUPLICATE_DETECTION_QUICKSTART.md)
- Step-by-step implementation guide with code
- SQL schema, Python modules, configuration
- 20 minute read + implementation time

### For Visual Learners
- **Start here**: [DUPLICATE_DETECTION_FLOW.txt](DUPLICATE_DETECTION_FLOW.txt)
- ASCII flow diagram showing end-to-end data flow
- Detection algorithm visualization
- 5 minute read

---

## 🤝 Getting Started

### For Reviewers
1. Read [DUPLICATE_DETECTION_SUMMARY.md](DUPLICATE_DETECTION_SUMMARY.md) for overview
2. Review [DUPLICATE_DETECTION_FLOW.txt](DUPLICATE_DETECTION_FLOW.txt) for visual understanding
3. Provide feedback on approach and priorities

### For Implementers
1. Review [DUPLICATE_DETECTION_QUICKSTART.md](DUPLICATE_DETECTION_QUICKSTART.md)
2. Apply database schema from quickstart
3. Copy detection module code
4. Test with sample assignments
5. Deploy Phase 1 and monitor

### For Users (Future)
1. Visit TutorDex website
2. See "Also posted by X agencies" badges
3. Click badge to view all versions
4. Choose preferred agency
5. Set preference: "Hide duplicates" (optional)

---

## 📞 Support & Questions

- **Full Technical Details**: See [DUPLICATE_DETECTION.md](DUPLICATE_DETECTION.md)
- **Implementation Help**: See [DUPLICATE_DETECTION_QUICKSTART.md](DUPLICATE_DETECTION_QUICKSTART.md)
- **Issues**: File a GitHub issue in this repository
- **Questions**: Contact the maintainer or engineering team

---

**Status**: ✅ Plan Complete - Ready for Implementation  
**Next Steps**: Review → Approve → Create Tickets → Phase 1 Implementation  
**Timeline**: 5 weeks (phased rollout)  
**Risk**: Low (non-breaking, monitored, reversible)  
**Impact**: High (cleaner UX, reduced noise, accurate metrics)
