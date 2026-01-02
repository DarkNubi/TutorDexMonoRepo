import unittest


from TutorDexBackend.matching import _learning_mode_is_online_only, _payload_to_query


class TestBackendMatchingV2Payload(unittest.TestCase):
    def test_learning_mode_dict_online(self):
        payload = {"parsed": {"learning_mode": {"mode": "Online", "raw_text": "online"}}}
        self.assertTrue(_learning_mode_is_online_only(payload))

    def test_learning_mode_dict_face_to_face(self):
        payload = {"parsed": {"learning_mode": {"mode": "Face-to-Face", "raw_text": "Face-to-Face Lessons"}}}
        self.assertFalse(_learning_mode_is_online_only(payload))

    def test_query_uses_signals_when_parsed_missing_subjects(self):
        payload = {
            "parsed": {"learning_mode": {"mode": "Online", "raw_text": "Online"}},
            "meta": {"signals": {"ok": True, "signals": {"subjects": ["E Maths", "A Maths"], "levels": ["Secondary"]}}},
        }
        q = _payload_to_query(payload)
        self.assertEqual(set(q.get("subjects") or []), {"E Maths", "A Maths"})
        self.assertIn("Secondary", (q.get("levels") or []))


if __name__ == "__main__":
    unittest.main()

