import unittest

from TutorDexAggregator.signals_builder import build_signals


class SignalsBuilderTests(unittest.TestCase):
    def test_prefers_academic_display_text(self) -> None:
        parsed = {"academic_display_text": "P4 English and P6 Math"}
        signals, err = build_signals(parsed=parsed, raw_text="raw irrelevant", normalized_text="normalized irrelevant")
        self.assertIsNone(err)
        self.assertIsNotNone(signals)
        self.assertEqual(signals["source"], "academic_display_text")
        self.assertEqual(signals["subjects"], ["English", "Maths"])
        self.assertEqual(signals["specific_student_levels"], ["Primary 4", "Primary 6"])

    def test_fallbacks_to_normalized_text(self) -> None:
        parsed = {}
        signals, err = build_signals(parsed=parsed, raw_text="raw", normalized_text="Sec 3 G3 English and G2 Math")
        self.assertIsNone(err)
        self.assertEqual(signals["source"], "normalized_text")
        self.assertIn("Secondary 3", signals["specific_student_levels"])
        self.assertIn("English", signals["subjects"])


if __name__ == "__main__":
    unittest.main()

