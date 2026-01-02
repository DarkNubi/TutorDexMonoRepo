import unittest

from TutorDexAggregator.normalize import normalize_text


class NormalizeTextTests(unittest.TestCase):
    def test_dash_normalization(self) -> None:
        raw = "a–b — c − d ‒ e"
        self.assertEqual(normalize_text(raw), "a-b - c - d - e")


    def test_token_splitting(self) -> None:
        raw = "sec3 jc2 p6 k2 year1 s3 j1"
        self.assertEqual(normalize_text(raw), "sec 3 jc 2 p 6 k 2 year 1 s 3 j 1")


    def test_time_punctuation_with_ampm(self) -> None:
        raw = "Thu 7.30pm and 11.45AM"
        self.assertEqual(normalize_text(raw), "Thu 7:30pm and 11:45AM")


    def test_time_range_left_side_dot_only_when_ampm_on_right(self) -> None:
        raw = "Available 2.30-5.30pm"
        self.assertEqual(normalize_text(raw), "Available 2:30-5:30pm")


    def test_whitespace_collapse(self) -> None:
        raw = "a\t\tb   c\n\n\n\nd"
        self.assertEqual(normalize_text(raw), "a b c\n\nd")


if __name__ == "__main__":
    unittest.main()
