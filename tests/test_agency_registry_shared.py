import unittest

from TutorDexAggregator.agency_registry import get_agency_display_name as agg_get_agency_display_name
from shared.agency_registry import get_agency_display_name, normalize_chat_ref


class AgencyRegistrySharedTests(unittest.TestCase):
    def test_normalize_chat_reference(self) -> None:
        self.assertEqual(normalize_chat_ref("https://t.me/TuitionAssignmentsSG"), "t.me/tuitionassignmentssg")
        self.assertEqual(normalize_chat_ref("@TutorSociety"), "t.me/tutorsociety")

    def test_display_name_lookup(self) -> None:
        self.assertEqual(get_agency_display_name("t.me/tuitionassignmentssg"), "MindFlex")
        self.assertEqual(get_agency_display_name("@tutorsociety"), "Tutor Society")
        self.assertEqual(get_agency_display_name("t.me/unknownagency", default="Unknown"), "Unknown")

    def test_aggregator_wrapper(self) -> None:
        self.assertEqual(agg_get_agency_display_name("t.me/tuitionassignmentssg"), "MindFlex")


if __name__ == "__main__":
    unittest.main()
