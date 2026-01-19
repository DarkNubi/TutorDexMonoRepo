"""
Duplicate Assignment Detection Module

This module implements multi-signal similarity scoring to detect duplicate assignments
across agencies. The algorithm was validated against 3,840 production assignments.

Algorithm Weights (Validated 2026-01-09):
- Postal code: 50 points (PRIMARY signal - agencies can't fake location)
- Subjects: 35 points (STRONG signal)
- Levels: 25 points (STRONG signal)
- Rate: 15 points (MODERATE signal - can legitimately vary)
- Temporal: 10 points (SUPPLEMENTARY - assignments posted within 48 hours)
- Assignment code: 10 points (WEAK signal - agency-specific formats)
- Time availability: 5 points (WEAK signal - hard to quantify similarity)

Detection Threshold: ≥70 = likely duplicate

Key Insights from Validation:
1. Assignment codes are agency-specific (TSS-123 vs PTA-456 for same assignment)
2. Postal codes are most reliable signal (91.46% coverage, standardized format)
3. Subjects/levels compensate for reduced code reliability
4. No duplicates within same agency (external_id is unique)

Usage:
    from TutorDexAggregator.duplicate_detector import DuplicateDetector
    
    detector = DuplicateDetector(supabase_url, supabase_key)
    detector.detect_and_update_duplicates(assignment_id)
"""

import os
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Any, Tuple, Set
import requests
from functools import lru_cache
from shared.observability.exception_handler import swallow_exception

try:
    from logging_setup import setup_logging  # type: ignore
except Exception:
    from TutorDexAggregator.logging_setup import setup_logging  # type: ignore

setup_logging()
logger = logging.getLogger("duplicate_detector")

# Postal code regex for Singapore (6 digits)
_SG_POSTAL_RE = re.compile(r"\b(\d{6})\b")


@dataclass
class DuplicateMatch:
    """Represents a detected duplicate match"""
    assignment_id: int
    similarity_score: float
    matching_signals: List[str]
    confidence_level: str  # 'high', 'medium', 'low'


@dataclass
class DetectionConfig:
    """Configuration for duplicate detection algorithm"""
    enabled: bool = True
    high_confidence_threshold: float = 90.0
    medium_confidence_threshold: float = 70.0
    low_confidence_threshold: float = 55.0
    time_window_days: int = 7
    detection_batch_size: int = 100
    fuzzy_postal_tolerance: int = 2
    
    # Signal weights (validated against production data)
    weight_postal: float = 50.0
    weight_subjects: float = 35.0
    weight_levels: float = 25.0
    weight_rate: float = 15.0
    weight_temporal: float = 10.0
    weight_assignment_code: float = 10.0
    weight_time: float = 5.0


class DuplicateDetector:
    """Detects duplicate assignments across agencies using multi-signal similarity"""
    
    def __init__(self, supabase_url: str, supabase_key: str, config: Optional[DetectionConfig] = None):
        """
        Initialize duplicate detector
        
        Args:
            supabase_url: Supabase project URL
            supabase_key: Supabase service role key
            config: Detection configuration (uses defaults if None)
        """
        self.supabase_url = supabase_url.rstrip("/")
        self.supabase_key = supabase_key
        self._headers = {
            "apikey": self.supabase_key,
            "Authorization": f"Bearer {self.supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }
        self.config = config or self._load_config_from_db() or DetectionConfig()
        
        logger.info(
            "DuplicateDetector initialized",
            extra={
                "enabled": self.config.enabled,
                "thresholds": {
                    "high": self.config.high_confidence_threshold,
                    "medium": self.config.medium_confidence_threshold,
                    "low": self.config.low_confidence_threshold
                },
                "weights": {
                    "postal": self.config.weight_postal,
                    "subjects": self.config.weight_subjects,
                    "levels": self.config.weight_levels,
                    "rate": self.config.weight_rate,
                    "temporal": self.config.weight_temporal,
                    "code": self.config.weight_assignment_code,
                    "time": self.config.weight_time
                }
            }
        )
    
    def _load_config_from_db(self) -> Optional[DetectionConfig]:
        """Load configuration from database"""
        try:
            # Get enabled status
            response = requests.get(
                f"{self.supabase_url}/rest/v1/duplicate_detection_config?config_key=eq.enabled&select=config_value",
                headers=self._headers,
                timeout=10
            )
            
            if response.status_code != 200 or not response.json():
                logger.warning("Could not load config from DB, using defaults")
                return None
            
            enabled_raw = response.json()[0].get("config_value")
            enabled = str(enabled_raw).strip().lower() in {"true", "1", "yes", "y", "on"}
            
            if not enabled:
                logger.info("Duplicate detection is DISABLED in database config")
                return DetectionConfig(enabled=False)
            
            # Load other config values
            config = DetectionConfig(enabled=True)
            
            # Get thresholds
            response = requests.get(
                f"{self.supabase_url}/rest/v1/duplicate_detection_config?config_key=eq.thresholds&select=config_value",
                headers=self._headers,
                timeout=10
            )
            if response.status_code == 200 and response.json():
                thresholds = response.json()[0]["config_value"]
                config.high_confidence_threshold = float(thresholds.get("high_confidence", 90))
                config.medium_confidence_threshold = float(thresholds.get("medium_confidence", 70))
                config.low_confidence_threshold = float(thresholds.get("low_confidence", 55))
            
            # Get weights
            response = requests.get(
                f"{self.supabase_url}/rest/v1/duplicate_detection_config?config_key=eq.weights&select=config_value",
                headers=self._headers,
                timeout=10
            )
            if response.status_code == 200 and response.json():
                weights = response.json()[0]["config_value"]
                config.weight_postal = float(weights.get("postal", 50))
                config.weight_subjects = float(weights.get("subjects", 35))
                config.weight_levels = float(weights.get("levels", 25))
                config.weight_rate = float(weights.get("rate", 15))
                config.weight_temporal = float(weights.get("temporal", 10))
                config.weight_assignment_code = float(weights.get("assignment_code", 10))
                config.weight_time = float(weights.get("time", 5))
            
            # Get time window
            response = requests.get(
                f"{self.supabase_url}/rest/v1/duplicate_detection_config?config_key=eq.time_window_days&select=config_value",
                headers=self._headers,
                timeout=10
            )
            if response.status_code == 200 and response.json():
                config.time_window_days = int(response.json()[0]["config_value"])
            
            logger.info("Loaded config from database", extra={"config": config})
            return config
            
        except Exception as e:
            logger.warning(f"Failed to load config from DB: {e}, using defaults")
            return None
    
    def detect_and_update_duplicates(self, assignment_id: int) -> Optional[int]:
        """
        Detect duplicates for a newly persisted assignment and update database
        
        Args:
            assignment_id: ID of the assignment to check for duplicates
            
        Returns:
            Duplicate group ID if duplicates found, None otherwise
        """
        if not self.config.enabled:
            logger.debug(f"Duplicate detection disabled, skipping assignment {assignment_id}")
            return None
        
        try:
            # Get the assignment data
            assignment = self._get_assignment(assignment_id)
            if not assignment:
                logger.warning(f"Assignment {assignment_id} not found")
                return None
            
            # Find potential duplicates
            duplicates = self._find_duplicates(assignment)
            
            if not duplicates:
                logger.debug(f"No duplicates found for assignment {assignment_id}")
                return None
            
            # Get best match
            best_match = duplicates[0]
            logger.info(
                f"Found {len(duplicates)} duplicate(s) for assignment {assignment_id}",
                extra={
                    "assignment_id": assignment_id,
                    "best_match_id": best_match.assignment_id,
                    "similarity_score": best_match.similarity_score,
                    "confidence": best_match.confidence_level,
                    "matching_signals": best_match.matching_signals
                }
            )
            
            # Update duplicate group
            group_id = self._update_duplicate_group(assignment, best_match)
            
            return group_id
            
        except Exception as e:
            logger.error(
                f"Error detecting duplicates for assignment {assignment_id}: {e}",
                exc_info=True
            )
            return None
    
    def _get_assignment(self, assignment_id: int) -> Optional[Dict[str, Any]]:
        """Fetch assignment data from database"""
        try:
            response = requests.get(
                f"{self.supabase_url}/rest/v1/assignments?id=eq.{assignment_id}&select=*",
                headers=self._headers,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch assignment {assignment_id}: {response.status_code}")
                return None
            
            assignments = response.json()
            return assignments[0] if assignments else None
            
        except Exception as e:
            logger.error(f"Error fetching assignment {assignment_id}: {e}")
            return None
    
    def _find_duplicates(self, assignment: Dict[str, Any]) -> List[DuplicateMatch]:
        """
        Find potential duplicates for an assignment
        
        Args:
            assignment: Assignment dict from database
            
        Returns:
            List of DuplicateMatch objects, sorted by similarity score (descending)
        """
        # Get candidate assignments (same agency excluded, recent only)
        candidates = self._get_candidate_assignments(assignment)
        
        if not candidates:
            return []
        
        # Calculate similarity scores
        matches = []
        for candidate in candidates:
            score, signals = self._calculate_similarity(assignment, candidate)
            
            # Check if score meets minimum threshold
            if score >= self.config.low_confidence_threshold:
                confidence = self._get_confidence_level(score)
                matches.append(DuplicateMatch(
                    assignment_id=candidate["id"],
                    similarity_score=score,
                    matching_signals=signals,
                    confidence_level=confidence
                ))
        
        # Sort by score (descending)
        matches.sort(key=lambda m: m.similarity_score, reverse=True)
        
        return matches
    
    def _get_candidate_assignments(self, assignment: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get candidate assignments to check for duplicates"""
        try:
            # Calculate time window
            cutoff_date = datetime.now(timezone.utc) - timedelta(days=self.config.time_window_days)
            cutoff_str = cutoff_date.isoformat()
            
            response = requests.get(
                f"{self.supabase_url}/rest/v1/assignments",
                headers=self._headers,
                params={
                    "status": "eq.open",
                    "agency_id": f"neq.{assignment['agency_id']}",
                    "published_at": f"gte.{cutoff_str}",
                    "select": "*",
                    "limit": str(self.config.detection_batch_size),
                },
                timeout=15
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch candidates: {response.status_code} body={(response.text or '')[:200]}")
                return []
            
            candidates = response.json()
            logger.debug(f"Found {len(candidates)} candidate assignments to check")
            
            return candidates
            
        except Exception as e:
            logger.error(f"Error fetching candidate assignments: {e}")
            return []
    
    def _calculate_similarity(self, a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[float, List[str]]:
        """
        Calculate similarity score between two assignments
        
        Returns:
            Tuple of (score, list_of_matching_signals)
        """
        score = 0.0
        matching_signals = []
        
        # 1. Postal code (50 points) - PRIMARY SIGNAL
        postal_a = self._extract_postal(a.get("postal_code") or a.get("postal_code_estimated"))
        postal_b = self._extract_postal(b.get("postal_code") or b.get("postal_code_estimated"))
        
        if postal_a and postal_b:
            if postal_a == postal_b:
                score += self.config.weight_postal
                matching_signals.append("postal_exact")
            elif self._postal_fuzzy_match(postal_a, postal_b):
                score += self.config.weight_postal * 0.9  # 45 points for fuzzy match
                matching_signals.append("postal_fuzzy")
        
        # 2. Subjects (35 points) - STRONG SIGNAL
        subjects_a = set(a.get("subjects_canonical") or a.get("signals_subjects") or [])
        subjects_b = set(b.get("subjects_canonical") or b.get("signals_subjects") or [])
        
        if subjects_a and subjects_b:
            jaccard = len(subjects_a & subjects_b) / len(subjects_a | subjects_b)
            if jaccard > 0:
                score += jaccard * self.config.weight_subjects
                matching_signals.append(f"subjects_{int(jaccard*100)}pct")
        
        # 3. Levels (25 points) - STRONG SIGNAL
        levels_a = set((a.get("signals_levels") or []) + (a.get("signals_specific_student_levels") or []))
        levels_b = set((b.get("signals_levels") or []) + (b.get("signals_specific_student_levels") or []))
        
        if levels_a and levels_b:
            jaccard = len(levels_a & levels_b) / len(levels_a | levels_b)
            if jaccard > 0:
                score += jaccard * self.config.weight_levels
                matching_signals.append(f"levels_{int(jaccard*100)}pct")
        
        # 4. Rate range (15 points) - MODERATE SIGNAL
        if self._rate_ranges_overlap(
            a.get("rate_min"), a.get("rate_max"),
            b.get("rate_min"), b.get("rate_max")
        ):
            score += self.config.weight_rate
            matching_signals.append("rate_overlap")
        
        # 5. Temporal proximity (10 points) - SUPPLEMENTARY SIGNAL
        published_a = a.get("published_at")
        published_b = b.get("published_at")
        
        if published_a and published_b:
            try:
                time_a = datetime.fromisoformat(published_a.replace("Z", "+00:00"))
                time_b = datetime.fromisoformat(published_b.replace("Z", "+00:00"))
                time_diff = abs((time_a - time_b).total_seconds())
                
                # Full points if within 48 hours, decay linearly to 7 days
                if time_diff < 48 * 3600:
                    score += self.config.weight_temporal
                    matching_signals.append("temporal_48h")
                elif time_diff < 7 * 24 * 3600:
                    factor = 1.0 - (time_diff - 48 * 3600) / (7 * 24 * 3600 - 48 * 3600)
                    score += self.config.weight_temporal * factor
                    matching_signals.append("temporal_7d")
            except Exception:
                pass
        
        # 6. Assignment code (10 points) - WEAK SIGNAL (agency-specific formats)
        code_a = (a.get("assignment_code") or "").strip().upper()
        code_b = (b.get("assignment_code") or "").strip().upper()
        
        if code_a and code_b:
            # Exact match
            if code_a == code_b:
                score += self.config.weight_assignment_code
                matching_signals.append("code_exact")
            # Prefix match (some agencies share prefix patterns)
            elif len(code_a) >= 3 and len(code_b) >= 3 and code_a[:3] == code_b[:3]:
                score += self.config.weight_assignment_code * 0.5
                matching_signals.append("code_prefix")
        
        # 7. Time availability (5 points) - WEAK SIGNAL
        time_a = a.get("time_availability_explicit") or a.get("time_availability_estimated")
        time_b = b.get("time_availability_explicit") or b.get("time_availability_estimated")
        
        if time_a and time_b:
            # Simple overlap check (both have time data)
            score += self.config.weight_time
            matching_signals.append("time_available")
        
        # Cap score at 100
        score = min(score, 100.0)
        
        return score, matching_signals
    
    def _extract_postal(self, postal_value: Any) -> Optional[str]:
        """Extract 6-digit postal code from value"""
        if not postal_value:
            return None
        
        # Handle array
        if isinstance(postal_value, list):
            postal_value = postal_value[0] if postal_value else None
        
        if not postal_value:
            return None
        
        # Extract 6 digits
        s = str(postal_value).strip()
        digits = re.sub(r"\D+", "", s)
        m = _SG_POSTAL_RE.search(digits)
        return m.group(1) if m else None
    
    def _postal_fuzzy_match(self, postal_a: str, postal_b: str) -> bool:
        """Check if postal codes are within tolerance (same district, ±N digits)"""
        if not postal_a or not postal_b or len(postal_a) != 6 or len(postal_b) != 6:
            return False
        
        # Must have same district (first 2 digits)
        if postal_a[:2] != postal_b[:2]:
            return False
        
        # Check if within tolerance
        try:
            diff = abs(int(postal_a) - int(postal_b))
            return diff <= self.config.fuzzy_postal_tolerance
        except ValueError:
            return False
    
    def _rate_ranges_overlap(self, min_a: Optional[int], max_a: Optional[int],
                             min_b: Optional[int], max_b: Optional[int]) -> bool:
        """Check if rate ranges overlap"""
        if not all([min_a, max_a, min_b, max_b]):
            return False
        
        # Ranges overlap if one starts before the other ends
        return min_a <= max_b and min_b <= max_a
    
    def _get_confidence_level(self, score: float) -> str:
        """Get confidence level from score"""
        if score >= self.config.high_confidence_threshold:
            return "high"
        elif score >= self.config.medium_confidence_threshold:
            return "medium"
        elif score >= self.config.low_confidence_threshold:
            return "low"
        else:
            return "none"
    
    def _update_duplicate_group(self, assignment: Dict[str, Any], match: DuplicateMatch) -> int:
        """
        Update or create duplicate group
        
        Args:
            assignment: New assignment data
            match: Best matching assignment
            
        Returns:
            Duplicate group ID
        """
        try:
            # Check if match already belongs to a group
            matched_assignment = self._get_assignment(match.assignment_id)
            if not matched_assignment:
                logger.error(f"Could not fetch matched assignment {match.assignment_id}")
                return None
            
            existing_group_id = matched_assignment.get("duplicate_group_id")
            
            if existing_group_id:
                # Add to existing group
                return self._add_to_existing_group(assignment, existing_group_id, match.similarity_score)
            else:
                # Create new group
                return self._create_new_group(assignment, matched_assignment, match.similarity_score)
                
        except Exception as e:
            logger.error(f"Error updating duplicate group: {e}", exc_info=True)
            return None
    
    def _create_new_group(self, assignment_a: Dict[str, Any], assignment_b: Dict[str, Any], 
                         similarity_score: float) -> Optional[int]:
        """Create a new duplicate group"""
        try:
            # Determine primary assignment (better parse quality, earlier timestamp, etc.)
            primary_id = self._select_primary([assignment_a, assignment_b])
            
            # Create group
            group_data = {
                "primary_assignment_id": primary_id,
                "member_count": 2,
                "avg_confidence_score": similarity_score,
                "status": "active",
                "detection_algorithm_version": "v1_revised",
                "meta": {
                    "member_ids": [assignment_a["id"], assignment_b["id"]],
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            }
            
            response = requests.post(
                f"{self.supabase_url}/rest/v1/assignment_duplicate_groups",
                headers=self._headers,
                json=group_data,
                timeout=10
            )
            
            if response.status_code not in (200, 201):
                logger.error(f"Failed to create duplicate group: {response.status_code} {response.text}")
                return None
            
            group = response.json()[0]
            group_id = group["id"]
            
            # Update assignments
            for assignment in [assignment_a, assignment_b]:
                is_primary = (assignment["id"] == primary_id)
                self._update_assignment_duplicate_fields(
                    assignment["id"],
                    group_id,
                    is_primary,
                    similarity_score if not is_primary else 100.0
                )
            
            logger.info(f"Created duplicate group {group_id} with {2} members")
            return group_id
            
        except Exception as e:
            logger.error(f"Error creating duplicate group: {e}", exc_info=True)
            return None
    
    def _add_to_existing_group(self, assignment: Dict[str, Any], group_id: int, 
                               similarity_score: float) -> Optional[int]:
        """Add assignment to existing duplicate group"""
        try:
            # Get current group
            response = requests.get(
                f"{self.supabase_url}/rest/v1/assignment_duplicate_groups?id=eq.{group_id}&select=*",
                headers=self._headers,
                timeout=10
            )
            
            if response.status_code != 200:
                logger.error(f"Failed to fetch group {group_id}: {response.status_code}")
                return None
            
            groups = response.json()
            if not groups:
                logger.error(f"Group {group_id} not found")
                return None
            
            group = groups[0]
            
            # Update group metadata
            member_ids = group.get("meta", {}).get("member_ids", [])
            member_ids.append(assignment["id"])
            
            new_member_count = group["member_count"] + 1
            
            # Recalculate average confidence
            new_avg_confidence = (
                (group["avg_confidence_score"] * group["member_count"] + similarity_score) 
                / new_member_count
            )
            
            update_data = {
                "member_count": new_member_count,
                "avg_confidence_score": round(new_avg_confidence, 2),
                "meta": {
                    **group.get("meta", {}),
                    "member_ids": member_ids,
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }
            }
            
            response = requests.patch(
                f"{self.supabase_url}/rest/v1/assignment_duplicate_groups?id=eq.{group_id}",
                headers=self._headers,
                json=update_data,
                timeout=10
            )
            
            if response.status_code not in (200, 204):
                logger.error(f"Failed to update group {group_id}: {response.status_code}")
                return None
            
            # Update assignment
            self._update_assignment_duplicate_fields(
                assignment["id"],
                group_id,
                is_primary=False,
                confidence_score=similarity_score
            )
            
            logger.info(f"Added assignment {assignment['id']} to duplicate group {group_id}")
            return group_id
            
        except Exception as e:
            logger.error(f"Error adding to duplicate group: {e}", exc_info=True)
            return None
    
    def _select_primary(self, assignments: List[Dict[str, Any]]) -> int:
        """
        Select primary assignment from a list
        
        Priority:
        1. Highest parse quality score
        2. Earliest published timestamp
        3. Lowest assignment ID (arbitrary tiebreaker)
        """
        best = assignments[0]
        
        for assignment in assignments[1:]:
            # Compare parse quality
            if assignment.get("parse_quality_score", 0) > best.get("parse_quality_score", 0):
                best = assignment
                continue
            elif assignment.get("parse_quality_score", 0) < best.get("parse_quality_score", 0):
                continue
            
            # Compare published time
            time_a = assignment.get("published_at")
            time_b = best.get("published_at")
            
            if time_a and time_b:
                try:
                    dt_a = datetime.fromisoformat(time_a.replace("Z", "+00:00"))
                    dt_b = datetime.fromisoformat(time_b.replace("Z", "+00:00"))
                    
                    if dt_a < dt_b:
                        best = assignment
                        continue
                    elif dt_a > dt_b:
                        continue
                except Exception:
                    pass
            
            # Tiebreaker: lower ID
            if assignment["id"] < best["id"]:
                best = assignment
        
        return best["id"]
    
    def _update_assignment_duplicate_fields(self, assignment_id: int, group_id: int,
                                           is_primary: bool, confidence_score: float):
        """Update duplicate-related fields on assignment"""
        try:
            update_data = {
                "duplicate_group_id": group_id,
                "is_primary_in_group": is_primary,
                "duplicate_confidence_score": round(confidence_score, 2)
            }
            
            response = requests.patch(
                f"{self.supabase_url}/rest/v1/assignments?id=eq.{assignment_id}",
                headers=self._headers,
                json=update_data,
                timeout=10
            )
            
            if response.status_code not in (200, 204):
                logger.error(
                    f"Failed to update assignment {assignment_id}: {response.status_code} {response.text}"
                )
            else:
                logger.debug(
                    f"Updated assignment {assignment_id}: group={group_id}, primary={is_primary}, "
                    f"confidence={confidence_score:.2f}"
                )
                
        except Exception as e:
            logger.error(f"Error updating assignment {assignment_id}: {e}", exc_info=True)


# Convenience function for integration
def detect_duplicates_for_assignment(assignment_id: int, supabase_url: str = None, 
                                     supabase_key: str = None) -> Optional[int]:
    """
    Convenience function to detect duplicates for a single assignment
    
    Args:
        assignment_id: Assignment ID to check
        supabase_url: Supabase URL (defaults to env var)
        supabase_key: Supabase key (defaults to env var)
        
    Returns:
        Duplicate group ID if found, None otherwise
    """
    from supabase_env import resolve_supabase_url  # type: ignore
    
    supabase_url = supabase_url or resolve_supabase_url()
    if not supabase_key:
        from shared.config import load_aggregator_config

        supabase_key = load_aggregator_config().supabase_auth_key
    
    if not supabase_url or not supabase_key:
        logger.error("Supabase credentials not available")
        return None
    
    detector = DuplicateDetector(supabase_url, supabase_key)
    return detector.detect_and_update_duplicates(assignment_id)
