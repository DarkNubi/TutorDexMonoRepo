import os
import unittest


from TutorDexAggregator.supabase_persist import _build_assignment_row


class TestSupabasePersistSignalsRollup(unittest.TestCase):
    def setUp(self) -> None:
        # Ensure we don't accidentally do network geocoding in unit tests.
        os.environ["DISABLE_NOMINATIM"] = "1"

    def test_assignments_row_materializes_signals_rollups(self):
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
                "time_availability": {"explicit": {d: [] for d in ("monday","tuesday","wednesday","thursday","friday","saturday","sunday")},
                                     "estimated": {d: [] for d in ("monday","tuesday","wednesday","thursday","friday","saturday","sunday")},
                                     "note": None},
                "rate": {"min": None, "max": None, "raw_text": "S$50/hr"},
            },
            "meta": {
                "signals": {
                    "ok": True,
                    "signals": {
                        "subjects": ["English", "Maths"],
                        "levels": ["Primary"],
                        "specific_student_levels": ["Primary 5"],
                    },
                }
            },
        }
        row = _build_assignment_row(payload)
        self.assertEqual(row.get("signals_subjects"), ["English", "Maths"])
        self.assertEqual(row.get("signals_levels"), ["Primary"])
        self.assertEqual(row.get("signals_specific_student_levels"), ["Primary 5"])


if __name__ == "__main__":
    unittest.main()
