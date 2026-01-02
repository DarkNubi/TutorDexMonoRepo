import unittest


from TutorDexAggregator.extractors.subjects_matcher import extract_subjects


class TestSubjectsMatcherAliases(unittest.TestCase):
    def _canon(self, text: str):
        return [m.canonical for m in extract_subjects(text)]

    def test_math_aliases(self):
        got = self._canon("Need E.Maths and A-Math, also add maths")
        self.assertIn("E Maths", got)
        self.assertIn("A Maths", got)

    def test_science_combined_aliases(self):
        got = self._canon("Sec 2 combined science, phy/chem")
        self.assertIn("Science", got)
        self.assertIn("Physics/Chem", got)

    def test_humanities_aliases(self):
        got = self._canon("SS. + Hist. + POA. + Soc. Studies")
        self.assertIn("Social Studies", got)
        self.assertIn("History", got)
        self.assertIn("Accounting (POA)", got)

    def test_jc_ib_aliases(self):
        got = self._canon("GP. PW. TOK. EE.")
        self.assertIn("General Paper", got)
        self.assertIn("Project Work", got)
        self.assertIn("Theory of Knowledge", got)
        self.assertIn("Extended Essay", got)

    def test_language_aliases(self):
        got = self._canon("HCL and Higher CL, MT Chinese, ML, TL")
        self.assertIn("Higher Chinese", got)
        self.assertIn("Chinese", got)
        self.assertIn("Malay", got)
        self.assertIn("Tamil", got)


if __name__ == "__main__":
    unittest.main()

