import unittest

from TutorDexAggregator.extractors.status_detector import detect_status
from TutorDexAggregator.supabase_persist import _build_assignment_row, _merge_patch_body


class StatusDetectorTests(unittest.TestCase):
    def test_elite_status_open(self) -> None:
        raw = "🌟 New Assignment Available! 🌟\nStatus: 🟢 Open\n\nAssignment code: S11050"
        d = detect_status(raw_text=raw, channel_link="t.me/elitetutorsg")
        self.assertIsNotNone(d)
        self.assertEqual(d.status, "open")

    def test_elite_status_closed(self) -> None:
        raw = "Status: 🔴 Closed\nAssignment code: S11052"
        d = detect_status(raw_text=raw, channel_link="t.me/elitetutorsg")
        self.assertIsNotNone(d)
        self.assertEqual(d.status, "closed")

    def test_tutoranywhr_status_open(self) -> None:
        raw = "🔹Assignment Code: 0694D29\n🔹Application Status: OPEN"
        d = detect_status(raw_text=raw, channel_link="t.me/TutorAnywhr")
        self.assertIsNotNone(d)
        self.assertEqual(d.status, "open")

    def test_tutoranywhr_status_closed(self) -> None:
        raw = "🔹Assignment Code: 4683D30\n🔹Application Status: CLOSED"
        d = detect_status(raw_text=raw, channel_link="t.me/TutorAnywhr")
        self.assertIsNotNone(d)
        self.assertEqual(d.status, "closed")

    def test_eduaid_closed_notice(self) -> None:
        raw = "⛔️ Assignment Closed ⛔️\n\n🔹 Assignment Code: 11307"
        d = detect_status(raw_text=raw, channel_link="t.me/eduaidtuition")
        self.assertIsNotNone(d)
        self.assertEqual(d.status, "closed")

    def test_eduaid_new_assignment(self) -> None:
        raw = "⭐ New Assignment ⭐\n\n🔹 Assignment Code: 11308"
        d = detect_status(raw_text=raw, channel_link="t.me/eduaidtuition")
        self.assertIsNotNone(d)
        self.assertEqual(d.status, "open")

    def test_non_allowlisted_channel_returns_none(self) -> None:
        raw = "Status: Closed\nAssignment code: X1"
        d = detect_status(raw_text=raw, channel_link="t.me/someotherchannel")
        self.assertIsNone(d)


class PersistStatusTests(unittest.TestCase):
    def test_build_assignment_row_sets_status(self) -> None:
        payload = {
            "channel_link": "t.me/elitetutorsg",
            "channel_username": "elitetutorsg",
            "raw_text": "Status: 🔴 Closed\nAssignment code: S11052",
            "parsed": {
                "assignment_code": "S11052",
                "academic_display_text": "Primary 4 Science",
                "learning_mode": "On-site",
            },
            "meta": {"signals": {"ok": True, "signals": {"subjects": ["Science"], "levels": ["Primary"], "specific_student_levels": ["Primary 4"]}}},
        }
        row = _build_assignment_row(payload)
        self.assertEqual(row.get("external_id"), "S11052")
        self.assertEqual(row.get("status"), "closed")
        meta = row.get("meta") or {}
        self.assertIn("status_detection", meta)
        self.assertEqual(meta["status_detection"]["status"], "closed")

    def test_merge_patch_body_updates_status_even_without_upgrade(self) -> None:
        existing = {"status": "open", "parse_quality_score": 10, "message_link": "a", "message_id": "1"}
        incoming = {"status": "closed", "parse_quality_score": 1, "message_link": "b", "message_id": "2"}
        patch = _merge_patch_body(existing=existing, incoming_row=incoming, force_upgrade=False)
        self.assertEqual(patch.get("status"), "closed")


if __name__ == "__main__":
    unittest.main()

