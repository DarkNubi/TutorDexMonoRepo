import json
import re
import sys
from pathlib import Path

import pytest


def _ensure_aggregator_sys_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    agg_dir = repo_root / "TutorDexAggregator"
    agg_path = str(agg_dir)
    if agg_path in sys.path:
        sys.path.remove(agg_path)
    sys.path.insert(0, agg_path)
    sys.modules.pop("logging_setup", None)


def _iter_message_example_cases():
    examples_dir = Path(__file__).resolve().parents[1] / "TutorDexAggregator" / "message_examples"
    for path in sorted(examples_dir.glob("*.txt")):
        text = path.read_text(encoding="utf-8")
        for idx, match in enumerate(re.finditer(r"Raw:\s*(.*?)(?=\nJSON\s*:)", text, re.S), start=1):
            raw_text = match.group(1).strip()
            json_start = text.find("{", match.end())
            if json_start < 0:
                continue
            json_end = _find_balanced_json_end(text, json_start)
            if json_end is None:
                continue
            yield path.name, idx, raw_text, json.loads(text[json_start:json_end])


def _find_balanced_json_end(text: str, start: int) -> int | None:
    depth = 0
    in_string = False
    escaped = False
    for idx, char in enumerate(text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return idx + 1
    return None


def _enrich_and_validate(parsed, raw_text):
    _ensure_aggregator_sys_path()
    from schema_validation import validate_parsed_assignment
    from workers.enrichment_pipeline import (
        fill_address_from_text,
        fill_learning_mode_from_text,
        fill_lesson_schedule_from_text,
    )

    parsed, _ = fill_learning_mode_from_text(parsed, raw_text)
    parsed, _ = fill_lesson_schedule_from_text(parsed, raw_text)
    parsed, _ = fill_address_from_text(parsed, raw_text)
    return parsed, validate_parsed_assignment(parsed)


@pytest.mark.parametrize(
    ("source", "case_index", "raw_text", "parsed"),
    list(_iter_message_example_cases()),
)
def test_message_examples_for_all_agencies_still_validate(source, case_index, raw_text, parsed):
    """Every curated agency example should survive deterministic enrichment + validation."""

    _, (ok, errors) = _enrich_and_validate(parsed, raw_text)

    assert ok is True, f"{source} example {case_index} failed validation: {errors}"


@pytest.mark.parametrize(
    ("agency", "raw_text"),
    [
        (
            "elitetutorsg",
            """🌟 New A ignment Available! 🌟
Statu : 🔴 Clo ed
Assignment code: T8895
Tuition venue: Online
Subject: Adult level Chine e
No. of le on per week: 1
No. of hour per le on: 1 hour
""",
        ),
        (
            "TuitionAssignmentsSG",
            """Code ID: 2904pd
Subject: JC2 H2 Geography (CJC)
Addre : Online Le on
Frequency: 1.5 Hr , 1x A Week
- Online le on Permanently
""",
        ),
        (
            "TuitionAssignmentsSG",
            """Code ID: 2704B
Subject: JC1 H2 Phy ic
Addre : Online Le on  Only
Frequency: 1.5 Hr , 1x A Week
""",
        ),
        (
            "tuitionassignmentsttrsg",
            """🌟9 year old KET Math #A9638
🔻Rate: $35/h
🔻Day  and time: Weekday  afternoon
🔻Location: ONLINE
🔻Requirement : Experienced part time tutor
""",
        ),
        (
            "tuittysg",
            """[NEW] A ignment #3617
▪️ Subject: Engli h Le on Planning
▪️ Level: P1-P3, P4-P6, Sec 1-4
▪️ Location: Online, Remote
▪️ Time and day: To complete a ap
▪️ Rate: $400 per term
""",
        ),
        (
            "TutorSociety",
            """📣 Greeting , tutor ! Here'  a new tuition a ignment for you!
📌 Subject: Sec 4 Exp Engli h
📌 Location: Online
📌 Day & Time: to be di cu ed
📌 Rate: Tutor to propo e
📌 Remark:
1.5 hr once a week
""",
        ),
        (
            "nanyangtuitionjobs",
            """Looking for Online Tutor
🔻 Location/Area: Online Tuition
Lesson Per Week: Once a week
Duration Per Lesson: 1.5h
""",
        ),
        (
            "PTHTassignments",
            """Subject: Primary Math
Mode: Zoom
Frequency: 1.5 Hr, 1x A Week
Rate: $45/hr
""",
        ),
        (
            "TutorNowAssignments",
            """New Assignment
Lesson mode: Google Meet
Schedule: Sunday morning
Rate: $50/hr
""",
        ),
        (
            "sgTuitions",
            """Assignment
Platform: Teams
Timing: Tuesday evening
Frequency: Once a week
""",
        ),
    ],
)
def test_live_online_address_failure_patterns_infer_online_and_validate(agency, raw_text):
    """Regression cases mined from failed missing_address_or_postal rows."""

    parsed = {
        "assignment_code": f"regression-{agency}",
        "learning_mode": {"mode": None, "raw_text": None},
        "address": None,
        "lesson_schedule": ["Once a week"],
    }

    enriched, (ok, errors) = _enrich_and_validate(parsed, raw_text)

    assert ok is True
    assert "missing_address_or_postal" not in errors
    assert enriched["learning_mode"]["mode"] == "Online"
