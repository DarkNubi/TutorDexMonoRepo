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

import math
from typing import Any, Dict, Optional

# Distance scoring parameters - Singapore-optimized breakpoints
# Based on SG transport reality: walkability, bus/MRT connections, peak-hour pain
DISTANCE_BREAKPOINTS = [
    (0.0, 5.0),    # 0km: Perfect match, walkable
    (0.8, 4.0),    # 800m: 1-2 bus stops, still very convenient
    (1.8, 3.0),    # 1.8km: Short feeder bus / 1 MRT stop
    (3.5, 2.0),    # 3.5km: Time uncertainty starts
    (6.0, 1.0),    # 6km: Peak-hour pain begins
    (10.0, 0.0),   # 10km: Neutral threshold
    (12.0, -1.5),  # 12km: Hard floor, actively avoid beyond this
]

# Hard floor for distance penalty (never worse than this)
DISTANCE_SCORE_MIN = -1.5

# Rate scoring parameters - Singapore-optimized
# Based on SG tutor psychology: anchoring to historical average
RATE_BREAKPOINTS = [
    (0.25, 2.0),    # +25% or more: Hard cap
    (0.15, 1.5),    # +15%: Strong positive
    (0.10, 1.0),    # +10%: Noticeable positive
    (0.05, 0.5),    # +5%: Slight positive
    (0.00, 0.0),    # 0%: Neutral (at average)
    (-0.05, -0.5),  # -5%: Slight negative
    (-0.10, -1.0),  # -10%: Noticeable negative
    (-0.15, -1.5),  # -15%: Strong negative
    (-0.25, -2.0),  # -25% or less: Hard floor
]

# Hard caps for rate scoring (never worse/better than this)
RATE_SCORE_MAX = 2.0
RATE_SCORE_MIN = -2.0


def calculate_distance_score(distance_km: Optional[float]) -> float:
    """
    Calculate distance-based score component using continuous interpolation.
    Singapore-optimized: accounts for walkability, bus/MRT connections, and peak-hour pain.
    
    Breakpoints (km → score):
    - 0.0 km   → +5.0 (walkable distance)
    - 0.8 km   → +4.0 (1-2 bus stops)
    - 1.8 km   → +3.0 (short feeder bus / 1 MRT stop)
    - 3.5 km   → +2.0 (time uncertainty starts)
    - 6.0 km   → +1.0 (peak-hour pain begins)
    - 10.0 km  →  0.0 (neutral threshold)
    - >12.0 km → -1.5 (hard floor - tutors actively avoid)
    
    Args:
        distance_km: Distance in kilometers, or None if not available
        
    Returns:
        Distance score contribution (continuous value, clamped to [-1.5, +5.0])
    """
    if distance_km is None:
        # No distance info (e.g., online assignments) - neutral
        return 0.0
    
    dist = float(distance_km)
    
    # Beyond last breakpoint: use hard floor
    if dist >= DISTANCE_BREAKPOINTS[-1][0]:
        return DISTANCE_SCORE_MIN
    
    # Find which tier range we're in and interpolate
    for i in range(len(DISTANCE_BREAKPOINTS) - 1):
        km_lower, score_lower = DISTANCE_BREAKPOINTS[i]
        km_upper, score_upper = DISTANCE_BREAKPOINTS[i + 1]
        
        if km_lower <= dist <= km_upper:
            # Linear interpolation between the two breakpoints
            if km_upper == km_lower:
                return score_lower
            
            # Calculate position within this tier (0.0 to 1.0)
            position = (dist - km_lower) / (km_upper - km_lower)
            
            # Interpolate between scores
            score = score_lower + (score_upper - score_lower) * position
            
            # Clamp to valid range (safety check)
            return max(DISTANCE_SCORE_MIN, min(5.0, score))
    
    # Fallback: return neutral
    return 0.0


def calculate_rate_score(
    assignment_rate_min: Optional[int],
    assignment_rate_max: Optional[int],
    tutor_avg_rate: Optional[float],
) -> float:
    """
    Calculate rate-based score component using continuous interpolation.
    Singapore-optimized: accounts for tutor psychology and anchoring to historical average.
    
    Rate difference → Score mapping:
    - +25% or more  → +2.0 (hard cap)
    - +15%          → +1.5
    - +10%          → +1.0
    - +5%           → +0.5
    - 0%            →  0.0 (neutral, at average)
    - -5%           → -0.5
    - -10%          → -1.0
    - -15%          → -1.5
    - -25% or less  → -2.0 (hard floor)
    
    Scoring is continuous and smoothly interpolated based on percentage difference.
    Rate should never overpower distance + subject fit combined.
    
    Args:
        assignment_rate_min: Assignment minimum rate
        assignment_rate_max: Assignment maximum rate (can be None)
        tutor_avg_rate: Tutor's historical average rate (or None if no history)
        
    Returns:
        Rate score contribution (continuous value, clamped to [-2.0, +2.0])
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
    
    # Calculate percentage difference from tutor's average (as decimal, not percentage)
    delta = (assignment_rate - tutor_avg_rate) / tutor_avg_rate
    
    # Beyond the extreme breakpoints: use hard caps
    if delta >= RATE_BREAKPOINTS[0][0]:
        return RATE_SCORE_MAX
    if delta <= RATE_BREAKPOINTS[-1][0]:
        return RATE_SCORE_MIN
    
    # Find which range we're in and interpolate
    for i in range(len(RATE_BREAKPOINTS) - 1):
        delta_lower, score_lower = RATE_BREAKPOINTS[i]
        delta_upper, score_upper = RATE_BREAKPOINTS[i + 1]
        
        if delta_upper <= delta <= delta_lower:
            # Linear interpolation between the two breakpoints
            if delta_lower == delta_upper:
                return score_lower
            
            # Calculate position within this range (0.0 to 1.0)
            position = (delta - delta_lower) / (delta_upper - delta_lower)
            
            # Interpolate between scores
            score = score_lower + (score_upper - score_lower) * position
            
            # Clamp to valid range (safety check)
            return max(RATE_SCORE_MIN, min(RATE_SCORE_MAX, score))
    
    # Fallback: return neutral
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
