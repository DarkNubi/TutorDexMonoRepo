"""
Lightweight contract checks for parsed assignments.

These checks are intentionally minimal to avoid blocking on optional fields;
they catch clearly incomplete outputs that will break downstream consumers.
"""

from typing import Any, Dict, List, Tuple


REQUIRED_FIELDS = ("subjects", "level")
# Note: Address fields are optional for online-only lessons (learning_mode == "online").
ADDRESS_FIELDS = ("address", "postal_code", "postal_code_estimated")
# At least one of these should be present to avoid empty schedules.
SCHEDULE_FIELDS = ("frequency", "duration", "time_slots", "estimated_time_slots")


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


def validate_parsed_assignment(parsed: Dict[str, Any]) -> Tuple[bool, List[str]]:
    errors: List[str] = []
    data = parsed or {}

    for field in REQUIRED_FIELDS:
        if not _has_value(data.get(field)):
            errors.append(f"missing_{field}")

    if not _is_online_only(data.get("learning_mode")) and not any(
        _has_value(data.get(f)) for f in ADDRESS_FIELDS
    ):
        errors.append("missing_address_or_postal")

    if not any(_has_value(data.get(f)) for f in SCHEDULE_FIELDS):
        errors.append("missing_schedule_info")

    return len(errors) == 0, errors
