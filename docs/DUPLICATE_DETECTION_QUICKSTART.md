# Duplicate Detection - Implementation Guide

## Quick Start

This guide helps you implement duplicate assignment detection in TutorDex. Start here if you're ready to build.

---

## 🎯 Implementation Priority

### Critical Path (Must Have)
1. ✅ Detection algorithm (similarity scoring)
2. ✅ Database schema (groups + assignment columns)
3. ✅ Aggregator integration (detect on persist)
4. ✅ DM filtering (skip duplicates)

### Important (Should Have)
5. ✅ API endpoints (expose duplicate data)
6. ✅ Website badges (show duplicate indicator)
7. ✅ Metrics & monitoring (Grafana dashboard)

### Nice to Have (Could Have)
8. ⭐ Duplicate group modal (detailed view)
9. ⭐ User preferences (hide/show toggle)
10. ⭐ Broadcast filtering (primary only)
11. ⭐ Admin review interface

---

## 📋 Phase 1: Backend Detection (Week 1)

### Step 1.1: Database Schema

**File**: Create `TutorDexAggregator/supabase sqls/2026-01-08_duplicate_detection.sql`

```sql
-- 1. Create duplicate groups table
CREATE TABLE IF NOT EXISTS public.assignment_duplicate_groups (
    id BIGSERIAL PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    primary_assignment_id BIGINT REFERENCES public.assignments(id) ON DELETE SET NULL,
    member_count INT NOT NULL DEFAULT 2,
    avg_confidence_score DECIMAL(5,2),
    status TEXT NOT NULL DEFAULT 'active',
    detection_algorithm_version TEXT NOT NULL DEFAULT 'v1',
    meta JSONB
);

CREATE INDEX IF NOT EXISTS duplicate_groups_primary_idx 
    ON public.assignment_duplicate_groups(primary_assignment_id);
CREATE INDEX IF NOT EXISTS duplicate_groups_status_idx 
    ON public.assignment_duplicate_groups(status) WHERE status = 'active';

-- 2. Add duplicate columns to assignments
ALTER TABLE public.assignments 
    ADD COLUMN IF NOT EXISTS duplicate_group_id BIGINT 
        REFERENCES public.assignment_duplicate_groups(id) ON DELETE SET NULL;
ALTER TABLE public.assignments 
    ADD COLUMN IF NOT EXISTS is_primary_in_group BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE public.assignments 
    ADD COLUMN IF NOT EXISTS duplicate_confidence_score DECIMAL(5,2);

CREATE INDEX IF NOT EXISTS assignments_duplicate_group_idx 
    ON public.assignments(duplicate_group_id) WHERE duplicate_group_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS assignments_is_primary_idx 
    ON public.assignments(is_primary_in_group, status) 
    WHERE is_primary_in_group = TRUE AND status = 'open';

-- 3. Configuration table
CREATE TABLE IF NOT EXISTS public.duplicate_detection_config (
    id BIGSERIAL PRIMARY KEY,
    config_key TEXT NOT NULL UNIQUE,
    config_value JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by TEXT
);

-- Initial config
INSERT INTO public.duplicate_detection_config (config_key, config_value) 
VALUES
    ('thresholds', '{"high_confidence": 85, "medium_confidence": 70, "low_confidence": 60}'),
    ('weights', '{"postal": 40, "assignment_code": 40, "subjects": 30, "levels": 20, "rate": 10, "time": 5, "temporal": 5}'),
    ('time_window_days', '7'),
    ('enabled', 'true')
ON CONFLICT (config_key) DO NOTHING;
```

**Deploy**:
```bash
# Apply in Supabase SQL Editor
cat TutorDexAggregator/supabase\ sqls/2026-01-08_duplicate_detection.sql
# Copy and paste into Supabase SQL Editor
# Run and verify no errors
```

---

### Step 1.2: Detection Module

**File**: Create `TutorDexAggregator/duplicate_detector.py`

```python
import os
import re
import logging
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta, timezone
import requests

from logging_setup import log_event, setup_logging
from supabase_env import resolve_supabase_url

setup_logging()
logger = logging.getLogger("duplicate_detector")


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


class DuplicateDetector:
    """Detect duplicate assignments across agencies."""
    
    def __init__(self):
        self.enabled = _truthy(os.environ.get("DUPLICATE_DETECTION_ENABLED", "false"))
        self.threshold = int(os.environ.get("DUPLICATE_DETECTION_THRESHOLD", "70"))
        self.time_window_days = int(os.environ.get("DUPLICATE_TIME_WINDOW_DAYS", "7"))
        self.batch_size = int(os.environ.get("DUPLICATE_DETECTION_BATCH_SIZE", "100"))
        
        # Weights (configurable)
        self.weight_postal = 40
        self.weight_code = 40
        self.weight_subjects = 30
        self.weight_levels = 20
        self.weight_rate = 10
        self.weight_time = 5
        self.weight_temporal = 5
        
        # Supabase config
        self.supabase_url = resolve_supabase_url()
        self.supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
        
        if self.enabled:
            log_event(logger, logging.INFO, "duplicate_detector_initialized",
                     threshold=self.threshold,
                     time_window_days=self.time_window_days)
    
    def find_duplicates(self, assignment_row: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        Find potential duplicates for a newly persisted assignment.
        
        Returns list of dicts: [{"assignment_id": X, "score": Y, "agency_name": Z}, ...]
        """
        if not self.enabled:
            return []
        
        assignment_id = assignment_row.get("id")
        agency_id = assignment_row.get("agency_id")
        
        if not assignment_id or not agency_id:
            return []
        
        # Get candidate assignments (recent, different agencies)
        candidates = self._get_candidate_assignments(assignment_row)
        
        # Score each candidate
        duplicates = []
        for candidate in candidates:
            score = self._calculate_score(assignment_row, candidate)
            if score >= self.threshold:
                duplicates.append({
                    "assignment_id": candidate["id"],
                    "score": score,
                    "agency_name": candidate.get("agency_name", "Unknown")
                })
        
        # Sort by score descending
        duplicates.sort(key=lambda x: x["score"], reverse=True)
        
        log_event(logger, logging.INFO, "duplicate_detection_complete",
                 assignment_id=assignment_id,
                 candidates_checked=len(candidates),
                 duplicates_found=len(duplicates),
                 max_score=duplicates[0]["score"] if duplicates else 0)
        
        return duplicates
    
    def _get_candidate_assignments(self, assignment_row: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Query recent assignments from different agencies."""
        agency_id = assignment_row.get("agency_id")
        time_window = datetime.now(timezone.utc) - timedelta(days=self.time_window_days)
        
        # Build query
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json"
        }
        
        # Query: status=open, published_at recent, different agency
        params = {
            "select": "id,agency_id,agency_name,assignment_code,postal_code,postal_code_estimated,"
                     "subjects_canonical,signals_subjects,signals_levels,signals_specific_student_levels,"
                     "rate_min,rate_max,time_availability_explicit,time_availability_estimated,published_at",
            "status": "eq.open",
            "published_at": f"gte.{time_window.isoformat()}",
            "agency_id": f"neq.{agency_id}",
            "limit": self.batch_size,
            "order": "published_at.desc"
        }
        
        try:
            response = requests.get(
                f"{self.supabase_url}/rest/v1/assignments",
                headers=headers,
                params=params,
                timeout=10
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                log_event(logger, logging.WARNING, "candidate_query_failed",
                         status_code=response.status_code,
                         error=response.text[:200])
                return []
        except Exception as e:
            log_event(logger, logging.ERROR, "candidate_query_exception",
                     error=str(e), exc_info=True)
            return []
    
    def _calculate_score(self, a: Dict[str, Any], b: Dict[str, Any]) -> float:
        """Calculate similarity score (0-100)."""
        score = 0.0
        
        # 1. Postal code (40 points)
        postal_a = self._extract_postal(a.get("postal_code") or a.get("postal_code_estimated"))
        postal_b = self._extract_postal(b.get("postal_code") or b.get("postal_code_estimated"))
        if postal_a and postal_b:
            if postal_a == postal_b:
                score += self.weight_postal
            elif self._postal_fuzzy_match(postal_a, postal_b):
                score += self.weight_postal * 0.85  # Slightly lower for fuzzy
        
        # 2. Assignment code (40 points)
        code_a = a.get("assignment_code")
        code_b = b.get("assignment_code")
        if code_a and code_b:
            if code_a == code_b:
                score += self.weight_code
            elif self._assignment_codes_similar(code_a, code_b):
                score += self.weight_code * 0.75  # Lower for prefix match
        
        # 3. Subjects (30 points)
        subjects_a = set(a.get("subjects_canonical") or a.get("signals_subjects") or [])
        subjects_b = set(b.get("subjects_canonical") or b.get("signals_subjects") or [])
        if subjects_a and subjects_b:
            jaccard = len(subjects_a & subjects_b) / len(subjects_a | subjects_b)
            score += jaccard * self.weight_subjects
        
        # 4. Levels (20 points)
        levels_a = set((a.get("signals_levels") or []) + (a.get("signals_specific_student_levels") or []))
        levels_b = set((b.get("signals_levels") or []) + (b.get("signals_specific_student_levels") or []))
        if levels_a and levels_b:
            jaccard = len(levels_a & levels_b) / len(levels_a | levels_b)
            score += jaccard * self.weight_levels
        
        # 5. Rate range (10 points)
        if self._rate_ranges_overlap(
            a.get("rate_min"), a.get("rate_max"),
            b.get("rate_min"), b.get("rate_max")
        ):
            score += self.weight_rate
        
        # 6. Time availability (5 points)
        if self._time_availability_similar(
            a.get("time_availability_explicit") or a.get("time_availability_estimated"),
            b.get("time_availability_explicit") or b.get("time_availability_estimated")
        ):
            score += self.weight_time
        
        # 7. Temporal proximity (5 points)
        pub_a = a.get("published_at")
        pub_b = b.get("published_at")
        if pub_a and pub_b:
            try:
                dt_a = datetime.fromisoformat(pub_a.replace("Z", "+00:00"))
                dt_b = datetime.fromisoformat(pub_b.replace("Z", "+00:00"))
                hours_apart = abs((dt_a - dt_b).total_seconds()) / 3600
                if hours_apart <= 48:
                    score += self.weight_temporal
                elif hours_apart <= 96:
                    score += self.weight_temporal * 0.6
            except Exception:
                pass
        
        return min(score, 100.0)
    
    def _extract_postal(self, value: Any) -> Optional[str]:
        """Extract 6-digit Singapore postal code."""
        if value is None:
            return None
        if isinstance(value, list):
            value = value[0] if value else None
        if not value:
            return None
        digits = re.sub(r"\D", "", str(value))
        match = re.search(r"\b(\d{6})\b", digits)
        return match.group(1) if match else None
    
    def _postal_fuzzy_match(self, postal_a: str, postal_b: str) -> bool:
        """Check if postal codes are similar (±1-2 digits, same district)."""
        if len(postal_a) != 6 or len(postal_b) != 6:
            return False
        # Same district (first 2 digits)
        if postal_a[:2] != postal_b[:2]:
            return False
        # Count differences
        diffs = sum(1 for i in range(6) if postal_a[i] != postal_b[i])
        return diffs <= 2
    
    def _assignment_codes_similar(self, code_a: str, code_b: str) -> bool:
        """Check if assignment codes are similar (prefix match)."""
        # Normalize: remove common prefixes, uppercase
        code_a_clean = re.sub(r"^(D|TUT|ASG|ASSIGN)[-_]?", "", code_a.upper())
        code_b_clean = re.sub(r"^(D|TUT|ASG|ASSIGN)[-_]?", "", code_b.upper())
        # Prefix match
        return (code_a_clean.startswith(code_b_clean) or 
                code_b_clean.startswith(code_a_clean))
    
    def _rate_ranges_overlap(self, min_a, max_a, min_b, max_b) -> bool:
        """Check if rate ranges overlap."""
        if None in (min_a, max_a, min_b, max_b):
            return False
        return max_a >= min_b and max_b >= min_a
    
    def _time_availability_similar(self, ta_a, ta_b) -> bool:
        """Check if time availability is similar (simple heuristic)."""
        # TODO: Implement detailed comparison
        # For now, just check if both are present
        return bool(ta_a and ta_b)
    
    def create_or_update_group(
        self, 
        primary_id: int, 
        duplicate_ids: List[int], 
        scores: List[float]
    ) -> Optional[int]:
        """Create a new duplicate group or add to existing."""
        if not self.enabled:
            return None
        
        # Check if any assignment already in a group
        existing_group_id = self._find_existing_group([primary_id] + duplicate_ids)
        
        if existing_group_id:
            # Add new members to existing group
            return self._add_to_group(existing_group_id, duplicate_ids, scores)
        else:
            # Create new group
            return self._create_group(primary_id, duplicate_ids, scores)
    
    def _find_existing_group(self, assignment_ids: List[int]) -> Optional[int]:
        """Check if any assignment is already in a group."""
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}"
        }
        
        # Query assignments for duplicate_group_id
        ids_str = ",".join(str(id) for id in assignment_ids)
        try:
            response = requests.get(
                f"{self.supabase_url}/rest/v1/assignments",
                headers=headers,
                params={
                    "select": "id,duplicate_group_id",
                    "id": f"in.({ids_str})",
                    "duplicate_group_id": "not.is.null"
                },
                timeout=5
            )
            
            if response.status_code == 200:
                rows = response.json()
                if rows:
                    return rows[0]["duplicate_group_id"]
        except Exception as e:
            log_event(logger, logging.WARNING, "find_existing_group_failed",
                     error=str(e))
        
        return None
    
    def _create_group(
        self, 
        primary_id: int, 
        duplicate_ids: List[int], 
        scores: List[float]
    ) -> Optional[int]:
        """Create a new duplicate group."""
        member_count = len(duplicate_ids) + 1
        avg_score = sum(scores) / len(scores) if scores else 0.0
        
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        
        try:
            # 1. Create group
            response = requests.post(
                f"{self.supabase_url}/rest/v1/assignment_duplicate_groups",
                headers=headers,
                json={
                    "primary_assignment_id": primary_id,
                    "member_count": member_count,
                    "avg_confidence_score": round(avg_score, 2),
                    "detection_algorithm_version": "v1",
                    "meta": {
                        "created_by": "duplicate_detector",
                        "scores": scores
                    }
                },
                timeout=10
            )
            
            if response.status_code not in (200, 201):
                log_event(logger, logging.ERROR, "create_group_failed",
                         status_code=response.status_code,
                         error=response.text[:200])
                return None
            
            group_data = response.json()
            if not group_data:
                return None
            
            group_id = group_data[0]["id"]
            
            # 2. Update assignments with group_id
            all_ids = [primary_id] + duplicate_ids
            for i, assignment_id in enumerate(all_ids):
                is_primary = (assignment_id == primary_id)
                score = scores[i-1] if i > 0 else avg_score
                
                self._update_assignment_group(
                    assignment_id, 
                    group_id, 
                    is_primary, 
                    score
                )
            
            log_event(logger, logging.INFO, "duplicate_group_created",
                     group_id=group_id,
                     primary_id=primary_id,
                     member_count=member_count,
                     avg_score=avg_score)
            
            return group_id
            
        except Exception as e:
            log_event(logger, logging.ERROR, "create_group_exception",
                     error=str(e), exc_info=True)
            return None
    
    def _update_assignment_group(
        self, 
        assignment_id: int, 
        group_id: int, 
        is_primary: bool, 
        score: float
    ):
        """Update assignment with duplicate group info."""
        headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.patch(
                f"{self.supabase_url}/rest/v1/assignments",
                headers=headers,
                params={"id": f"eq.{assignment_id}"},
                json={
                    "duplicate_group_id": group_id,
                    "is_primary_in_group": is_primary,
                    "duplicate_confidence_score": round(score, 2)
                },
                timeout=10
            )
            
            if response.status_code not in (200, 204):
                log_event(logger, logging.WARNING, "update_assignment_group_failed",
                         assignment_id=assignment_id,
                         status_code=response.status_code)
        except Exception as e:
            log_event(logger, logging.WARNING, "update_assignment_group_exception",
                     assignment_id=assignment_id, error=str(e))
    
    def _add_to_group(
        self, 
        group_id: int, 
        duplicate_ids: List[int], 
        scores: List[float]
    ) -> int:
        """Add new members to existing group."""
        # TODO: Implement
        return group_id


# Global instance
_detector_instance: Optional[DuplicateDetector] = None


def get_detector() -> DuplicateDetector:
    """Get singleton detector instance."""
    global _detector_instance
    if _detector_instance is None:
        _detector_instance = DuplicateDetector()
    return _detector_instance
```

---

### Step 1.3: Integration

**File**: Modify `TutorDexAggregator/supabase_persist.py`

Add at the end of the `upsert_assignment` function (after successful upsert):

```python
def upsert_assignment(row: Dict[str, Any]) -> Dict[str, Any]:
    # ... existing upsert logic ...
    
    # After successful upsert, check for duplicates
    if _duplicate_detection_enabled():
        try:
            from duplicate_detector import get_detector
            detector = get_detector()
            duplicates = detector.find_duplicates(row)
            
            if duplicates:
                # Select primary (highest score, or current assignment if tied)
                primary_id = row['id']
                duplicate_ids = [d['assignment_id'] for d in duplicates]
                scores = [d['score'] for d in duplicates]
                
                # Create or update group
                group_id = detector.create_or_update_group(
                    primary_id=primary_id,
                    duplicate_ids=duplicate_ids,
                    scores=scores
                )
                
                if group_id:
                    log_event(logger, logging.INFO, "duplicates_detected",
                             assignment_id=row['id'],
                             group_id=group_id,
                             duplicate_count=len(duplicates),
                             max_score=max(scores))
        except Exception as e:
            # Non-blocking: duplicate detection failure shouldn't break ingestion
            log_event(logger, logging.WARNING, "duplicate_detection_failed",
                     assignment_id=row.get('id'), error=str(e))
    
    return row


def _duplicate_detection_enabled() -> bool:
    """Check if duplicate detection is enabled."""
    return _truthy(os.environ.get("DUPLICATE_DETECTION_ENABLED", "false"))
```

---

### Step 1.4: Configuration

**File**: Add to `TutorDexAggregator/.env.example`

```bash
# Duplicate Detection
DUPLICATE_DETECTION_ENABLED=true
DUPLICATE_DETECTION_THRESHOLD=70  # Minimum score for duplicate (0-100)
DUPLICATE_TIME_WINDOW_DAYS=7  # Only check assignments from last N days
DUPLICATE_DETECTION_BATCH_SIZE=100  # Max candidates to score per assignment
```

---

### Step 1.5: Testing

**File**: Create `tests/test_duplicate_detector.py`

```python
import pytest
from TutorDexAggregator.duplicate_detector import DuplicateDetector


def test_exact_postal_match():
    detector = DuplicateDetector()
    
    a = {
        'postal_code': ['123456'],
        'subjects_canonical': ['MATH.SEC_EMATH'],
        'signals_levels': ['Secondary', 'Sec 3']
    }
    b = {
        'postal_code': ['123456'],
        'subjects_canonical': ['MATH.SEC_EMATH'],
        'signals_levels': ['Secondary', 'Sec 3']
    }
    
    score = detector._calculate_score(a, b)
    assert score >= 70, f"Expected score >= 70, got {score}"


def test_fuzzy_postal_match():
    detector = DuplicateDetector()
    
    a = {'postal_code': ['123456'], ...}
    b = {'postal_code': ['123457'], ...}  # Off by 1
    
    score = detector._calculate_score(a, b)
    assert score >= 60, "Fuzzy postal should still score reasonably"


def test_different_districts_no_match():
    detector = DuplicateDetector()
    
    a = {'postal_code': ['123456'], ...}  # District 12
    b = {'postal_code': ['343456'], ...}  # District 34
    
    score = detector._calculate_score(a, b)
    assert score < 40, "Different districts should not match"


def test_assignment_code_match():
    detector = DuplicateDetector()
    
    a = {'assignment_code': 'D2388', ...}
    b = {'assignment_code': 'D2388', ...}
    
    score = detector._calculate_score(a, b)
    assert score >= 70, "Exact assignment code should be strong signal"
```

**Run tests**:
```bash
cd /home/runner/work/TutorDexMonoRepo/TutorDexMonoRepo
pytest tests/test_duplicate_detector.py -v
```

---

### Step 1.6: Metrics

**File**: Add to `TutorDexAggregator/observability_metrics.py`

```python
from prometheus_client import Counter, Histogram

duplicate_detected_total = Counter(
    'tutordex_duplicate_detected_total',
    'Total duplicate assignments detected',
    ['confidence']
)

duplicate_group_size = Histogram(
    'tutordex_duplicate_group_size',
    'Size of duplicate groups',
    buckets=[2, 3, 4, 5, 10]
)

duplicate_detection_latency = Histogram(
    'tutordex_duplicate_detection_seconds',
    'Time spent detecting duplicates'
)
```

Update detection code to emit metrics:

```python
# In duplicate_detector.py
from observability_metrics import (
    duplicate_detected_total,
    duplicate_group_size,
    duplicate_detection_latency
)

with duplicate_detection_latency.time():
    duplicates = detector.find_duplicates(row)

if duplicates:
    confidence = "high" if max_score >= 85 else "medium"
    duplicate_detected_total.labels(confidence=confidence).inc()
    duplicate_group_size.observe(len(duplicates) + 1)
```

---

## ✅ Phase 1 Checklist

- [ ] SQL schema applied in Supabase
- [ ] `duplicate_detector.py` created
- [ ] Integration added to `supabase_persist.py`
- [ ] Environment variables configured
- [ ] Unit tests written and passing
- [ ] Metrics added to observability
- [ ] Docker compose rebuilt: `docker compose up -d --build`
- [ ] Monitoring: Check Prometheus metrics appear
- [ ] Manual test: Create similar assignments, verify grouping

---

## 🚀 Quick Validation

After deploying Phase 1:

1. **Check Supabase**:
   ```sql
   SELECT COUNT(*) FROM assignment_duplicate_groups;
   -- Should be > 0 after processing some assignments
   
   SELECT 
       duplicate_group_id,
       is_primary_in_group,
       agency_name,
       assignment_code,
       postal_code
   FROM assignments
   WHERE duplicate_group_id IS NOT NULL
   ORDER BY duplicate_group_id;
   ```

2. **Check Prometheus** (`http://localhost:9090`):
   ```promql
   tutordex_duplicate_detected_total
   tutordex_duplicate_group_size_bucket
   ```

3. **Check Logs**:
   ```bash
   docker compose logs aggregator-worker | grep duplicate
   ```

---

## 📞 Support

If you encounter issues:
- Check `docs/DUPLICATE_DETECTION.md` for full details
- Review error logs: `docker compose logs aggregator-worker`
- Verify Supabase schema is applied correctly
- Ensure environment variables are set
- Test with simple assignments first

---

**Next**: After Phase 1 is stable, move to Phase 2 (API Layer) in the full documentation.
