import re
import unittest


from TutorDexAggregator.normalize import normalize_text
from TutorDexAggregator.extractors.time_availability import extract_time_availability


TIME_RE = re.compile(r"^\d{2}:\d{2}-\d{2}:\d{2}$")
DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


def _slots(obj, section: str, day: str):
    return (((obj or {}).get(section) or {}).get(day)) or []


class TestTimeAvailability(unittest.TestCase):
    def test_explicit_day_single_time(self):
        raw = "Timing: TUESDAY AT 7PM"
        norm = normalize_text(raw)
        ta, meta = extract_time_availability(raw_text=raw, normalized_text=norm)
        self.assertIn("explicit", ta)
        self.assertEqual(_slots(ta, "explicit", "tuesday"), ["19:00-19:00"])
        self.assertEqual(_slots(ta, "estimated", "tuesday"), [])
        self.assertIsInstance(meta, dict)

    def test_estimated_after_time_multi_days(self):
        raw = "Preferably Tuesday or Thursday after 3pm"
        norm = normalize_text(raw)
        ta, _meta = extract_time_availability(raw_text=raw, normalized_text=norm)
        self.assertEqual(_slots(ta, "estimated", "tuesday"), ["15:00-23:00"])
        self.assertEqual(_slots(ta, "estimated", "thursday"), ["15:00-23:00"])

    def test_estimated_from_time_with_dot_normalization(self):
        raw = "Saturdays, from 11.45am"
        norm = normalize_text(raw)
        ta, _meta = extract_time_availability(raw_text=raw, normalized_text=norm)
        self.assertEqual(_slots(ta, "estimated", "saturday"), ["11:45-23:00"])

    def test_weekdays_policy_and_flexible_note_and_before_rule(self):
        raw = "Weekdays at 730pm / Saturday flexible / No Sunday before 3pm"
        norm = normalize_text(raw)
        ta, meta = extract_time_availability(raw_text=raw, normalized_text=norm)

        # Policy: weekdays keyword + single time => estimated Mon–Fri start=end.
        for d in ("monday", "tuesday", "wednesday", "thursday", "friday"):
            self.assertEqual(_slots(ta, "estimated", d), ["19:30-19:30"])
            self.assertEqual(_slots(ta, "explicit", d), [])

        # "Saturday flexible" => note only, no windows.
        self.assertEqual(_slots(ta, "explicit", "saturday"), [])
        self.assertEqual(_slots(ta, "estimated", "saturday"), [])
        self.assertIsInstance(ta.get("note"), (str, type(None)))
        self.assertTrue((ta.get("note") or "").lower().find("flexible") >= 0)

        # "before 3pm" => estimated window 08:00-15:00.
        self.assertEqual(_slots(ta, "estimated", "sunday"), ["08:00-15:00"])

        # Negation warning should be present (schema doesn't support unavailability).
        self.assertIn("parse_warnings", meta)
        self.assertTrue("negation_detected_near_time" in (meta.get("parse_warnings") or []))

    def test_tbc_note_only(self):
        raw = "Days and time: tbc"
        norm = normalize_text(raw)
        ta, _meta = extract_time_availability(raw_text=raw, normalized_text=norm)
        for d in DAYS:
            self.assertEqual(_slots(ta, "explicit", d), [])
            self.assertEqual(_slots(ta, "estimated", d), [])
        self.assertTrue((ta.get("note") or "").lower().find("tbc") >= 0)

    def test_day_list_with_single_relative_time_applies_to_all_days(self):
        raw = "Timing: MONDAY / THURSDAY / FRIDAY - AFTER 4PM"
        norm = normalize_text(raw)
        ta, _meta = extract_time_availability(raw_text=raw, normalized_text=norm)
        for d in ("monday", "thursday", "friday"):
            self.assertEqual(_slots(ta, "estimated", d), ["16:00-23:00"])

    def test_day_list_then_next_line_time_carry_over(self):
        raw = "Timing:\nMonday / Thursday / Friday\nAfter 4pm"
        norm = normalize_text(raw)
        ta, meta = extract_time_availability(raw_text=raw, normalized_text=norm)
        for d in ("monday", "thursday", "friday"):
            self.assertEqual(_slots(ta, "estimated", d), ["16:00-23:00"])
        self.assertIn("rules_fired", meta)
        self.assertTrue("carry_days_to_next_line" in (meta.get("rules_fired") or []))

    def test_output_shape_and_time_format_property(self):
        cases = [
            "Timing: Tue 7pm",
            "Available weekdays",
            "Preferably Thurs after 3pm",
            "Saturday morning",
        ]
        for raw in cases:
            norm = normalize_text(raw)
            ta, _meta = extract_time_availability(raw_text=raw, normalized_text=norm)
            self.assertIn("explicit", ta)
            self.assertIn("estimated", ta)
            self.assertIn("note", ta)
            for section in ("explicit", "estimated"):
                self.assertIsInstance(ta.get(section), dict)
                for d in DAYS:
                    self.assertIn(d, ta[section])
                    self.assertIsInstance(ta[section][d], list)
                    for slot in ta[section][d]:
                        self.assertTrue(TIME_RE.match(slot), f"bad slot: {slot!r}")


if __name__ == "__main__":
    unittest.main()
