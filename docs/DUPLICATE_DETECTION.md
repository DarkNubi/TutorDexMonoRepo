# Duplicate Assignment Detection and Handling

## Overview

TutorDex aggregates assignments from multiple agency Telegram channels. Sometimes the same assignment appears across multiple agencies because:
1. **Parent applied to multiple agencies** - Parents often apply to 2-3 agencies simultaneously to maximize chances
2. **Agency partnerships** - Some agencies have formal partnerships and cross-post each other's assignments
3. **Assignment sharing** - Agencies may repost popular/difficult-to-fill assignments from other channels
4. **Assignment code reuse** - Different agencies may assign the same code by coincidence

This document describes how TutorDex detects, manages, and displays duplicate assignments to provide a better experience for tutors.

---

## Problem Statement

### Current Issues
- **Tutor confusion**: Tutors see the same assignment multiple times, don't know if it's the same opportunity
- **Wasted effort**: Tutors may apply to the same assignment through multiple agencies
- **DM spam**: Tutors receive multiple DMs for the same assignment if they match
- **Inaccurate counts**: Assignment counts appear inflated due to duplicates
- **Unclear agency relationships**: Tutors don't know which agencies share assignments

### User Goals
- **Tutors**: Want to know if they've seen an assignment before, which agency to apply through, and avoid duplicate applications
- **System**: Want to reduce noise, improve matching accuracy, and provide transparency
- **Analytics**: Want accurate metrics on unique assignment volume

---

## Detection Strategy

### Multi-Signal Similarity Scoring

Duplicate detection uses a weighted scoring system across multiple signals:

#### High-Weight Signals (40 points each)
- **Postal code match**: Exact or fuzzy match (±1-2 digits)
  - Singapore postal codes are 6 digits, first 2 digits = district
  - Fuzzy match accounts for OCR/parsing errors
- **Assignment code match**: Exact match on `assignment_code` field
  - Many agencies use unique codes (e.g., "D2388", "TUT-123")
  - Some agencies share codes when partnered

#### Medium-Weight Signals (20-30 points each)
- **Subject overlap** (30 points): Jaccard similarity of subject arrays
  - Score = |A ∩ B| / |A ∪ B|
  - Uses canonical subject codes from taxonomy v2
  - Example: ["MATH.SEC_EMATH", "PHYSICS"] vs ["MATH.SEC_EMATH"] = 0.67
- **Level overlap** (20 points): Jaccard similarity of level arrays
  - Includes both `signals_levels` and `signals_specific_student_levels`
  - Example: ["Secondary", "Sec 3"] vs ["Secondary"] = 0.50

#### Low-Weight Signals (5-10 points each)
- **Rate overlap** (10 points): Overlapping rate ranges
  - Check if `[rate_min, rate_max]` intervals overlap
  - Handles missing rates gracefully (no penalty)
- **Time availability overlap** (5 points): Similar scheduling requirements
  - Compare `time_availability_explicit` or `time_availability_estimated`
  - Weekday/weekend overlap, preferred hours
- **Temporal proximity** (5 points): Posted within 24-48 hours
  - Uses `published_at` timestamps
  - Accounts for assignment reposting patterns

### Duplicate Threshold

**Score ≥ 70 = Likely Duplicate**
- High confidence: score ≥ 85 (e.g., same postal + assignment code + subjects)
- Medium confidence: 70 ≤ score < 85 (e.g., same postal + subjects, no code)
- Low confidence: 60 ≤ score < 70 (potential duplicate, needs review)

Scores below 70 are considered distinct assignments.

### Algorithm Pseudocode

```python
def detect_duplicates(new_assignment, existing_assignments):
    """
    Find potential duplicates for a newly persisted assignment.
    
    Args:
        new_assignment: The assignment just added to the database
        existing_assignments: Recent open assignments from other agencies
            (exclude same agency, filter by time window)
    
    Returns:
        List of (assignment_id, confidence_score) tuples for duplicates
    """
    candidates = []
    
    # Pre-filter: only check assignments from last 7 days
    recent_assignments = [a for a in existing_assignments 
                          if (now - a.published_at).days <= 7
                          and a.agency_id != new_assignment.agency_id]
    
    for candidate in recent_assignments:
        score = calculate_similarity_score(new_assignment, candidate)
        if score >= 60:  # Include medium-confidence for review
            candidates.append((candidate.id, score))
    
    # Sort by score descending
    candidates.sort(key=lambda x: x[1], reverse=True)
    return candidates


def calculate_similarity_score(a, b):
    """Calculate duplicate confidence score (0-100)."""
    score = 0
    
    # Postal code (40 points)
    if postal_codes_match(a.postal_code, b.postal_code):
        score += 40
    elif postal_codes_fuzzy_match(a.postal_code, b.postal_code):
        score += 35  # Slightly lower for fuzzy match
    
    # Assignment code (40 points)
    if a.assignment_code and b.assignment_code:
        if a.assignment_code == b.assignment_code:
            score += 40
        elif assignment_codes_similar(a.assignment_code, b.assignment_code):
            score += 30  # Prefix match, e.g., "D2388" vs "D2388A"
    
    # Subject overlap (30 points)
    subjects_a = set(a.subjects_canonical or a.signals_subjects)
    subjects_b = set(b.subjects_canonical or b.signals_subjects)
    if subjects_a and subjects_b:
        jaccard = len(subjects_a & subjects_b) / len(subjects_a | subjects_b)
        score += jaccard * 30
    
    # Level overlap (20 points)
    levels_a = set(a.signals_levels + (a.signals_specific_student_levels or []))
    levels_b = set(b.signals_levels + (b.signals_specific_student_levels or []))
    if levels_a and levels_b:
        jaccard = len(levels_a & levels_b) / len(levels_a | levels_b)
        score += jaccard * 20
    
    # Rate overlap (10 points)
    if rate_ranges_overlap(a.rate_min, a.rate_max, b.rate_min, b.rate_max):
        score += 10
    
    # Time availability (5 points)
    if time_availability_similar(a.time_availability_explicit, 
                                  b.time_availability_explicit):
        score += 5
    
    # Temporal proximity (5 points)
    hours_apart = abs((a.published_at - b.published_at).total_seconds()) / 3600
    if hours_apart <= 48:
        score += 5
    elif hours_apart <= 96:
        score += 3
    
    return min(score, 100)  # Cap at 100


def postal_codes_fuzzy_match(postal_a, postal_b):
    """
    Check if postal codes are similar (within 1-2 digit error).
    Singapore postal codes: XXXXXX (6 digits), first 2 = district.
    """
    if not postal_a or not postal_b:
        return False
    
    # Extract 6-digit codes
    digits_a = re.sub(r'\D', '', str(postal_a))[-6:]
    digits_b = re.sub(r'\D', '', str(postal_b))[-6:]
    
    if len(digits_a) != 6 or len(digits_b) != 6:
        return False
    
    # Same district (first 2 digits)
    if digits_a[:2] != digits_b[:2]:
        return False
    
    # Count digit differences
    diffs = sum(1 for i in range(6) if digits_a[i] != digits_b[i])
    return diffs <= 2


def assignment_codes_similar(code_a, code_b):
    """Check if assignment codes are similar (prefix match)."""
    # Remove common prefixes/suffixes, compare core
    code_a_clean = re.sub(r'^(D|TUT|ASG|ASSIGN)[-_]?', '', code_a.upper())
    code_b_clean = re.sub(r'^(D|TUT|ASG|ASSIGN)[-_]?', '', code_b.upper())
    
    # Check if one is prefix of the other
    if code_a_clean.startswith(code_b_clean) or code_b_clean.startswith(code_a_clean):
        return True
    
    # Check Levenshtein distance (allow 1-2 char difference)
    distance = levenshtein_distance(code_a_clean, code_b_clean)
    return distance <= 2


def rate_ranges_overlap(min_a, max_a, min_b, max_b):
    """Check if rate ranges overlap."""
    if None in (min_a, max_a, min_b, max_b):
        return False  # Can't determine overlap with missing data
    
    # Ranges overlap if max_a >= min_b and max_b >= min_a
    return max_a >= min_b and max_b >= min_a
```

---

## Data Model

### Database Schema

#### New Table: `assignment_duplicate_groups`
```sql
CREATE TABLE public.assignment_duplicate_groups (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    
    -- Primary assignment (best quality, earliest, or preferred agency)
    primary_assignment_id BIGINT REFERENCES public.assignments(id),
    
    -- Group metadata
    member_count INT NOT NULL DEFAULT 2,
    avg_confidence_score DECIMAL(5,2),
    detection_algorithm_version TEXT NOT NULL DEFAULT 'v1',
    
    -- Status tracking
    status TEXT NOT NULL DEFAULT 'active',  -- active, resolved, invalid
    
    -- Optional manual review fields
    reviewed_at TIMESTAMPTZ,
    reviewed_by TEXT,
    review_notes TEXT,
    
    -- Store detection metadata
    meta JSONB  -- {agencies: [], first_detected: timestamp, last_updated: timestamp}
);

CREATE INDEX duplicate_groups_primary_idx 
    ON public.assignment_duplicate_groups(primary_assignment_id);
CREATE INDEX duplicate_groups_status_idx 
    ON public.assignment_duplicate_groups(status) WHERE status = 'active';
```

#### Modified Table: `assignments`
```sql
-- Add duplicate tracking columns
ALTER TABLE public.assignments 
    ADD COLUMN IF NOT EXISTS duplicate_group_id BIGINT 
        REFERENCES public.assignment_duplicate_groups(id) ON DELETE SET NULL;

ALTER TABLE public.assignments 
    ADD COLUMN IF NOT EXISTS is_primary_in_group BOOLEAN 
        NOT NULL DEFAULT TRUE;

ALTER TABLE public.assignments 
    ADD COLUMN IF NOT EXISTS duplicate_confidence_score DECIMAL(5,2);

-- Indexes for efficient duplicate queries
CREATE INDEX IF NOT EXISTS assignments_duplicate_group_idx 
    ON public.assignments(duplicate_group_id) 
    WHERE duplicate_group_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS assignments_is_primary_idx 
    ON public.assignments(is_primary_in_group, status) 
    WHERE is_primary_in_group = TRUE AND status = 'open';
```

#### New Table: `duplicate_detection_config`
```sql
CREATE TABLE public.duplicate_detection_config (
    id BIGSERIAL PRIMARY KEY,
    config_key TEXT NOT NULL UNIQUE,
    config_value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT
);

-- Initial config values
INSERT INTO public.duplicate_detection_config (config_key, config_value) VALUES
('thresholds', '{"high_confidence": 85, "medium_confidence": 70, "low_confidence": 60}'),
('weights', '{"postal": 40, "assignment_code": 40, "subjects": 30, "levels": 20, "rate": 10, "time": 5, "temporal": 5}'),
('agency_partnerships', '[]'),  -- List of known agency pairs that share assignments
('agency_exclusions', '[]'),  -- Agencies to exclude from duplicate detection
('time_window_days', '7'),  -- Only check duplicates within this window
('enabled', 'true');
```

### Duplicate Group Lifecycle

1. **Detection**: New assignment triggers duplicate scan
2. **Group Creation**: If duplicates found (score ≥ 70), create or update group
3. **Primary Selection**: Choose primary based on:
   - Parse quality score (higher is better)
   - Published timestamp (earlier is better)
   - Agency reputation (configurable preference list)
   - Assignment code presence (prefer assignments with codes)
4. **Group Updates**: When members are edited/closed
   - If primary closed → promote next best member
   - If all members closed → mark group as resolved
5. **Manual Review**: Admin can merge/split groups, override primary

---

## Internal Handling

### Aggregator Integration

#### 1. Detection Module: `TutorDexAggregator/duplicate_detector.py`

```python
# Core detection logic (new file)
class DuplicateDetector:
    def __init__(self, config_store):
        self.config = config_store.get_config()
        self.threshold = self.config['thresholds']['medium_confidence']
    
    def find_duplicates(self, assignment_row):
        """Find potential duplicates for a new assignment."""
        # Query recent assignments from different agencies
        candidates = self._get_candidate_assignments(assignment_row)
        
        # Score each candidate
        duplicates = []
        for candidate in candidates:
            score = self._calculate_score(assignment_row, candidate)
            if score >= self.threshold:
                duplicates.append({
                    'assignment_id': candidate['id'],
                    'score': score,
                    'agency_telegram_channel_name': candidate['agency_telegram_channel_name']
                })
        
        return duplicates
    
    def create_or_update_group(self, primary_id, duplicate_ids, scores):
        """Create a new duplicate group or add to existing."""
        # Check if any assignment already in a group
        existing_group = self._find_existing_group(primary_id, duplicate_ids)
        
        if existing_group:
            # Add new members to existing group
            self._add_to_group(existing_group['id'], duplicate_ids, scores)
        else:
            # Create new group
            group_id = self._create_group(primary_id, duplicate_ids, scores)
        
        return group_id
```

#### 2. Integration Point: `TutorDexAggregator/supabase_persist.py`

Add duplicate detection after successful assignment upsert:

```python
def upsert_assignment(row: Dict[str, Any]) -> Dict[str, Any]:
    # ... existing upsert logic ...
    
    # After successful upsert, check for duplicates
    if _duplicate_detection_enabled():
        try:
            from duplicate_detector import DuplicateDetector
            detector = DuplicateDetector(config_store)
            duplicates = detector.find_duplicates(row)
            
            if duplicates:
                # Update duplicate group
                detector.create_or_update_group(
                    primary_id=row['id'],
                    duplicate_ids=[d['assignment_id'] for d in duplicates],
                    scores=[d['score'] for d in duplicates]
                )
                
                log_event(logger, logging.INFO, "duplicates_detected",
                         assignment_id=row['id'],
                         duplicate_count=len(duplicates),
                         max_score=max(d['score'] for d in duplicates))
        except Exception as e:
            # Non-blocking: duplicate detection failure shouldn't break ingestion
            log_event(logger, logging.WARNING, "duplicate_detection_failed",
                     assignment_id=row['id'], error=str(e))
    
    return row
```

#### 3. Configuration: Environment Variables

Add to `TutorDexAggregator/.env.example`:

```bash
# Duplicate Detection
DUPLICATE_DETECTION_ENABLED=true
DUPLICATE_DETECTION_THRESHOLD=70  # Minimum score for duplicate
DUPLICATE_TIME_WINDOW_DAYS=7  # Only check assignments from last N days
DUPLICATE_DETECTION_BATCH_SIZE=100  # Max candidates to score per assignment
```

### Backend Integration

#### 1. API Extensions: `TutorDexBackend/app.py`

Add duplicate-aware parameters to existing endpoints:

```python
@app.get("/assignments")
async def list_assignments(
    # ... existing parameters ...
    show_duplicates: bool = False,  # NEW: include duplicates in results
    duplicate_group_id: Optional[int] = None,  # NEW: filter by group
):
    """
    List open assignments with optional duplicate filtering.
    
    - show_duplicates=false (default): only show primary assignments
    - show_duplicates=true: show all assignments including duplicates
    - duplicate_group_id=X: show only assignments in group X
    """
    # ... existing auth/validation ...
    
    # Build query
    query_params = {
        'status': status,
        'show_duplicates': show_duplicates,
        'duplicate_group_id': duplicate_group_id,
        # ... other filters ...
    }
    
    # Call updated Supabase RPC
    result = await supabase_store.list_open_assignments_v3(**query_params)
    return result
```

Add new endpoint for duplicate group details:

```python
@app.get("/assignments/{assignment_id}/duplicates")
async def get_assignment_duplicates(assignment_id: int):
    """
    Get all assignments in the same duplicate group.
    
    Returns:
    {
        "group_id": 123,
        "primary_assignment_id": 456,
        "members": [
            {
                "id": 456,
                "agency_display_name": "Agency A",
                "assignment_code": "D2388",
                "published_at": "2026-01-08T10:00:00Z",
                "confidence_score": 95,
                "is_primary": true
            },
            {
                "id": 789,
                "agency_display_name": "Agency B",
                "assignment_code": "TUT-2388",
                "published_at": "2026-01-08T11:30:00Z",
                "confidence_score": 92,
                "is_primary": false
            }
        ]
    }
    """
    result = await supabase_store.get_duplicate_group(assignment_id)
    return result
```

#### 2. Matching Algorithm Update: `TutorDexBackend/matching.py`

Ensure tutors only matched once per duplicate group:

```python
def match_from_payload(store: TutorStore, payload: Dict[str, Any]) -> List[str]:
    """Match tutors, filtering duplicate groups."""
    # ... existing matching logic ...
    
    # After generating candidate tutors, check if this assignment is in a group
    assignment_id = payload.get('assignment_id')
    if assignment_id:
        group_info = store.get_duplicate_group_for_assignment(assignment_id)
        if group_info and not group_info['is_primary']:
            # This is a duplicate, not primary
            # Check if we already matched tutors for the primary assignment
            primary_id = group_info['primary_assignment_id']
            if store.was_assignment_already_sent_to_tutors(primary_id):
                # Already sent primary, skip duplicates
                log_event(logger, logging.INFO, "skipping_duplicate_for_matching",
                         assignment_id=assignment_id,
                         primary_id=primary_id,
                         reason="primary_already_sent")
                return []
    
    return matched_tutor_ids
```

#### 3. Supabase RPCs: New/Updated Functions

Create `TutorDexAggregator/supabase sqls/2026-01-08_duplicate_detection.sql`:

```sql
-- Function: list_open_assignments_v3 (extends v2 with duplicate filtering)
CREATE OR REPLACE FUNCTION public.list_open_assignments_v3(
    p_status TEXT DEFAULT 'open',
    p_show_duplicates BOOLEAN DEFAULT FALSE,
    p_duplicate_group_id BIGINT DEFAULT NULL,
    -- ... other existing parameters ...
)
RETURNS TABLE (
    -- ... existing columns ...
    duplicate_group_id BIGINT,
    is_primary_in_group BOOLEAN,
    duplicate_confidence_score DECIMAL,
    duplicate_count INT
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        a.*,
        a.duplicate_group_id,
        a.is_primary_in_group,
        a.duplicate_confidence_score,
        (
            SELECT COUNT(*) 
            FROM public.assignments a2 
            WHERE a2.duplicate_group_id = a.duplicate_group_id 
                AND a2.duplicate_group_id IS NOT NULL
        ) AS duplicate_count
    FROM public.assignments a
    WHERE a.status = p_status
        -- Duplicate filtering
        AND (
            p_show_duplicates = TRUE  -- Show all
            OR a.is_primary_in_group = TRUE  -- Only primaries
            OR a.duplicate_group_id IS NULL  -- No group (unique)
        )
        -- Group filter
        AND (p_duplicate_group_id IS NULL OR a.duplicate_group_id = p_duplicate_group_id)
        -- ... other existing filters ...
    ORDER BY a.published_at DESC;
END;
$$ LANGUAGE plpgsql STABLE;


-- Function: get_duplicate_group_members
CREATE OR REPLACE FUNCTION public.get_duplicate_group_members(
    p_assignment_id BIGINT
)
RETURNS TABLE (
    group_id BIGINT,
    primary_assignment_id BIGINT,
    member_id BIGINT,
    agency_display_name TEXT,
    assignment_code TEXT,
    published_at TIMESTAMPTZ,
    confidence_score DECIMAL,
    is_primary BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT 
        g.id AS group_id,
        g.primary_assignment_id,
        a.id AS member_id,
        a.agency_display_name,
        a.assignment_code,
        a.published_at,
        a.duplicate_confidence_score AS confidence_score,
        a.is_primary_in_group AS is_primary
    FROM public.assignment_duplicate_groups g
    INNER JOIN public.assignments a ON a.duplicate_group_id = g.id
    WHERE g.id = (
        SELECT duplicate_group_id 
        FROM public.assignments 
        WHERE id = p_assignment_id
    )
    ORDER BY a.is_primary_in_group DESC, a.published_at ASC;
END;
$$ LANGUAGE plpgsql STABLE;
```

---

## User-Facing Display

### Website Changes

#### 1. Assignment Card UI: `TutorDexWebsite/src/page-assignments.js`

Add duplicate indicator badge:

```javascript
function renderAssignmentCard(assignment) {
    const card = document.createElement('div');
    card.className = 'assignment-card';
    
    // ... existing card content ...
    
    // NEW: Duplicate indicator
    if (assignment.duplicate_group_id && assignment.duplicate_count > 1) {
        const duplicateBadge = document.createElement('div');
        duplicateBadge.className = 'duplicate-badge';
        
        if (assignment.is_primary_in_group) {
            const otherCount = assignment.duplicate_count - 1;
            duplicateBadge.innerHTML = `
                <span class="badge badge-info">
                    <i class="icon-layers"></i>
                    Also posted by ${otherCount} other ${otherCount === 1 ? 'agency' : 'agencies'}
                </span>
            `;
        } else {
            duplicateBadge.innerHTML = `
                <span class="badge badge-secondary">
                    <i class="icon-copy"></i>
                    Duplicate assignment
                </span>
            `;
        }
        
        duplicateBadge.addEventListener('click', () => {
            showDuplicateGroupModal(assignment.id);
        });
        
        card.appendChild(duplicateBadge);
    }
    
    return card;
}
```

#### 2. Duplicate Group Modal: New UI Component

```javascript
async function showDuplicateGroupModal(assignmentId) {
    // Fetch duplicate group details
    const response = await fetch(
        `${BACKEND_URL}/assignments/${assignmentId}/duplicates`,
        {
            headers: {'Authorization': `Bearer ${await getIdToken()}`}
        }
    );
    const groupData = await response.json();
    
    // Render modal
    const modal = document.createElement('div');
    modal.className = 'modal duplicate-group-modal';
    modal.innerHTML = `
        <div class="modal-content">
            <h2>Same Assignment Posted by Multiple Agencies</h2>
            <p class="subtitle">
                This assignment appears across ${groupData.members.length} agencies. 
                They may be sharing the same parent/student request.
            </p>
            
            <div class="duplicate-list">
                ${groupData.members.map(member => `
                    <div class="duplicate-item ${member.is_primary ? 'primary' : ''}">
                        <div class="agency-info">
                            <strong>${member.agency_display_name}</strong>
                            ${member.is_primary ? '<span class="badge">Recommended</span>' : ''}
                        </div>
                        <div class="assignment-code">${member.assignment_code || 'N/A'}</div>
                        <div class="posted-time">Posted ${formatRelativeTime(member.published_at)}</div>
                        <div class="confidence">
                            Match confidence: ${Math.round(member.confidence_score)}%
                        </div>
                        <button class="btn-apply" onclick="applyToAssignment(${member.member_id})">
                            Apply via ${member.agency_display_name}
                        </button>
                    </div>
                `).join('')}
            </div>
            
            <div class="modal-footer">
                <p class="note">
                    <i class="icon-info"></i>
                    Tip: Some parents apply to multiple agencies simultaneously. 
                    You can apply via any agency, but avoid sending duplicate applications.
                </p>
                <button class="btn-close" onclick="this.closest('.modal').remove()">Close</button>
            </div>
        </div>
    `;
    
    document.body.appendChild(modal);
}
```

#### 3. User Preference: Show/Hide Duplicates

Add toggle in profile page:

```javascript
// In TutorDexWebsite/src/page-profile.js
function renderDuplicatePreference() {
    return `
        <div class="preference-section">
            <h3>Duplicate Assignments</h3>
            <label class="checkbox-label">
                <input type="checkbox" 
                       id="hide-duplicates" 
                       ${userPrefs.hide_duplicates ? 'checked' : ''}>
                <span>Hide duplicate assignments (show only primary version)</span>
            </label>
            <p class="help-text">
                When enabled, you'll only see one version of assignments posted by multiple agencies.
                You can still view all versions by clicking the duplicate badge.
            </p>
        </div>
    `;
}

// Update backend API call when saving
async function savePreferences() {
    const hideDuplicates = document.getElementById('hide-duplicates').checked;
    
    await fetch(`${BACKEND_URL}/me/tutor`, {
        method: 'PUT',
        headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${await getIdToken()}`
        },
        body: JSON.stringify({
            ...currentPreferences,
            hide_duplicates: hideDuplicates
        })
    });
}
```

#### 4. Filter UI Update

Add "Show duplicates" toggle to assignment list filters:

```javascript
// In filters section
<div class="filter-item">
    <label class="toggle-label">
        <input type="checkbox" id="show-duplicates" onchange="refreshAssignments()">
        <span>Show duplicate assignments</span>
    </label>
    <p class="help-text">
        Include assignments posted by multiple agencies
    </p>
</div>
```

### CSS Styling

```css
/* Duplicate badge styling */
.duplicate-badge {
    display: inline-block;
    margin-top: 8px;
    cursor: pointer;
}

.duplicate-badge .badge {
    display: inline-flex;
    align-items: center;
    gap: 4px;
    padding: 4px 12px;
    border-radius: 12px;
    font-size: 13px;
}

.badge-info {
    background: #e3f2fd;
    color: #1976d2;
}

.badge-secondary {
    background: #f5f5f5;
    color: #757575;
}

/* Duplicate group modal */
.duplicate-group-modal .modal-content {
    max-width: 700px;
    padding: 24px;
}

.duplicate-list {
    display: flex;
    flex-direction: column;
    gap: 16px;
    margin: 24px 0;
}

.duplicate-item {
    border: 1px solid #e0e0e0;
    border-radius: 8px;
    padding: 16px;
    background: #fafafa;
}

.duplicate-item.primary {
    border-color: #1976d2;
    background: #e3f2fd;
}

.duplicate-item .agency-info {
    display: flex;
    align-items: center;
    gap: 8px;
    margin-bottom: 8px;
}

.duplicate-item .agency-info strong {
    font-size: 16px;
}

.duplicate-item .assignment-code {
    font-family: 'Courier New', monospace;
    color: #666;
    margin-bottom: 4px;
}

.duplicate-item .confidence {
    font-size: 13px;
    color: #999;
    margin-top: 8px;
}
```

---

## Telegram Distribution

### DM Handling

#### Current Behavior (Without Duplicate Detection)
- Tutor matched to multiple agencies → receives multiple DMs for same assignment
- Confusing, feels like spam

#### New Behavior (With Duplicate Detection)
- Tutor matched to assignment → check if duplicate group exists
- If duplicate group: send **only primary assignment**
- DM includes note about other agencies

#### Implementation: `TutorDexAggregator/dm_assignments.py`

```python
def send_assignment_dm(chat_id, payload):
    """Send DM for an assignment, with duplicate awareness."""
    
    # Check for duplicate group
    assignment_id = payload.get('id')
    duplicate_info = _get_duplicate_info(assignment_id)
    
    if duplicate_info and not duplicate_info['is_primary']:
        # This is a duplicate, not primary
        # Skip if primary already sent
        if _was_already_sent_to_chat(chat_id, duplicate_info['primary_id']):
            log_event(logger, logging.INFO, "skipping_duplicate_dm",
                     assignment_id=assignment_id,
                     chat_id=chat_id,
                     reason="primary_already_sent")
            return {"status": "skipped", "reason": "duplicate"}
    
    # Format message
    message_text = _format_dm_message(payload, duplicate_info)
    
    # Send via Telegram Bot API
    response = requests.post(
        f"{DM_BOT_API_URL}",
        json={
            "chat_id": chat_id,
            "text": message_text,
            "parse_mode": "HTML",
            "reply_markup": _build_keyboard(payload, duplicate_info)
        }
    )
    
    return response.json()


def _format_dm_message(payload, duplicate_info):
    """Format DM text with duplicate note."""
    parsed = payload.get('parsed', {})
    
    # Standard message formatting
    lines = [
        f"<b>New Assignment Match!</b>",
        f"",
        f"📚 {parsed.get('academic_display_text', 'N/A')}",
        f"📍 {parsed.get('postal_code', ['N/A'])[0]}",
        f"💰 {parsed.get('rate_raw_text', 'Not specified')}",
    ]
    
    # Add duplicate note if applicable
    if duplicate_info and duplicate_info.get('other_agencies'):
        other_agencies = duplicate_info['other_agencies']
        if len(other_agencies) == 1:
            lines.append(f"")
            lines.append(f"ℹ️ Also posted by <b>{other_agencies[0]}</b>")
        else:
            lines.append(f"")
            lines.append(f"ℹ️ Also posted by <b>{len(other_agencies)} other agencies</b>")
    
    return "\n".join(lines)


def _build_keyboard(payload, duplicate_info):
    """Build inline keyboard with view duplicates button."""
    buttons = [
        [{
            "text": "Apply Now",
            "url": payload.get('message_link')
        }]
    ]
    
    # Add "View all versions" button if duplicates exist
    if duplicate_info and duplicate_info.get('duplicate_count', 0) > 1:
        assignment_id = payload.get('id')
        website_url = f"{WEBSITE_URL}/assignments?duplicate_group={duplicate_info['group_id']}"
        buttons.append([{
            "text": f"View all {duplicate_info['duplicate_count']} versions",
            "url": website_url
        }])
    
    return {"inline_keyboard": buttons}
```

### Broadcast Channel Handling

#### Configuration Options

Add to `TutorDexAggregator/.env.example`:

```bash
# Broadcast duplicate handling
BROADCAST_DUPLICATE_MODE=primary_only  # Options: all, primary_only, primary_with_note
```

**Modes:**
- `all`: Broadcast all assignments (current behavior)
- `primary_only`: Only broadcast primary from each duplicate group
- `primary_with_note`: Broadcast primary with note about other agencies

#### Implementation: `TutorDexAggregator/broadcast_assignments.py`

```python
def should_broadcast_assignment(payload):
    """Determine if assignment should be broadcast based on duplicate policy."""
    mode = os.environ.get('BROADCAST_DUPLICATE_MODE', 'primary_with_note')
    
    # Check duplicate status
    assignment_id = payload.get('id')
    duplicate_info = _get_duplicate_info(assignment_id)
    
    if not duplicate_info:
        # Not a duplicate, always broadcast
        return True
    
    if mode == 'all':
        # Broadcast everything
        return True
    
    if mode == 'primary_only' or mode == 'primary_with_note':
        # Only broadcast if this is the primary
        return duplicate_info['is_primary']
    
    return True  # Default: broadcast


def format_broadcast_message(payload):
    """Format broadcast message with duplicate note if applicable."""
    parsed = payload.get('parsed', {})
    
    # Standard formatting
    lines = [
        f"📚 <b>{parsed.get('academic_display_text', 'N/A')}</b>",
        f"",
        # ... rest of formatting ...
    ]
    
    # Add duplicate note if in primary_with_note mode
    mode = os.environ.get('BROADCAST_DUPLICATE_MODE', 'primary_with_note')
    if mode == 'primary_with_note':
        duplicate_info = _get_duplicate_info(payload.get('id'))
        if duplicate_info and duplicate_info.get('other_agencies'):
            agencies = duplicate_info['other_agencies']
            lines.append(f"")
            lines.append(f"ℹ️ <i>Also posted by: {', '.join(agencies)}</i>")
    
    return "\n".join(lines)
```

---

## Analytics & Monitoring

### Metrics to Track

#### Prometheus Metrics (Add to `TutorDexAggregator/observability_metrics.py`)

```python
# Duplicate detection metrics
duplicate_detected_total = Counter(
    'tutordex_duplicate_detected_total',
    'Total duplicate assignments detected',
    ['detection_confidence']  # high, medium, low
)

duplicate_group_size = Histogram(
    'tutordex_duplicate_group_size',
    'Size of duplicate groups (number of agencies)',
    buckets=[2, 3, 4, 5, 10]
)

duplicate_detection_latency = Histogram(
    'tutordex_duplicate_detection_seconds',
    'Time spent detecting duplicates per assignment'
)

# DM impact metrics
dm_skipped_duplicate_total = Counter(
    'tutordex_dm_skipped_duplicate_total',
    'DMs skipped due to duplicate detection'
)

# Broadcast impact metrics
broadcast_skipped_duplicate_total = Counter(
    'tutordex_broadcast_skipped_duplicate_total',
    'Broadcasts skipped due to duplicate detection'
)
```

#### Analytics Events (Add to `TutorDexBackend/app.py`)

```python
# User interaction events
@app.post("/analytics/event")
async def track_analytics_event(event: AnalyticsEvent):
    # ... existing event tracking ...
    
    # New duplicate-related events:
    # - duplicate_group_viewed: User clicked "view duplicates"
    # - duplicate_agency_selected: User applied via specific agency in group
    # - duplicate_preference_changed: User toggled hide/show duplicates
    pass
```

### Grafana Dashboard

Create dashboard: **Duplicate Assignment Insights**

**Panels:**
1. **Duplicate Detection Rate** (last 24h)
   - `rate(tutordex_duplicate_detected_total[1h])`
   - Gauge showing % of assignments with duplicates

2. **Duplicate Group Sizes**
   - Histogram of group sizes (2, 3, 4+ agencies)
   
3. **Top Agency Pairs** (who duplicates with whom)
   - Custom query on `assignment_duplicate_groups.meta`

4. **DM Reduction Impact**
   - `tutordex_dm_skipped_duplicate_total` 
   - Shows how many duplicate DMs were prevented

5. **User Preferences**
   - Pie chart: % users hiding vs showing duplicates
   
6. **Detection Performance**
   - `tutordex_duplicate_detection_seconds` percentiles
   - Should be < 100ms p95

### Alert Rules

Add to `observability/prometheus/alerts/duplicate_detection.yml`:

```yaml
groups:
  - name: duplicate_detection
    interval: 5m
    rules:
      - alert: HighDuplicateRate
        expr: |
          (
            rate(tutordex_duplicate_detected_total[1h]) 
            / 
            rate(tutordex_assignments_persisted_total[1h])
          ) > 0.50
        for: 15m
        labels:
          severity: warning
        annotations:
          summary: "High duplicate detection rate"
          description: "Over 50% of new assignments are duplicates ({{ $value }}% in last hour)"
      
      - alert: DuplicateDetectionSlow
        expr: |
          histogram_quantile(0.95, 
            rate(tutordex_duplicate_detection_seconds_bucket[5m])
          ) > 0.5
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Duplicate detection is slow"
          description: "P95 latency is {{ $value }}s (target < 0.1s)"
      
      - alert: DuplicateDetectionFailing
        expr: |
          rate(tutordex_duplicate_detection_errors_total[5m]) > 0.05
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "Duplicate detection is failing"
          description: "Error rate is {{ $value }}/sec"
```

---

## Admin Tools

### Manual Review Interface

Create admin endpoint: `GET /admin/duplicates/review`

**Features:**
- List duplicate groups ordered by confidence score (low confidence first)
- Show assignment details side-by-side
- Actions:
  - Confirm duplicate (keep group)
  - Mark as false positive (split group)
  - Merge groups (combine separate groups)
  - Change primary assignment

### Configuration Management

Create admin endpoint: `PUT /admin/duplicates/config`

**Configurable Parameters:**
- Detection thresholds (high/medium/low confidence)
- Signal weights (postal, subjects, levels, etc.)
- Time window (days to look back)
- Agency partnerships (known pairs that share assignments)
- Agency exclusions (agencies to skip)

### Agency Partnership Registry

Some agencies have known partnerships:

```json
{
  "agency_partnerships": [
    {
      "agencies": ["Elite Tutor", "SmartTutors"],
      "relationship": "partner",
      "auto_mark_as_duplicate": true,
      "notes": "Official partnership, share all assignments"
    },
    {
      "agencies": ["TutorCity", "TutorAnywhere"],
      "relationship": "competitor",
      "auto_mark_as_duplicate": false,
      "notes": "Sometimes cross-post popular assignments"
    }
  ]
}
```

---

## Rollout Plan

### Phase 1: Backend Detection (Week 1)
**Goal:** Detect duplicates, don't change user experience yet

- [ ] Add database schema (tables, indices)
- [ ] Implement detection algorithm
- [ ] Integrate into persistence pipeline
- [ ] Add metrics and logging
- [ ] Monitor false positive/negative rates

**Success Criteria:**
- Detection runs on all new assignments
- < 100ms p95 latency
- No persistence failures due to detection

### Phase 2: API Layer (Week 2)
**Goal:** Expose duplicate data via APIs

- [ ] Add duplicate fields to assignment responses
- [ ] Create `/assignments/{id}/duplicates` endpoint
- [ ] Update Supabase RPCs
- [ ] Add `show_duplicates` query parameter

**Success Criteria:**
- APIs return duplicate metadata
- No breaking changes to existing clients

### Phase 3: Website Display (Week 3)
**Goal:** Show duplicate badges, but don't filter yet

- [ ] Add duplicate badges to cards
- [ ] Create duplicate group modal
- [ ] Add user preference toggle
- [ ] Default to "show all" (current behavior)

**Success Criteria:**
- Users see duplicate indicators
- Modal shows all agencies
- No complaints about missing assignments

### Phase 4: Telegram Distribution (Week 4)
**Goal:** Reduce duplicate DMs and broadcasts

- [ ] Update DM logic to filter duplicates
- [ ] Update broadcast logic (primary_with_note mode)
- [ ] Monitor DM/broadcast volume reduction

**Success Criteria:**
- 20-40% reduction in DMs per assignment
- No tutor complaints about missing opportunities
- Broadcast channel quality improves

### Phase 5: Default to Hide Duplicates (Week 5+)
**Goal:** Clean up default UX after monitoring

- [ ] Change default to `hide_duplicates=true`
- [ ] Clearly communicate change to users
- [ ] Monitor engagement with "view duplicates"

**Success Criteria:**
- Users find it cleaner
- Users click "view duplicates" occasionally
- No increase in missed applications

---

## Testing Strategy

### Unit Tests

```python
# tests/test_duplicate_detector.py

def test_exact_postal_match():
    a = {'postal_code': '123456', 'subjects': ['Math'], 'levels': ['Secondary']}
    b = {'postal_code': '123456', 'subjects': ['Math'], 'levels': ['Secondary']}
    score = calculate_similarity_score(a, b)
    assert score >= 70  # Should be detected as duplicate


def test_fuzzy_postal_match():
    a = {'postal_code': '123456', ...}
    b = {'postal_code': '123457', ...}  # Off by 1
    score = calculate_similarity_score(a, b)
    assert score >= 65  # Should still score reasonably high


def test_different_districts_no_match():
    a = {'postal_code': '123456', ...}  # District 12
    b = {'postal_code': '343456', ...}  # District 34
    score = calculate_similarity_score(a, b)
    assert score < 40  # Should not match


def test_assignment_code_match():
    a = {'assignment_code': 'D2388', ...}
    b = {'assignment_code': 'D2388', ...}
    score = calculate_similarity_score(a, b)
    assert score >= 70  # Strong signal


def test_no_common_subjects():
    a = {'postal_code': '123456', 'subjects': ['Math'], ...}
    b = {'postal_code': '123456', 'subjects': ['English'], ...}
    score = calculate_similarity_score(a, b)
    assert score < 70  # Probably not a duplicate
```

### Integration Tests

```python
# tests/test_duplicate_integration.py

def test_duplicate_detection_pipeline():
    """Test end-to-end duplicate detection."""
    # Persist assignment A
    assignment_a = persist_assignment({...})
    
    # Persist similar assignment B from different agency
    assignment_b = persist_assignment({...})
    
    # Check that duplicate group was created
    group = get_duplicate_group(assignment_a['id'])
    assert group is not None
    assert len(group['members']) == 2
    assert assignment_a['id'] in group['member_ids']
    assert assignment_b['id'] in group['member_ids']


def test_dm_skips_duplicates():
    """Test that DMs are not sent for duplicate assignments."""
    # Setup duplicate group
    group_id = create_duplicate_group([assignment_a, assignment_b])
    
    # Send DM for primary
    send_dm(tutor_chat_id, assignment_a)
    assert dm_was_sent(tutor_chat_id, assignment_a['id'])
    
    # Try to send DM for duplicate
    result = send_dm(tutor_chat_id, assignment_b)
    assert result['status'] == 'skipped'
    assert result['reason'] == 'duplicate'
```

### Manual Testing Checklist

- [ ] Create test assignments with known duplicates
- [ ] Verify duplicate badges appear correctly
- [ ] Click "view duplicates" modal, check all versions shown
- [ ] Toggle "hide duplicates" preference, verify filtering
- [ ] Send test DM, verify only primary sent
- [ ] Check broadcast channel, verify primary_with_note works
- [ ] Test admin review interface
- [ ] Verify metrics appear in Grafana
- [ ] Test with 3+ duplicate group (edge case)

---

## Edge Cases & Considerations

### Edge Case 1: Assignment Code Collisions
**Problem:** Different agencies may use same code format (e.g., "D2388")
**Solution:** Assignment code alone is not sufficient; require postal code or subject match

### Edge Case 2: Legitimate Similar Assignments
**Problem:** Two nearby locations, same subject, different students
**Example:** Both in postal district 12, both Sec 3 Math, but different students
**Solution:** 
- Lower threshold (70 vs 85)
- Require high confidence for auto-grouping
- Manual review for edge cases

### Edge Case 3: Edited Assignments
**Problem:** Agency edits assignment (e.g., changes rate), still same assignment
**Solution:**
- Re-run duplicate detection on edits
- Update duplicate group if needed
- Don't create new group if already in one

### Edge Case 4: Assignment Closures
**Problem:** One agency closes, another still open
**Solution:**
- Update primary if primary closes
- Show "X of Y agencies still accepting" in UI
- Mark group as resolved if all close

### Edge Case 5: 3+ Duplicate Group
**Problem:** Same assignment across 4 agencies
**Solution:**
- Support N-way groups (not just pairs)
- Show list of all agencies
- Allow tutor to pick preferred agency

### Edge Case 6: False Positives
**Problem:** Algorithm incorrectly groups unrelated assignments
**Solution:**
- Admin manual review interface
- "Report incorrect grouping" button for users
- Lower confidence threshold over time based on feedback

### Edge Case 7: Partial Matches
**Problem:** Assignment A matches B and C, but B doesn't match C
**Example:** A has postal+subjects, B has postal only, C has subjects only
**Solution:**
- Use transitive closure carefully
- Require minimum direct score between any pair
- Flag low-confidence groups for review

---

## Future Enhancements

### Enhancement 1: Machine Learning
- Train ML model on manual review labels
- Learn agency-specific duplication patterns
- Improve fuzzy matching with embeddings

### Enhancement 2: Assignment Source Tracking
- Track which agency is "original source"
- Prefer original agency in primary selection
- Show source in UI ("Originally posted by X")

### Enhancement 3: Agency Reputation Scoring
- Track fill rates per agency
- User feedback on agencies
- Prioritize primary from high-reputation agencies

### Enhancement 4: Tutor Agency Preferences
- Let tutors specify preferred agencies
- DM/broadcast respects preferences
- "Only show me Agency X versions"

### Enhancement 5: Historical Analysis
- Track how long duplicates persist
- Which agencies duplicate most frequently
- Use data to optimize detection parameters

---

## FAQ

**Q: What if I only want to apply to one specific agency in a duplicate group?**
A: Click the duplicate badge to see all versions, then apply to your preferred agency.

**Q: Will hiding duplicates make me miss opportunities?**
A: No, you'll still see every unique assignment. Duplicates are the same opportunity posted by multiple agencies.

**Q: How do I know which agency to apply to?**
A: The system marks one as "Recommended" (primary), usually the earliest posting or highest quality. But you can apply to any.

**Q: Can duplicates have different details?**
A: Yes, sometimes. Agencies may format details differently. We show you all versions so you can compare.

**Q: What if the duplicate detection is wrong?**
A: Use "Report incorrect grouping" or contact support. We review flagged cases to improve accuracy.

**Q: Do broadcast messages show duplicates?**
A: By default, we only broadcast the primary version with a note about other agencies. This keeps the channel cleaner.

---

## Summary

This duplicate detection system provides:

1. **For Tutors:**
   - Cleaner assignment feed (less noise)
   - Transparency about which agencies posted the same assignment
   - Flexibility to choose preferred agency
   - Reduced duplicate DMs

2. **For System:**
   - Accurate assignment volume metrics
   - Improved matching (no duplicate notifications)
   - Better understanding of agency relationships
   - Data for future optimizations

3. **For Operators:**
   - Monitoring dashboard for duplicate trends
   - Admin tools for edge cases
   - Configurable detection parameters
   - Insights into agency partnerships

The implementation is phased to minimize risk, with extensive monitoring and fallbacks at each stage.
