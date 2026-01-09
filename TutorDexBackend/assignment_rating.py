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


# Distance scoring parameters
DISTANCE_VERY_CLOSE_KM = _env_float("RATING_DISTANCE_VERY_CLOSE_KM", 1.0)
DISTANCE_CLOSE_KM = _env_float("RATING_DISTANCE_CLOSE_KM", 3.0)
DISTANCE_MODERATE_KM = _env_float("RATING_DISTANCE_MODERATE_KM", 5.0)
DISTANCE_FAR_KM = _env_float("RATING_DISTANCE_FAR_KM", 10.0)

# Distance score bonuses/penalties
DISTANCE_VERY_CLOSE_BONUS = _env_float("RATING_DISTANCE_VERY_CLOSE_BONUS", 5.0)
DISTANCE_CLOSE_BONUS = _env_float("RATING_DISTANCE_CLOSE_BONUS", 3.0)
DISTANCE_MODERATE_BONUS = _env_float("RATING_DISTANCE_MODERATE_BONUS", 1.0)
DISTANCE_FAR_PENALTY = _env_float("RATING_DISTANCE_FAR_PENALTY", -2.0)

# Rate scoring parameters
RATE_BONUS_THRESHOLD_PCT = _env_float("RATING_RATE_BONUS_THRESHOLD_PCT", 20.0)  # 20% above avg
RATE_BONUS_MAX = _env_float("RATING_RATE_BONUS_MAX", 3.0)
RATE_PENALTY_THRESHOLD_PCT = _env_float("RATING_RATE_PENALTY_THRESHOLD_PCT", 30.0)  # 30% below avg
RATE_PENALTY_MAX = _env_float("RATING_RATE_PENALTY_MAX", -2.0)


def calculate_distance_score(distance_km: Optional[float]) -> float:
    """
    Calculate distance-based score component.
    
    Scoring tiers:
    - < 1km: +5.0 (very close, highly valuable)
    - 1-3km: +3.0 (close, valuable)
    - 3-5km: +1.0 (moderate, slight bonus)
    - 5-10km: 0.0 (neutral)
    - > 10km: -2.0 (far, penalty)
    
    Args:
        distance_km: Distance in kilometers, or None if not available
        
    Returns:
        Distance score contribution
    """
    if distance_km is None:
        # No distance info (e.g., online assignments) - neutral
        return 0.0
    
    if distance_km < DISTANCE_VERY_CLOSE_KM:
        return DISTANCE_VERY_CLOSE_BONUS
    elif distance_km < DISTANCE_CLOSE_KM:
        return DISTANCE_CLOSE_BONUS
    elif distance_km < DISTANCE_MODERATE_KM:
        return DISTANCE_MODERATE_BONUS
    elif distance_km < DISTANCE_FAR_KM:
        return 0.0  # Neutral
    else:
        return DISTANCE_FAR_PENALTY


def calculate_rate_score(
    assignment_rate_min: Optional[int],
    assignment_rate_max: Optional[int],
    tutor_avg_rate: Optional[float],
) -> float:
    """
    Calculate rate-based score component.
    
    Compares assignment rate against tutor's historical average:
    - Assignment pays significantly more (>20% above avg): bonus up to +3.0
    - Assignment pays around average: neutral (0.0)
    - Assignment pays significantly less (<30% below avg): penalty up to -2.0
    
    Args:
        assignment_rate_min: Assignment minimum rate
        assignment_rate_max: Assignment maximum rate (can be None)
        tutor_avg_rate: Tutor's historical average rate (or None if no history)
        
    Returns:
        Rate score contribution
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
    
    # Calculate percentage difference
    rate_diff_pct = ((assignment_rate - tutor_avg_rate) / tutor_avg_rate) * 100.0
    
    if rate_diff_pct > RATE_BONUS_THRESHOLD_PCT:
        # High pay - give bonus
        # Scale linearly: 20% above = 0.0, 50%+ above = max bonus
        scale = min(1.0, (rate_diff_pct - RATE_BONUS_THRESHOLD_PCT) / 30.0)
        return scale * RATE_BONUS_MAX
    elif rate_diff_pct < -RATE_PENALTY_THRESHOLD_PCT:
        # Low pay - give penalty
        # Scale linearly: 30% below = 0.0, 60%+ below = max penalty
        scale = min(1.0, (abs(rate_diff_pct) - RATE_PENALTY_THRESHOLD_PCT) / 30.0)
        return scale * RATE_PENALTY_MAX
    else:
        # Around average - neutral
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
