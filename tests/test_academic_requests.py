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


if __name__ == "__main__":
    unittest.main()

