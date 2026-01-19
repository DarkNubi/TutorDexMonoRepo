import os
import sys
import unittest
from unittest.mock import patch, MagicMock

# Add TutorDexAggregator to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'TutorDexAggregator'))

# Set environment before importing modules that need it
os.environ["DISABLE_NOMINATIM"] = "0"  # Enable for testing
os.environ["DM_ENABLED"] = "0"  # Disable DM sending for unit tests

# Mock the logging_setup module before importing dm_assignments
sys.modules['logging_setup'] = MagicMock()
sys.modules['observability_metrics'] = MagicMock()

from dm_assignments import _get_or_geocode_assignment_coords
from broadcast_assignments import build_message_text


class TestDMPostalCoordsEstimated(unittest.TestCase):

    @patch('supabase_persist._geocode_sg_postal')
    def test_dm_uses_explicit_postal_code_first(self, mock_geocode):
        """Test that DM geocoding tries explicit postal code first."""
        mock_geocode.return_value = (1.3521, 103.8198)

        payload = {
            "parsed": {
                "postal_code": ["123456"],
                "postal_code_estimated": ["654321"],
            }
        }

        lat, lon, is_estimated = _get_or_geocode_assignment_coords(payload)

        # Should call with explicit postal code
        mock_geocode.assert_called_with("123456")
        self.assertEqual(lat, 1.3521)
        self.assertEqual(lon, 103.8198)
        self.assertFalse(is_estimated)
        # Should have set the flag in payload
        self.assertFalse(payload["parsed"]["postal_coords_estimated"])

    @patch('supabase_persist._geocode_sg_postal')
    def test_dm_falls_back_to_estimated_postal_code(self, mock_geocode):
        """Test that DM geocoding falls back to estimated when explicit is missing."""
        mock_geocode.return_value = (1.3521, 103.8198)

        payload = {
            "parsed": {
                "postal_code_estimated": ["654321"],
            }
        }

        lat, lon, is_estimated = _get_or_geocode_assignment_coords(payload)

        # Should call with estimated postal code
        mock_geocode.assert_called_with("654321")
        self.assertEqual(lat, 1.3521)
        self.assertEqual(lon, 103.8198)
        self.assertTrue(is_estimated)
        # Should have set the flag in payload
        self.assertTrue(payload["parsed"]["postal_coords_estimated"])

    @patch('supabase_persist._geocode_sg_postal')
    def test_dm_tries_estimated_when_explicit_fails(self, mock_geocode):
        """Test that DM geocoding tries estimated when explicit geocoding fails."""
        # First call (explicit) returns None, second call (estimated) returns coordinates
        mock_geocode.side_effect = [None, (1.3521, 103.8198)]

        payload = {
            "parsed": {
                "postal_code": ["999999"],  # Invalid
                "postal_code_estimated": ["654321"],
            }
        }

        lat, lon, is_estimated = _get_or_geocode_assignment_coords(payload)

        # Should call twice
        self.assertEqual(mock_geocode.call_count, 2)
        self.assertEqual(lat, 1.3521)
        self.assertEqual(lon, 103.8198)
        self.assertTrue(is_estimated)
        self.assertTrue(payload["parsed"]["postal_coords_estimated"])

    def test_dm_message_shows_estimated_label(self):
        """Test that DM message includes (estimated) label when distance is from estimated postal code."""
        payload = {
            "channel_title": "Test Agency",
            "parsed": {
                "assignment_code": "A123",
                "academic_display_text": "P5 Mathematics",
                "learning_mode": {"mode": "Face-to-Face"},
                "rate": {"raw_text": "$40/hr"},
            }
        }

        # Build message with estimated distance
        text = build_message_text(
            payload,
            distance_km=5.2,
            postal_coords_estimated=True
        )

        # Should contain distance with estimated label
        self.assertIn("📏 Distance: ~5.2 km (estimated)", text)

    def test_dm_message_without_estimated_label(self):
        """Test that DM message doesn't show (estimated) label when distance is from explicit postal code."""
        payload = {
            "channel_title": "Test Agency",
            "parsed": {
                "assignment_code": "A123",
                "academic_display_text": "P5 Mathematics",
                "learning_mode": {"mode": "Face-to-Face"},
                "rate": {"raw_text": "$40/hr"},
            }
        }

        # Build message with explicit distance
        text = build_message_text(
            payload,
            distance_km=5.2,
            postal_coords_estimated=False
        )

        # Should contain distance without estimated label
        self.assertIn("📏 Distance: ~5.2 km", text)
        self.assertNotIn("(estimated)", text)

    def test_dm_preserves_existing_coords_and_flag(self):
        """Test that existing coordinates and flag are preserved."""
        payload = {
            "parsed": {
                "postal_lat": 1.3521,
                "postal_lon": 103.8198,
                "postal_coords_estimated": True,
            }
        }

        lat, lon, is_estimated = _get_or_geocode_assignment_coords(payload)

        self.assertEqual(lat, 1.3521)
        self.assertEqual(lon, 103.8198)
        self.assertTrue(is_estimated)


if __name__ == "__main__":
    unittest.main()
