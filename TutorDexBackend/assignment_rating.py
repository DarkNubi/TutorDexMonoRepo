"""
Assignment Rating System (backend compatibility wrapper).

The implementation lives in `shared/assignment_rating.py` so both the backend and
aggregator can use the same pure rating functions without cross-component imports.
"""

from shared.assignment_rating import (  # noqa: F401
    DISTANCE_BREAKPOINTS,
    DISTANCE_SCORE_MIN,
    RATE_BREAKPOINTS,
    RATE_SCORE_MAX,
    RATE_SCORE_MIN,
    calculate_assignment_rating,
    calculate_distance_score,
    calculate_rate_score,
    get_rating_components,
)

