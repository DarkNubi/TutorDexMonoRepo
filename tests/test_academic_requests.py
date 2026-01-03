import unittest

from TutorDexAggregator.extractors.academic_requests import parse_academic_requests


class AcademicRequestsTests(unittest.TestCase):
    def test_p4_and_p6(self) -> None:
        res = parse_academic_requests(text="P4 English and P6 Math")
        self.assertEqual(res["subjects"], ["English", "Maths"])
        self.assertEqual(res["specific_student_levels"], ["Primary 4", "Primary 6"])
        self.assertIn("Primary", res["levels"])
        self.assertIsNotNone(res["academic_requests"])
        reqs = res["academic_requests"] or []
        self.assertEqual(len(reqs), 2)
        self.assertEqual(reqs[0]["specific_student_level"], "Primary 4")
        self.assertEqual(reqs[0]["subjects"], ["English"])
        self.assertEqual(reqs[1]["specific_student_level"], "Primary 6")
        self.assertEqual(reqs[1]["subjects"], ["Maths"])

    def test_secondary_with_stream_and_emaths(self) -> None:
        res = parse_academic_requests(text="Secondary 2 Science and Secondary 4 Express E-Maths (2026)")
        self.assertIn("Science", res["subjects"])
        self.assertIn("E Maths", res["subjects"])
        self.assertIn("Express", res["streams"])
        reqs = res["academic_requests"] or []
        self.assertEqual(len(reqs), 2)
        self.assertEqual(reqs[0]["specific_student_level"], "Secondary 2")
        self.assertEqual(reqs[0]["subjects"], ["Science"])
        self.assertEqual(reqs[1]["specific_student_level"], "Secondary 4")
        self.assertEqual(reqs[1]["stream"], "Express")
        self.assertEqual(reqs[1]["subjects"], ["E Maths"])

    def test_sec3_two_streams(self) -> None:
        res = parse_academic_requests(text="Sec 3 G3 English and G2 Math")
        self.assertIn("Secondary 3", res["specific_student_levels"])
        self.assertIn("G3", res["streams"])
        self.assertIn("G2", res["streams"])
        reqs = res["academic_requests"] or []
        self.assertEqual(len(reqs), 2)
        self.assertEqual(reqs[0]["stream"], "G3")
        self.assertEqual(reqs[0]["subjects"], ["English"])
        self.assertEqual(reqs[1]["stream"], "G2")
        self.assertEqual(reqs[1]["subjects"], ["Maths"])

    def test_level_only_pri_sec(self) -> None:
        res = parse_academic_requests(text="Pri Eng/Math/Sci/Chinese, Sec Eng/Creative Writing")
        self.assertIn("Primary", res["levels"])
        self.assertIn("Secondary", res["levels"])
        self.assertEqual(res["specific_student_levels"], [])
        self.assertEqual(res["subjects"], ["English", "Maths", "Science", "Chinese", "Creative Writing"])
        reqs = res["academic_requests"] or []
        self.assertEqual(len(reqs), 2)
        self.assertEqual(reqs[0]["level"], "Primary")
        self.assertEqual(reqs[0]["subjects"], ["English", "Maths", "Science", "Chinese"])
        self.assertEqual(reqs[1]["level"], "Secondary")
        self.assertEqual(reqs[1]["subjects"], ["English", "Creative Writing"])

    def test_ib_hl_language_and_literature(self) -> None:
        res = parse_academic_requests(text="IB Year 1 HL Language & Literature (English)")
        self.assertIn("IB", res["levels"])
        self.assertIn("IB Year 1", res["specific_student_levels"])
        self.assertIn("HL", res["streams"])
        self.assertIn("English Literature (IB/IGCSE)", res["subjects"])
        reqs = res["academic_requests"] or []
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["level"], "IB")
        self.assertEqual(reqs[0]["specific_student_level"], "IB Year 1")
        self.assertEqual(reqs[0]["stream"], "HL")
        self.assertEqual(reqs[0]["subjects"], ["English Literature (IB/IGCSE)"])

    def test_kindergarten_and_psle_level_only(self) -> None:
        res = parse_academic_requests(text="K1 English, PSLE Maths")
        self.assertIn("Kindergarten 1", res["specific_student_levels"])
        self.assertIn("Pre-School", res["levels"])
        self.assertIn("Primary", res["levels"])
        self.assertEqual(res["subjects"], ["English", "Maths"])

    def test_o_levels_and_n_levels_map_to_secondary(self) -> None:
        res = parse_academic_requests(text="O Levels Physics / N level Maths")
        self.assertIn("Secondary", res["levels"])
        self.assertEqual(res["specific_student_levels"], [])
        self.assertIn("Physics", res["subjects"])
        self.assertIn("Maths", res["subjects"])

    def test_a_levels_and_h2(self) -> None:
        res = parse_academic_requests(text="A Level H2 Maths")
        self.assertIn("Junior College", res["levels"])
        self.assertIn("H2", res["streams"])
        reqs = res["academic_requests"] or []
        self.assertEqual(len(reqs), 1)
        self.assertEqual(reqs[0]["level"], "Junior College")
        self.assertEqual(reqs[0]["stream"], "H2")
        self.assertEqual(reqs[0]["subjects"], ["Maths"])

    def test_normal_academic_and_integrated_programme(self) -> None:
        res = parse_academic_requests(text="Sec 2 Normal Academic English; Sec 3 Integrated Programme Math")
        self.assertIn("Secondary 2", res["specific_student_levels"])
        self.assertIn("Secondary 3", res["specific_student_levels"])
        self.assertIn("NA", res["streams"])
        self.assertIn("IP", res["streams"])
        reqs = res["academic_requests"] or []
        self.assertEqual(len(reqs), 2)
        self.assertEqual(reqs[0]["specific_student_level"], "Secondary 2")
        self.assertEqual(reqs[0]["stream"], "NA")
        self.assertEqual(reqs[0]["subjects"], ["English"])
        self.assertEqual(reqs[1]["specific_student_level"], "Secondary 3")
        self.assertEqual(reqs[1]["stream"], "IP")
        self.assertEqual(reqs[1]["subjects"], ["Maths"])

    def test_higher_level_and_standard_level_words(self) -> None:
        res = parse_academic_requests(text="IB Year 5 Higher Level Chemistry and Standard Level Maths")
        self.assertIn("IB", res["levels"])
        self.assertIn("IB Year 5", res["specific_student_levels"])
        self.assertIn("HL", res["streams"])
        self.assertIn("SL", res["streams"])
        reqs = res["academic_requests"] or []
        self.assertEqual(len(reqs), 2)
        self.assertEqual(reqs[0]["stream"], "HL")
        self.assertEqual(reqs[0]["subjects"], ["Chemistry"])
        self.assertEqual(reqs[1]["stream"], "SL")
        self.assertEqual(reqs[1]["subjects"], ["Maths"])


if __name__ == "__main__":
    unittest.main()
