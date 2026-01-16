"""
Assignment Rating System (shared)

Pure functions used by both TutorDexBackend and TutorDexAggregator.
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

# Distance scoring parameters - Singapore-optimized breakpoints
DISTANCE_BREAKPOINTS = [
    (0.0, 5.0),
    (0.8, 4.0),
    (1.8, 3.0),
    (3.5, 2.0),
    (6.0, 1.0),
    (10.0, 0.0),
    (12.0, -1.5),
]

DISTANCE_SCORE_MIN = -1.5

RATE_BREAKPOINTS = [
    (0.25, 2.0),
    (0.15, 1.5),
    (0.10, 1.0),
    (0.05, 0.5),
    (0.00, 0.0),
    (-0.05, -0.5),
    (-0.10, -1.0),
    (-0.15, -1.5),
    (-0.25, -2.0),
]

RATE_SCORE_MAX = 2.0
RATE_SCORE_MIN = -2.0


def calculate_distance_score(distance_km: Optional[float]) -> float:
    if distance_km is None:
        return 0.0
    dist = float(distance_km)
    if dist >= DISTANCE_BREAKPOINTS[-1][0]:
        return DISTANCE_SCORE_MIN
    for i in range(len(DISTANCE_BREAKPOINTS) - 1):
        km_lower, score_lower = DISTANCE_BREAKPOINTS[i]
        km_upper, score_upper = DISTANCE_BREAKPOINTS[i + 1]
        if km_lower <= dist <= km_upper:
            if km_upper == km_lower:
                return score_lower
            position = (dist - km_lower) / (km_upper - km_lower)
            score = score_lower + (score_upper - score_lower) * position
            return max(DISTANCE_SCORE_MIN, min(5.0, score))
    return 0.0


def calculate_rate_score(
    assignment_rate_min: Optional[int],
    assignment_rate_max: Optional[int],
    tutor_avg_rate: Optional[float],
) -> float:
    if assignment_rate_min is None or assignment_rate_min <= 0:
        return 0.0
    if assignment_rate_max is not None and assignment_rate_max > assignment_rate_min:
        assignment_rate = (assignment_rate_min + assignment_rate_max) / 2.0
    else:
        assignment_rate = float(assignment_rate_min)
    if tutor_avg_rate is None or tutor_avg_rate <= 0:
        return 0.0

    delta = (assignment_rate - tutor_avg_rate) / tutor_avg_rate
    if delta >= RATE_BREAKPOINTS[0][0]:
        return RATE_SCORE_MAX
    if delta <= RATE_BREAKPOINTS[-1][0]:
        return RATE_SCORE_MIN
    for i in range(len(RATE_BREAKPOINTS) - 1):
        delta_lower, score_lower = RATE_BREAKPOINTS[i]
        delta_upper, score_upper = RATE_BREAKPOINTS[i + 1]
        if delta_upper <= delta <= delta_lower:
            if delta_lower == delta_upper:
                return score_lower
            position = (delta - delta_lower) / (delta_upper - delta_lower)
            score = score_lower + (score_upper - score_lower) * position
            return max(RATE_SCORE_MIN, min(RATE_SCORE_MAX, score))
    return 0.0


def calculate_assignment_rating(
    *,
    base_score: int,
    distance_km: Optional[float] = None,
    assignment_rate_min: Optional[int] = None,
    assignment_rate_max: Optional[int] = None,
    tutor_avg_rate: Optional[float] = None,
) -> float:
    return float(base_score) + calculate_distance_score(distance_km) + calculate_rate_score(
        assignment_rate_min, assignment_rate_max, tutor_avg_rate
    )


def get_rating_components(
    *,
    base_score: int,
    distance_km: Optional[float] = None,
    assignment_rate_min: Optional[int] = None,
    assignment_rate_max: Optional[int] = None,
    tutor_avg_rate: Optional[float] = None,
) -> Dict[str, float]:
    distance_component = calculate_distance_score(distance_km)
    rate_component = calculate_rate_score(assignment_rate_min, assignment_rate_max, tutor_avg_rate)
    total = float(base_score) + distance_component + rate_component
    return {
        "base_score": float(base_score),
        "distance_score": distance_component,
        "rate_score": rate_component,
        "total_rating": total,
        "total": total,
    }


def parse_rate_min_max(parsed: Any) -> Tuple[Optional[int], Optional[int]]:
    if not isinstance(parsed, dict):
        return None, None
    a = parsed.get("rate_min")
    b = parsed.get("rate_max")
    try:
        a_i = int(a) if a is not None else None
    except Exception:
        a_i = None
    try:
        b_i = int(b) if b is not None else None
    except Exception:
        b_i = None
    return a_i, b_i
