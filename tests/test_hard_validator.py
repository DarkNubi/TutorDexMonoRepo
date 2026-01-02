import unittest

from TutorDexAggregator.hard_validator import hard_validate


class HardValidatorTests(unittest.TestCase):
    def test_hard_validate_time_drops_invalid_entries(self) -> None:
        parsed = {
            "time_availability": {
                "explicit": {
                    "monday": ["9:00-10:00", "09:00–10:00", "25:00-26:00"],
                    "tuesday": [],
                    "wednesday": [],
                    "thursday": [],
                    "friday": [],
                    "saturday": [],
                    "sunday": [],
                },
                "estimated": {
                    "monday": [],
                    "tuesday": [],
                    "wednesday": [],
                    "thursday": [],
                    "friday": [],
                    "saturday": [],
                    "sunday": [],
                },
                "note": None,
            }
        }
        cleaned, violations = hard_validate(parsed, raw_text="Mon 9am", normalized_text=None)
        self.assertEqual(cleaned["time_availability"]["explicit"]["monday"], ["09:00-10:00"])
        self.assertTrue(any(v["code"] == "TIME" for v in violations))

    def test_rate_quote_like_forces_null_min_max(self) -> None:
        parsed = {"rate": {"min": 40, "max": 60, "raw_text": "pls quote"}}
        cleaned, violations = hard_validate(parsed, raw_text="Rate: pls quote", normalized_text=None)
        self.assertIsNone(cleaned["rate"]["min"])
        self.assertIsNone(cleaned["rate"]["max"])
        self.assertTrue(any(v["code"] == "RATE" for v in violations))

    def test_additional_remarks_requires_marker_and_support(self) -> None:
        parsed = {"additional_remarks": "Tutor to commit 6 months"}
        cleaned, _ = hard_validate(parsed, raw_text="No marker here", normalized_text=None)
        self.assertIsNone(cleaned["additional_remarks"])


if __name__ == "__main__":
    unittest.main()
