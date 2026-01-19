"""
Tests for the matching algorithm in TutorDexBackend/matching.py

Covers:
- Subject/level matching logic
- Distance-based filtering
- Rate range validation
- Edge cases (missing fields, malformed input)
- DM recipient filtering
"""

from typing import Any, Dict, List, Optional
from TutorDexBackend.matching import (
    match_from_payload,
    score_tutor,
    _tutor_subject_level_match,
    _passes_distance_filter,
    _haversine_km,
    _payload_to_query,
    _norm_text,
    _as_list,
    _canonical_type,
    _safe_float,
    _safe_int,
    _safe_radius_km,
)


class MockTutorStore:
    """Mock implementation of TutorStore protocol for testing"""

    def __init__(self, tutors: Dict[str, Dict[str, Any]]):
        self.tutors = tutors

    def list_tutor_ids(self) -> List[str]:
        return list(self.tutors.keys())

    def get_tutor(self, tutor_id: str) -> Optional[Dict[str, Any]]:
        return self.tutors.get(tutor_id)


class TestNormalizationFunctions:
    """Test utility normalization functions"""

    def test_norm_text_basic(self):
        assert _norm_text("Hello") == "hello"
        assert _norm_text("  WORLD  ") == "world"
        assert _norm_text(None) == ""
        assert _norm_text(123) == "123"

    def test_as_list_various_inputs(self):
        assert _as_list(None) == []
        assert _as_list("") == []
        assert _as_list("item") == ["item"]
        assert _as_list(["a", "b"]) == ["a", "b"]
        assert _as_list(123) == ["123"]
        assert _as_list([["nested"], "flat"]) == ["nested", "flat"]

    def test_canonical_type(self):
        assert _canonical_type("tuition centre") == "tuition centre"
        assert _canonical_type("tuition center") == "tuition centre"
        assert _canonical_type("private home") == "private"
        assert _canonical_type("PRIVATE") == "private"
        assert _canonical_type("unknown") == "unknown"
        assert _canonical_type(None) == ""

    def test_safe_float(self):
        assert _safe_float(1.23) == 1.23
        assert _safe_float("4.56") == 4.56
        assert _safe_float(None) is None
        assert _safe_float("invalid") is None

    def test_safe_int(self):
        assert _safe_int(42) == 42
        assert _safe_int("123") == 123
        assert _safe_int(None) is None
        assert _safe_int("invalid") is None
        assert _safe_int(3.7) == 3

    def test_safe_radius_km(self):
        assert _safe_radius_km(5.0) == 5.0
        assert _safe_radius_km("10") == 10.0
        assert _safe_radius_km(None) == 5.0  # default
        assert _safe_radius_km(0) == 5.0  # invalid, returns default
        assert _safe_radius_km(-1) == 5.0  # invalid
        assert _safe_radius_km(0.3) == 0.5  # minimum
        assert _safe_radius_km(100) == 50.0  # maximum


class TestPayloadToQuery:
    """Test conversion of assignment payload to query format"""

    def test_basic_payload_extraction(self):
        payload = {
            "meta": {
                "signals": {
                    "ok": True,
                    "signals": {
                        "subjects": ["math", "science"],
                        "levels": ["primary", "secondary"],
                        "specific_student_levels": ["primary 5", "primary 6"]
                    }
                }
            }
        }
        query = _payload_to_query(payload)
        assert query["subjects"] == ["math", "science"]
        assert query["levels"] == ["primary", "secondary"]
        assert query["specific_student_levels"] == ["primary 5", "primary 6"]

    def test_taxonomy_v2_canonical_subjects(self):
        """Prefer canonical subjects over legacy labels"""
        payload = {
            "meta": {
                "signals": {
                    "ok": True,
                    "signals": {
                        "subjects_canonical": ["MATH.SEC_EMATH"],
                        "subjects": ["mathematics"],
                        "levels": ["secondary"]
                    }
                }
            }
        }
        query = _payload_to_query(payload)
        assert query["subjects"] == ["MATH.SEC_EMATH"]

    def test_missing_signals(self):
        """Handle payload without signals gracefully"""
        payload = {}
        query = _payload_to_query(payload)
        assert query["subjects"] == []
        assert query["levels"] == []

    def test_learning_mode_extraction(self):
        payload = {
            "parsed": {
                "learning_mode": {
                    "mode": "online",
                    "raw_text": "Online tuition"
                }
            }
        }
        query = _payload_to_query(payload)
        # The function extracts the "mode" value when learning_mode is a dict
        assert query["learning_modes"] == "online"


class TestHaversineDistance:
    """Test distance calculation using Haversine formula"""

    def test_zero_distance(self):
        # Same location
        dist = _haversine_km(1.3521, 103.8198, 1.3521, 103.8198)
        assert dist < 0.001

    def test_known_distance(self):
        # Singapore downtown to Changi (approx 17-18 km)
        dist = _haversine_km(1.2897, 103.8501, 1.3644, 103.9915)
        assert 16.0 < dist < 19.0

    def test_cross_hemisphere(self):
        # Should handle large distances
        dist = _haversine_km(0, 0, 90, 0)
        assert dist > 5000  # Should be ~10,000 km


class TestSubjectLevelMatching:
    """Test subject and level matching logic"""

    def test_exact_subject_level_match(self):
        tutor = {
            "subjects": ["math", "science"],
            "levels": ["primary"]
        }
        query = {
            "subjects": ["math"],
            "levels": ["primary"],
            "specific_student_levels": []
        }
        assert _tutor_subject_level_match(tutor=tutor, query=query) is True

    def test_no_match_different_subject(self):
        tutor = {
            "subjects": ["english"],
            "levels": ["primary"]
        }
        query = {
            "subjects": ["math"],
            "levels": ["primary"],
            "specific_student_levels": []
        }
        assert _tutor_subject_level_match(tutor=tutor, query=query) is False

    def test_no_match_different_level(self):
        tutor = {
            "subjects": ["math"],
            "levels": ["secondary"]
        }
        query = {
            "subjects": ["math"],
            "levels": ["primary"],
            "specific_student_levels": []
        }
        assert _tutor_subject_level_match(tutor=tutor, query=query) is False

    def test_subject_pairs_specific_level_match(self):
        """Test matching with subject_pairs and specific levels"""
        tutor = {
            "subject_pairs": [
                {"subject": "math", "level": "primary", "specific_level": "primary 5"}
            ]
        }
        query = {
            "subjects": ["math"],
            "levels": ["primary"],
            "specific_student_levels": ["primary 5"]
        }
        assert _tutor_subject_level_match(tutor=tutor, query=query) is True

    def test_subject_pairs_general_level_match(self):
        """Test matching with subject_pairs without specific level"""
        tutor = {
            "subject_pairs": [
                {"subject": "math", "level": "primary", "specific_level": None}
            ]
        }
        query = {
            "subjects": ["math"],
            "levels": ["primary"],
            "specific_student_levels": []
        }
        assert _tutor_subject_level_match(tutor=tutor, query=query) is True

    def test_missing_fields(self):
        """Handle missing or empty fields gracefully"""
        tutor = {"subjects": [], "levels": []}
        query = {"subjects": ["math"], "levels": ["primary"], "specific_student_levels": []}
        assert _tutor_subject_level_match(tutor=tutor, query=query) is False

    def test_case_insensitive_matching(self):
        """Matching should be case-insensitive"""
        tutor = {
            "subjects": ["MATH"],
            "levels": ["PRIMARY"]
        }
        query = {
            "subjects": ["math"],
            "levels": ["primary"],
            "specific_student_levels": []
        }
        assert _tutor_subject_level_match(tutor=tutor, query=query) is True


class TestDistanceFiltering:
    """Test distance-based filtering logic"""

    def test_tutor_without_coords_passes(self):
        """Tutor without coordinates should pass distance filter"""
        tutor = {"postal_lat": None, "postal_lon": None}
        payload = {}
        assert _passes_distance_filter(tutor=tutor, payload=payload, distance_km=10.0) is True

    def test_online_assignment_passes(self):
        """Online-only assignments should pass regardless of distance"""
        tutor = {"postal_lat": 1.0, "postal_lon": 103.0, "dm_max_distance_km": 5.0}
        payload = {"parsed": {"learning_mode": "online"}}
        assert _passes_distance_filter(tutor=tutor, payload=payload, distance_km=100.0) is True

    def test_within_radius_passes(self):
        """Assignment within tutor's radius should pass"""
        tutor = {"postal_lat": 1.0, "postal_lon": 103.0, "dm_max_distance_km": 10.0}
        payload = {}
        assert _passes_distance_filter(tutor=tutor, payload=payload, distance_km=8.0) is True

    def test_outside_radius_fails(self):
        """Assignment outside tutor's radius should fail"""
        tutor = {"postal_lat": 1.0, "postal_lon": 103.0, "dm_max_distance_km": 5.0}
        payload = {}
        assert _passes_distance_filter(tutor=tutor, payload=payload, distance_km=7.0) is False

    def test_missing_distance_fails_when_tutor_has_coords(self):
        """When tutor has coords but distance can't be computed, fail to avoid spurious DMs"""
        tutor = {"postal_lat": 1.0, "postal_lon": 103.0, "dm_max_distance_km": 5.0}
        payload = {}
        assert _passes_distance_filter(tutor=tutor, payload=payload, distance_km=None) is False

    def test_default_radius_5km(self):
        """Default radius should be 5km when not specified"""
        tutor = {"postal_lat": 1.0, "postal_lon": 103.0}  # No dm_max_distance_km
        payload = {}
        assert _passes_distance_filter(tutor=tutor, payload=payload, distance_km=4.0) is True
        assert _passes_distance_filter(tutor=tutor, payload=payload, distance_km=6.0) is False


class TestScoreTutor:
    """Test tutor scoring algorithm"""

    def test_subject_match_adds_3_points(self):
        tutor = {"subjects": ["math"], "levels": [], "assignment_types": [], "tutor_kinds": [], "learning_modes": []}
        query = {"subjects": ["math"], "levels": [], "types": [], "tutor_type": [], "learning_modes": []}
        score, reasons = score_tutor(tutor, query)
        assert score == 3
        assert "subject" in reasons

    def test_level_match_adds_2_points(self):
        tutor = {"subjects": [], "levels": ["primary"], "assignment_types": [], "tutor_kinds": [], "learning_modes": []}
        query = {"subjects": [], "levels": ["primary"], "types": [], "tutor_type": [], "learning_modes": []}
        score, reasons = score_tutor(tutor, query)
        assert score == 2
        assert "level" in reasons

    def test_subject_and_level_match_adds_5_points(self):
        tutor = {"subjects": ["math"], "levels": ["primary"], "assignment_types": [], "tutor_kinds": [], "learning_modes": []}
        query = {"subjects": ["math"], "levels": ["primary"], "types": [], "tutor_type": [], "learning_modes": []}
        score, reasons = score_tutor(tutor, query)
        assert score == 5
        assert "subject" in reasons
        assert "level" in reasons

    def test_no_match_zero_score(self):
        tutor = {"subjects": ["english"], "levels": ["secondary"], "assignment_types": [], "tutor_kinds": [], "learning_modes": []}
        query = {"subjects": ["math"], "levels": ["primary"], "types": [], "tutor_type": [], "learning_modes": []}
        score, reasons = score_tutor(tutor, query)
        assert score == 0
        assert len(reasons) == 0


class TestMatchFromPayload:
    """Test end-to-end matching logic"""

    def test_basic_match(self):
        """Test basic subject+level matching"""
        tutors = {
            "t1": {
                "chat_id": "12345",
                "subjects": ["math"],
                "levels": ["primary"],
                "subject_pairs": [{"subject": "math", "level": "primary", "specific_level": None}]
            }
        }
        store = MockTutorStore(tutors)
        payload = {
            "meta": {
                "signals": {
                    "ok": True,
                    "signals": {
                        "subjects": ["math"],
                        "levels": ["primary"],
                        "specific_student_levels": []
                    }
                }
            },
            "parsed": {}
        }
        results = match_from_payload(store, payload)
        assert len(results) == 1
        assert results[0].tutor_id == "t1"
        assert results[0].chat_id == "12345"

    def test_no_match_different_subject(self):
        """Test no match when subjects don't overlap"""
        tutors = {
            "t1": {
                "chat_id": "12345",
                "subjects": ["english"],
                "levels": ["primary"],
                "subject_pairs": [{"subject": "english", "level": "primary", "specific_level": None}]
            }
        }
        store = MockTutorStore(tutors)
        payload = {
            "meta": {
                "signals": {
                    "ok": True,
                    "signals": {
                        "subjects": ["math"],
                        "levels": ["primary"],
                        "specific_student_levels": []
                    }
                }
            },
            "parsed": {}
        }
        results = match_from_payload(store, payload)
        assert len(results) == 0

    def test_distance_filtering_blocks_far_tutors(self):
        """Test distance filtering excludes tutors beyond radius"""
        tutors = {
            "t1": {
                "chat_id": "12345",
                "subjects": ["math"],
                "levels": ["primary"],
                "postal_lat": 1.3521,
                "postal_lon": 103.8198,
                "dm_max_distance_km": 5.0,
                "subject_pairs": [{"subject": "math", "level": "primary", "specific_level": None}]
            }
        }
        store = MockTutorStore(tutors)
        payload = {
            "meta": {
                "signals": {
                    "ok": True,
                    "signals": {
                        "subjects": ["math"],
                        "levels": ["primary"],
                        "specific_student_levels": []
                    }
                }
            },
            "parsed": {
                "postal_lat": 1.4437,  # ~10km away
                "postal_lon": 103.8014
            }
        }
        results = match_from_payload(store, payload)
        assert len(results) == 0  # Tutor is too far

    def test_distance_filtering_allows_close_tutors(self):
        """Test distance filtering includes tutors within radius"""
        tutors = {
            "t1": {
                "chat_id": "12345",
                "subjects": ["math"],
                "levels": ["primary"],
                "postal_lat": 1.3521,
                "postal_lon": 103.8198,
                "dm_max_distance_km": 5.0,
                "subject_pairs": [{"subject": "math", "level": "primary", "specific_level": None}]
            }
        }
        store = MockTutorStore(tutors)
        payload = {
            "meta": {
                "signals": {
                    "ok": True,
                    "signals": {
                        "subjects": ["math"],
                        "levels": ["primary"],
                        "specific_student_levels": []
                    }
                }
            },
            "parsed": {
                "postal_lat": 1.3550,  # ~0.3km away
                "postal_lon": 103.8200
            }
        }
        results = match_from_payload(store, payload)
        assert len(results) == 1
        assert results[0].distance_km is not None
        assert results[0].distance_km < 1.0

    def test_tutors_without_coords_skip_distance_filter(self):
        """Test tutors without coordinates aren't filtered by distance"""
        tutors = {
            "t1": {
                "chat_id": "12345",
                "subjects": ["math"],
                "levels": ["primary"],
                # No postal_lat/postal_lon
                "subject_pairs": [{"subject": "math", "level": "primary", "specific_level": None}]
            }
        }
        store = MockTutorStore(tutors)
        payload = {
            "meta": {
                "signals": {
                    "ok": True,
                    "signals": {
                        "subjects": ["math"],
                        "levels": ["primary"],
                        "specific_student_levels": []
                    }
                }
            },
            "parsed": {
                "postal_lat": 1.3521,
                "postal_lon": 103.8198
            }
        }
        results = match_from_payload(store, payload)
        assert len(results) == 1  # Should match despite distance
        assert results[0].distance_km is None

    def test_online_assignment_ignores_distance(self):
        """Test online assignments match regardless of distance"""
        tutors = {
            "t1": {
                "chat_id": "12345",
                "subjects": ["math"],
                "levels": ["primary"],
                "postal_lat": 1.3521,
                "postal_lon": 103.8198,
                "dm_max_distance_km": 5.0,
                "subject_pairs": [{"subject": "math", "level": "primary", "specific_level": None}]
            }
        }
        store = MockTutorStore(tutors)
        payload = {
            "meta": {
                "signals": {
                    "ok": True,
                    "signals": {
                        "subjects": ["math"],
                        "levels": ["primary"],
                        "specific_student_levels": []
                    }
                }
            },
            "parsed": {
                "learning_mode": "online",
                "postal_lat": 1.4437,  # 10km away, but online
                "postal_lon": 103.8014
            }
        }
        results = match_from_payload(store, payload)
        assert len(results) == 1  # Should match because online

    def test_skips_tutors_without_chat_id(self):
        """Test tutors without chat_id are excluded"""
        tutors = {
            "t1": {
                "subjects": ["math"],
                "levels": ["primary"],
                # No chat_id
                "subject_pairs": [{"subject": "math", "level": "primary", "specific_level": None}]
            }
        }
        store = MockTutorStore(tutors)
        payload = {
            "meta": {
                "signals": {
                    "ok": True,
                    "signals": {
                        "subjects": ["math"],
                        "levels": ["primary"],
                        "specific_student_levels": []
                    }
                }
            },
            "parsed": {}
        }
        results = match_from_payload(store, payload)
        assert len(results) == 0

    def test_rate_information_included(self):
        """Test rate information is extracted and included in results"""
        tutors = {
            "t1": {
                "chat_id": "12345",
                "subjects": ["math"],
                "levels": ["primary"],
                "subject_pairs": [{"subject": "math", "level": "primary", "specific_level": None}]
            }
        }
        store = MockTutorStore(tutors)
        payload = {
            "meta": {
                "signals": {
                    "ok": True,
                    "signals": {
                        "subjects": ["math"],
                        "levels": ["primary"],
                        "specific_student_levels": []
                    }
                }
            },
            "parsed": {
                "rate_min": 40,
                "rate_max": 60
            }
        }
        results = match_from_payload(store, payload)
        assert len(results) == 1
        assert results[0].rate_min == 40
        assert results[0].rate_max == 60

    def test_multiple_tutors_sorted_by_score(self):
        """Test multiple matching tutors are returned sorted by score"""
        tutors = {
            "t1": {
                "chat_id": "12345",
                "subjects": ["math"],
                "levels": ["primary"],
                "subject_pairs": [{"subject": "math", "level": "primary", "specific_level": None}]
            },
            "t2": {
                "chat_id": "67890",
                "subjects": ["math"],
                "levels": ["primary"],
                "subject_pairs": [{"subject": "math", "level": "primary", "specific_level": None}]
            }
        }
        store = MockTutorStore(tutors)
        payload = {
            "meta": {
                "signals": {
                    "ok": True,
                    "signals": {
                        "subjects": ["math"],
                        "levels": ["primary"],
                        "specific_student_levels": []
                    }
                }
            },
            "parsed": {}
        }
        results = match_from_payload(store, payload)
        assert len(results) == 2
        # Both should have same score, sorted by tutor_id
        assert results[0].score == results[1].score
