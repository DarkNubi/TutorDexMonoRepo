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


def test_compilation_split_includes_details_before_bottom_job_id():
    from TutorDexAggregator.compilation_message_handler import (
        order_verified_identifiers,
        split_compilation_message,
    )

    text = """
🔻 Level and Subject(s): Economics
🔻 Location/Area: Online Tuition
🔻 Lesson Per Week: Once a week, 1.5 hours
Job ID: NT29838

🔻 Level and Subject(s): Primary 5 Math
🔻 Location/Area: Lorong Lew Lian
🔻 Lesson Per Week: Twice a week
Job ID: NT29839
    """.strip()

    identifiers = order_verified_identifiers(raw_message=text, verified=["NT29838", "NT29839"])
    segments = split_compilation_message(raw_message=text, identifiers=identifiers)

    assert len(segments) == 2
    assert "Economics" in segments[0]["text"]
    assert "Online Tuition" in segments[0]["text"]
    assert "NT29838" in segments[0]["text"]
    assert "Primary 5 Math" in segments[1]["text"]
    assert "Lorong Lew Lian" in segments[1]["text"]


def test_compilation_identifier_confirm_uses_deterministic_fallback(monkeypatch):
    from TutorDexAggregator import compilation_message_handler as handler

    text = """
Assignment 1
Subject: Economics
Job ID: NT29838

Assignment 2
Subject: Math
Job ID: NT29839
    """.strip()

    monkeypatch.setattr(
        handler,
        "extract_assignment_identifiers_llm",
        lambda **_: {"ok": False, "candidates": [], "parse_error": "No JSON"},
    )

    audit = handler.confirm_compilation_identifiers(raw_message=text, min_verified=2)

    assert audit["confirmed"] is True
    assert audit["verified"] == ["NT29838", "NT29839"]
    assert audit["deterministic_fallback_codes"] == ["NT29838", "NT29839"]


def test_compact_tuition_assignment_codes_trigger_compilation():
    from TutorDexAggregator.compilation_extractor import extract_assignment_codes

    text = """
Compiled Tuition Assignments

0706si: N1 Abacus @ 414 Jurong West Street 42 (S)640414
1 Hr, 1x A Week; $25-35/Hr

0706ts: N1 Phonics @ 105 Clementi Street 12. (S)120105
Female Tutor; 1.5 Hr, 1x A Week; $25-35/Hr
    """.strip()

    codes, meta = extract_assignment_codes(text)
    is_comp, triggers = is_compilation(text)

    assert codes[:2] == ["0706SI", "0706TS"]
    assert meta["codes_count"] == 2
    assert is_comp is True
    assert any("Multiple distinct assignment codes" in t for t in triggers)
