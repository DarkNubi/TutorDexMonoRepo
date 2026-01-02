"""
Lightweight contract checks for parsed assignments.

These checks are intentionally minimal to avoid blocking on optional fields;
they catch clearly incomplete outputs that will break downstream consumers.
"""

from typing import Any, Dict, List, Tuple


REQUIRED_FIELDS_V1 = ("subjects", "level")
# V2 prompt/schema no longer reliably includes `subjects` (and the prompt requires other
# fixed-shape fields like `time_availability`), so keep required fields empty here and
# rely on the schedule/address checks below.
REQUIRED_FIELDS_V2: Tuple[str, ...] = ()
# Note: Address fields are optional for online-only lessons (learning_mode == "online").
ADDRESS_FIELDS = ("address", "postal_code", "postal_code_estimated")
# At least one of these should be present to avoid empty schedules.
SCHEDULE_FIELDS = ("frequency", "duration", "time_slots", "estimated_time_slots")
V2_SCHEDULE_FIELDS = ("lesson_schedule", "time_availability")


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set)):
        return len(value) > 0
    return True


def _is_online_only(learning_mode: Any) -> bool:
    """Return True when learning_mode indicates an online-only lesson."""

    mode: Any = learning_mode
    if isinstance(learning_mode, dict):
        mode = learning_mode.get("mode") or learning_mode.get("raw_text")
    if isinstance(learning_mode, (list, tuple, set)):
        # Prefer the first non-empty string entry
        mode = None
        for item in learning_mode:
            if isinstance(item, str) and item.strip():
                mode = item
                break
        if mode is None and learning_mode:
            mode = next(iter(learning_mode))

    try:
        return str(mode).strip().lower() == "online"
    except Exception:
        return False


def _v2_has_schedule_info(data: Dict[str, Any]) -> bool:
    lesson = data.get("lesson_schedule")
    if isinstance(lesson, list):
        for item in lesson:
            if isinstance(item, str) and item.strip():
                return True
    if isinstance(lesson, dict):
        for k in ("raw_text", "lessons_per_week", "hours_per_lesson", "total_hours_per_week", "subject_breakdown"):
            if _has_value(lesson.get(k)):
                return True

    ta = data.get("time_availability")
    if isinstance(ta, dict):
        note = ta.get("note")
        if isinstance(note, str) and note.strip():
            return True

        def _has_any_slots(obj: Any) -> bool:
            if not isinstance(obj, dict):
                return False
            for day_val in obj.values():
                if isinstance(day_val, list) and any(isinstance(x, str) and x.strip() for x in day_val):
                    return True
            return False

        if _has_any_slots(ta.get("explicit")):
            return True
        if _has_any_slots(ta.get("estimated")):
            return True

    return False


def validate_parsed_assignment(parsed: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    data = parsed or {}

    # V2 schema (prompt B / system_prompt_live.txt) allows `level` to be null.
    is_v2 = isinstance(data.get("lesson_schedule"), dict) or isinstance(data.get("rate"), dict) or ("academic_display_text" in data)
    required = REQUIRED_FIELDS_V2 if is_v2 else REQUIRED_FIELDS_V1

    for field in required:
        if not _has_value(data.get(field)):
            errors.append(f"missing_{field}")

    if not _is_online_only(data.get("learning_mode")) and not any(
        _has_value(data.get(f)) for f in ADDRESS_FIELDS
    ):
        errors.append("missing_address_or_postal")

    if not any(_has_value(data.get(f)) for f in SCHEDULE_FIELDS) and not _v2_has_schedule_info(data):
        errors.append("missing_schedule_info")

    return len(errors) == 0, errors
