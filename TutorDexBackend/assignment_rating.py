"""
Assignment Rating System

Calculates a quality score for each assignment relative to a tutor's preferences.
The rating combines:
1. Base matching score (subjects, levels, etc.)
2. Distance score (heavily rewards nearby, penalizes far)
3. Rate score (rewards assignments with higher rates relative to tutor's history)

This allows for adaptive thresholds based on assignment volume rather than
fixed minimum scores.
"""

import os
import math
from typing import Any, Dict, Optional


def _env_float(name: str, default: float) -> float:
    """Get environment variable as float with fallback."""
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return float(str(v).strip())
    except Exception:
        return default


# Distance scoring parameters (tiers in km)
DISTANCE_TIER_1_KM = _env_float("RATING_DISTANCE_TIER_1_KM", 0.5)   # 0-500m
DISTANCE_TIER_2_KM = _env_float("RATING_DISTANCE_TIER_2_KM", 1.5)   # 500-1500m
DISTANCE_TIER_3_KM = _env_float("RATING_DISTANCE_TIER_3_KM", 3.0)   # 1.5-3km
DISTANCE_TIER_4_KM = _env_float("RATING_DISTANCE_TIER_4_KM", 5.0)   # 3-5km
DISTANCE_TIER_5_KM = _env_float("RATING_DISTANCE_TIER_5_KM", 10.0)  # 5-10km

# Distance score values at each tier boundary
DISTANCE_SCORE_0KM = _env_float("RATING_DISTANCE_SCORE_0KM", 5.0)     # Perfect match at 0km
DISTANCE_SCORE_TIER_1 = _env_float("RATING_DISTANCE_SCORE_TIER_1", 4.0)  # At 500m
DISTANCE_SCORE_TIER_2 = _env_float("RATING_DISTANCE_SCORE_TIER_2", 3.0)  # At 1.5km
DISTANCE_SCORE_TIER_3 = _env_float("RATING_DISTANCE_SCORE_TIER_3", 2.0)  # At 3km
DISTANCE_SCORE_TIER_4 = _env_float("RATING_DISTANCE_SCORE_TIER_4", 1.0)  # At 5km
DISTANCE_SCORE_TIER_5 = _env_float("RATING_DISTANCE_SCORE_TIER_5", 0.0)  # At 10km
DISTANCE_SCORE_FAR = _env_float("RATING_DISTANCE_SCORE_FAR", -2.0)       # Beyond 10km

# Rate scoring parameters
RATE_BONUS_THRESHOLD_PCT = _env_float("RATING_RATE_BONUS_THRESHOLD_PCT", 20.0)  # 20% above avg
RATE_BONUS_MAX = _env_float("RATING_RATE_BONUS_MAX", 3.0)
RATE_PENALTY_THRESHOLD_PCT = _env_float("RATING_RATE_PENALTY_THRESHOLD_PCT", 30.0)  # 30% below avg
RATE_PENALTY_MAX = _env_float("RATING_RATE_PENALTY_MAX", -2.0)


def calculate_distance_score(distance_km: Optional[float]) -> float:
    """
    Calculate distance-based score component using continuous interpolation.
    
    Scoring is continuous and linearly interpolated between tier boundaries:
    - 0km: +5.0 (perfect match)
    - 0-500m: +5.0 to +4.0 (very close)
    - 500m-1.5km: +4.0 to +3.0 (close)
    - 1.5-3km: +3.0 to +2.0 (moderate)
    - 3-5km: +2.0 to +1.0 (acceptable)
    - 5-10km: +1.0 to 0.0 (neutral)
    - > 10km: -2.0 (far, penalty)
    
    Args:
        distance_km: Distance in kilometers, or None if not available
        
    Returns:
        Distance score contribution (continuous value)
    """
    if distance_km is None:
        # No distance info (e.g., online assignments) - neutral
        return 0.0
    
    dist = float(distance_km)
    
    # Beyond 10km: constant penalty
    if dist > DISTANCE_TIER_5_KM:
        return DISTANCE_SCORE_FAR
    
    # Define tier boundaries and scores
    tiers = [
        (0.0, DISTANCE_SCORE_0KM),
        (DISTANCE_TIER_1_KM, DISTANCE_SCORE_TIER_1),
        (DISTANCE_TIER_2_KM, DISTANCE_SCORE_TIER_2),
        (DISTANCE_TIER_3_KM, DISTANCE_SCORE_TIER_3),
        (DISTANCE_TIER_4_KM, DISTANCE_SCORE_TIER_4),
        (DISTANCE_TIER_5_KM, DISTANCE_SCORE_TIER_5),
    ]
    
    # Find which tier range we're in and interpolate
    for i in range(len(tiers) - 1):
        km_lower, score_lower = tiers[i]
        km_upper, score_upper = tiers[i + 1]
        
        if km_lower <= dist <= km_upper:
            # Linear interpolation between the two tier boundaries
            if km_upper == km_lower:
                return score_lower
            
            # Calculate position within this tier (0.0 to 1.0)
            position = (dist - km_lower) / (km_upper - km_lower)
            
            # Interpolate between scores
            score = score_lower + (score_upper - score_lower) * position
            return score
    
    # Should not reach here, but return neutral as fallback
    return 0.0


def calculate_rate_score(
    assignment_rate_min: Optional[int],
    assignment_rate_max: Optional[int],
    tutor_avg_rate: Optional[float],
) -> float:
    """
    Calculate rate-based score component using continuous interpolation.
    
    Compares assignment rate against tutor's historical average with smooth scaling:
    - Rate significantly above average (>20%): bonus from 0 to +3.0 (max at 50%+ above)
    - Rate around average (±20%): neutral (0.0)
    - Rate significantly below average (<-20%): penalty from 0 to -2.0 (max at 50%+ below)
    
    Scoring is continuous and smoothly interpolated based on percentage difference.
    
    Args:
        assignment_rate_min: Assignment minimum rate
        assignment_rate_max: Assignment maximum rate (can be None)
        tutor_avg_rate: Tutor's historical average rate (or None if no history)
        
    Returns:
        Rate score contribution (continuous value)
    """
    # If no rate info, neutral
    if assignment_rate_min is None or assignment_rate_min <= 0:
        return 0.0
    
    # Calculate assignment midpoint rate
    if assignment_rate_max is not None and assignment_rate_max > assignment_rate_min:
        assignment_rate = (assignment_rate_min + assignment_rate_max) / 2.0
    else:
        assignment_rate = float(assignment_rate_min)
    
    # If tutor has no history, use assignment_rate as baseline (neutral)
    if tutor_avg_rate is None or tutor_avg_rate <= 0:
        return 0.0
    
    # Calculate percentage difference from tutor's average
    rate_diff_pct = ((assignment_rate - tutor_avg_rate) / tutor_avg_rate) * 100.0
    
    # Continuous scaling for bonuses and penalties
    if rate_diff_pct > RATE_BONUS_THRESHOLD_PCT:
        # High pay - continuous bonus
        # 20% above = 0.0, 50% above = max bonus (+3.0)
        # Linear interpolation between threshold and max
        excess_pct = rate_diff_pct - RATE_BONUS_THRESHOLD_PCT
        scale = min(1.0, excess_pct / 30.0)  # 30% range (20% to 50%)
        return scale * RATE_BONUS_MAX
        
    elif rate_diff_pct < -RATE_PENALTY_THRESHOLD_PCT:
        # Low pay - continuous penalty
        # -30% below = 0.0, -60% below = max penalty (-2.0)
        # Linear interpolation between threshold and max
        deficit_pct = abs(rate_diff_pct) - RATE_PENALTY_THRESHOLD_PCT
        scale = min(1.0, deficit_pct / 30.0)  # 30% range (30% to 60%)
        return scale * RATE_PENALTY_MAX
        
    elif rate_diff_pct > 0:
        # Between 0% and +20%: gradual ramp from 0.0 to 0.0
        # Smooth transition into bonus zone
        return 0.0
        
    elif rate_diff_pct < 0:
        # Between 0% and -30%: gradual ramp from 0.0 to 0.0
        # Smooth transition into penalty zone
        return 0.0
    
    else:
        # Exactly at average
        return 0.0


def calculate_assignment_rating(
    *,
    base_score: int,
    distance_km: Optional[float] = None,
    assignment_rate_min: Optional[int] = None,
    assignment_rate_max: Optional[int] = None,
    tutor_avg_rate: Optional[float] = None,
) -> float:
    """
    Calculate overall assignment rating for a tutor.
    
    Combines:
    - Base matching score (from subject/level/type matching)
    - Distance bonus/penalty
    - Rate bonus/penalty
    
    Args:
        base_score: Base matching score from matching algorithm
        distance_km: Distance to assignment in km
        assignment_rate_min: Assignment minimum hourly rate
        assignment_rate_max: Assignment maximum hourly rate
        tutor_avg_rate: Tutor's historical average rate
        
    Returns:
        Overall assignment rating (higher is better)
    """
    distance_component = calculate_distance_score(distance_km)
    rate_component = calculate_rate_score(
        assignment_rate_min, assignment_rate_max, tutor_avg_rate
    )
    
    # Combine components
    rating = float(base_score) + distance_component + rate_component
    
    return rating


def get_rating_components(
    *,
    base_score: int,
    distance_km: Optional[float] = None,
    assignment_rate_min: Optional[int] = None,
    assignment_rate_max: Optional[int] = None,
    tutor_avg_rate: Optional[float] = None,
) -> Dict[str, float]:
    """
    Get breakdown of rating components for debugging/transparency.
    
    Returns:
        Dictionary with rating components and total
    """
    distance_component = calculate_distance_score(distance_km)
    rate_component = calculate_rate_score(
        assignment_rate_min, assignment_rate_max, tutor_avg_rate
    )
    total = float(base_score) + distance_component + rate_component
    
    return {
        "base_score": float(base_score),
        "distance_score": distance_component,
        "rate_score": rate_component,
        "total_rating": total,
        "distance_km": distance_km,
        "assignment_rate_min": assignment_rate_min,
        "assignment_rate_max": assignment_rate_max,
        "tutor_avg_rate": tutor_avg_rate,
    }
