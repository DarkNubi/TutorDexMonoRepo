"""
Tests for online learning mode validation.

Ensures that assignments marked as online don't fail validation for missing address.
"""

from TutorDexAggregator.schema_validation import validate_parsed_assignment, _is_online_only


class TestIsOnlineOnly:
    """Test the _is_online_only helper function."""

    def test_exact_online(self):
        assert _is_online_only({"mode": "Online"}) is True
        assert _is_online_only({"mode": "online"}) is True
        assert _is_online_only({"mode": "ONLINE"}) is True

    def test_online_with_extra_text(self):
        # Common patterns in real messages
        assert _is_online_only({"mode": "Online Tuition"}) is True
        assert _is_online_only({"mode": "online tuition"}) is True
        assert _is_online_only({"mode": "Online Lesson"}) is True
        assert _is_online_only({"raw_text": "Online Tuition"}) is True

    def test_face_to_face(self):
        assert _is_online_only({"mode": "Face-to-Face"}) is False
        assert _is_online_only({"mode": "face-to-face"}) is False

    def test_hybrid(self):
        assert _is_online_only({"mode": "Hybrid"}) is False

    def test_none_or_empty(self):
        assert _is_online_only(None) is False
        assert _is_online_only({}) is False
        assert _is_online_only({"mode": None}) is False
        assert _is_online_only({"mode": ""}) is False


class TestOnlineAssignmentValidation:
    """Test that online assignments don't require address."""

    def test_online_without_address_passes(self):
        """Online assignments should pass validation even without address/postal."""
        parsed = {
            "learning_mode": {"mode": "Online", "raw_text": "Online Tuition"},
            "lesson_schedule": ["Monday 3pm-5pm"],
            # No address, postal_code, or nearest_mrt
        }

        ok, errors = validate_parsed_assignment(parsed)
        assert ok is True
        assert "missing_address_or_postal" not in errors

    def test_online_tuition_variant_passes(self):
        """Test with 'Online Tuition' text."""
        parsed = {
            "learning_mode": {"mode": "Online Tuition", "raw_text": "Online Tuition"},
            "lesson_schedule": ["Once a week, 1.5 hours per session"],
        }

        ok, errors = validate_parsed_assignment(parsed)
        assert ok is True
        assert "missing_address_or_postal" not in errors

    def test_face_to_face_without_address_fails(self):
        """Face-to-face assignments should fail without address."""
        parsed = {
            "learning_mode": {"mode": "Face-to-Face", "raw_text": "Face-to-Face"},
            "lesson_schedule": ["Monday 3pm-5pm"],
            # No address
        }

        ok, errors = validate_parsed_assignment(parsed)
        assert ok is False
        assert "missing_address_or_postal" in errors

    def test_no_learning_mode_without_address_fails(self):
        """Assignments without learning mode should fail without address."""
        parsed = {
            "lesson_schedule": ["Monday 3pm-5pm"],
            # No learning_mode, no address
        }

        ok, errors = validate_parsed_assignment(parsed)
        assert ok is False
        assert "missing_address_or_postal" in errors

    def test_online_with_postal_code_estimated_passes(self):
        """Online with estimated postal should also pass."""
        parsed = {
            "learning_mode": {"mode": "Online", "raw_text": "Online"},
            "lesson_schedule": ["Weekdays after 6pm"],
            "postal_code_estimated": ["123456"],  # This is OK but not required
        }

        ok, errors = validate_parsed_assignment(parsed)
        assert ok is True
