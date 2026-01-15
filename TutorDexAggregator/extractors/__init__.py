"""
Extractors package for TutorDex.

This package contains deterministic extractors for various signals:
- Academic requests (subjects, levels)
- Time availability
- Tutor types
- Postal codes
- Assignment status
- Non-assignment detection
"""

from extractors.academic_requests import parse_academic_requests as extract_academic_requests
from extractors.non_assignment_detector import detection_meta, is_non_assignment
from extractors.postal_code_estimated import estimate_postal_codes
from extractors.status_detector import detect_status as extract_status
from extractors.subjects_matcher import extract_subjects as match_subjects
from extractors.time_availability import extract_time_availability
from extractors.tutor_types import extract_tutor_types

__all__ = [
    "extract_academic_requests",
    "detection_meta",
    "is_non_assignment",
    "estimate_postal_codes",
    "extract_status",
    "match_subjects",
    "extract_time_availability",
    "extract_tutor_types",
]
