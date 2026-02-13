"""
Tests for compilation detection heuristics.
"""

from TutorDexAggregator.compilation_detection import is_compilation


def test_single_assignment_not_flagged_with_multiple_id_fields_and_blocks():
    # Common single-assignment template that includes multiple "ID/Code" fields and blank-line blocks.
    # Previously this was often misclassified due to broad "ID:" counting + block-count heuristics.
    text = """
🔥 Available Assignment:

Level: Primary 5 English
Location: Kingsford Waterbay (Postal Code: 123456)

Job ID: NT29838
Assignment Code: NT29838
Rate: $55/hr

Please apply via https://example.com/apply
    """.strip()

    is_comp, triggers = is_compilation(text)
    assert is_comp is False
    assert triggers == []


def test_compilation_flagged_with_multiple_distinct_codes():
    text = """
🔥 Calling All Tutors! Apply now!

✅ Primary 5 English @ Kingsford Waterbay - Job ID: NT29838
✅ Primary 3 English @ Chai Chee - Assignment Code: FT12345
    """.strip()

    is_comp, triggers = is_compilation(text)
    assert is_comp is True
    assert any("Multiple distinct assignment codes" in t for t in triggers)


def test_compilation_flagged_with_enumerated_items():
    text = """
Assignment 1:
Job ID: AA10001

Assignment 2:
Job ID: BB20002

Assignment 3:
Job ID: CC30003
    """.strip()

    is_comp, triggers = is_compilation(text)
    assert is_comp is True
    assert any("Multiple enumerated items" in t for t in triggers)


def test_single_assignment_with_timeslots_and_one_url_not_flagged():
    # Single assignment template: many "Slot A/B/..." lines + one apply URL (often contains https:// + www.).
    text = """
Code ID: 28011H (Tuition Centre)
(NIE-Trained Tutors)
Subject: IB HL Chemistry
Address: Beauty World Centre
Frequency: 2 Hrs, multiple timeslots
Rate: $120/Hr

- Working Hours:
Slot A: Fri 6.30pm-8.30pm
Slot B: Sat 12.30pm-2.30pm
Slot C: Sat 2.45pm-4.45pm
------------------------------------
To apply: https://www.singaporetuitionteachers.com/adm/tutor/
    """.strip()

    is_comp, triggers = is_compilation(text)
    assert is_comp is False
    assert triggers == []


def test_single_assignment_with_hashtag_code_and_tags_not_flagged():
    # Tags like "#sec4" should not be treated as assignment codes.
    text = """
⚡️Sec 4 G3 English @ 455 Tampines Street 42⚡️
Rate: $35 - $45 hr
Code: #ASN1712

Tags: #sec4, #english
    """.strip()

    is_comp, triggers = is_compilation(text)
    assert is_comp is False
    assert triggers == []
