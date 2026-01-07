import os
import unittest
from unittest.mock import patch

from TutorDexAggregator.supabase_persist import _build_assignment_row


class TestPostalCoordsEstimated(unittest.TestCase):
    def setUp(self) -> None:
        # Ensure we don't accidentally do network geocoding in unit tests by default.
        os.environ["DISABLE_NOMINATIM"] = "1"

    def tearDown(self) -> None:
        # Clean up
        if "DISABLE_NOMINATIM" in os.environ:
            del os.environ["DISABLE_NOMINATIM"]

    @patch('TutorDexAggregator.supabase_persist._geocode_sg_postal')
    def test_explicit_postal_code_takes_precedence(self, mock_geocode):
        """Test that explicit postal code is used before estimated postal code."""
        mock_geocode.return_value = (1.3521, 103.8198)  # Mock coordinates
        
        payload = {
            "channel_link": "t.me/sample",
            "channel_title": "Sample",
            "message_id": 123,
            "channel_id": -100,
            "message_link": "https://t.me/sample/123",
            "raw_text": "raw",
            "parsed": {
                "assignment_code": "A1",
                "academic_display_text": "P5 English",
                "postal_code": ["123456"],
                "postal_code_estimated": ["654321"],
                "learning_mode": {"mode": "Online", "raw_text": "online"},
            },
        }
        
        row = _build_assignment_row(payload)
        
        # Should call geocode with explicit postal code first
        mock_geocode.assert_called_with("123456")
        self.assertEqual(row.get("postal_lat"), 1.3521)
        self.assertEqual(row.get("postal_lon"), 103.8198)
        self.assertFalse(row.get("postal_coords_estimated"))

    @patch('TutorDexAggregator.supabase_persist._geocode_sg_postal')
    def test_estimated_postal_code_used_when_no_explicit(self, mock_geocode):
        """Test that estimated postal code is used when explicit is not available."""
        mock_geocode.return_value = (1.3521, 103.8198)  # Mock coordinates
        
        payload = {
            "channel_link": "t.me/sample",
            "channel_title": "Sample",
            "message_id": 123,
            "channel_id": -100,
            "message_link": "https://t.me/sample/123",
            "raw_text": "raw",
            "parsed": {
                "assignment_code": "A1",
                "academic_display_text": "P5 English",
                "postal_code_estimated": ["654321"],
                "learning_mode": {"mode": "Online", "raw_text": "online"},
            },
        }
        
        row = _build_assignment_row(payload)
        
        # Should call geocode with estimated postal code
        mock_geocode.assert_called_with("654321")
        self.assertEqual(row.get("postal_lat"), 1.3521)
        self.assertEqual(row.get("postal_lon"), 103.8198)
        self.assertTrue(row.get("postal_coords_estimated"))

    @patch('TutorDexAggregator.supabase_persist._geocode_sg_postal')
    def test_estimated_used_when_explicit_geocoding_fails(self, mock_geocode):
        """Test that estimated postal code is used when explicit geocoding fails."""
        # First call (explicit) returns None, second call (estimated) returns coordinates
        mock_geocode.side_effect = [None, (1.3521, 103.8198)]
        
        payload = {
            "channel_link": "t.me/sample",
            "channel_title": "Sample",
            "message_id": 123,
            "channel_id": -100,
            "message_link": "https://t.me/sample/123",
            "raw_text": "raw",
            "parsed": {
                "assignment_code": "A1",
                "academic_display_text": "P5 English",
                "postal_code": ["999999"],  # Invalid postal code
                "postal_code_estimated": ["654321"],
                "learning_mode": {"mode": "Online", "raw_text": "online"},
            },
        }
        
        row = _build_assignment_row(payload)
        
        # Should call geocode twice: first with explicit, then with estimated
        self.assertEqual(mock_geocode.call_count, 2)
        self.assertEqual(row.get("postal_lat"), 1.3521)
        self.assertEqual(row.get("postal_lon"), 103.8198)
        self.assertTrue(row.get("postal_coords_estimated"))

    def test_no_coordinates_when_both_missing(self):
        """Test that no coordinates are set when both explicit and estimated are missing."""
        payload = {
            "channel_link": "t.me/sample",
            "channel_title": "Sample",
            "message_id": 123,
            "channel_id": -100,
            "message_link": "https://t.me/sample/123",
            "raw_text": "raw",
            "parsed": {
                "assignment_code": "A1",
                "academic_display_text": "P5 English",
                "learning_mode": {"mode": "Online", "raw_text": "online"},
            },
        }
        
        row = _build_assignment_row(payload)
        
        self.assertIsNone(row.get("postal_lat"))
        self.assertIsNone(row.get("postal_lon"))
        self.assertFalse(row.get("postal_coords_estimated"))


if __name__ == "__main__":
    unittest.main()
