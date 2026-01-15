from __future__ import annotations

import html
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from delivery.config import _CFG

def _escape(text: Optional[str]) -> str:
    if not text:
        return ''
    return html.escape(str(text))

def _coerce_hours_env(name: str, default: int) -> int:
    mapping = {
        "FRESHNESS_GREEN_HOURS": "freshness_green_hours",
        "FRESHNESS_YELLOW_HOURS": "freshness_yellow_hours",
        "FRESHNESS_ORANGE_HOURS": "freshness_orange_hours",
        "FRESHNESS_RED_HOURS": "freshness_red_hours",
    }
    field = mapping.get(str(name or "").strip().upper())
    if field:
        try:
            return max(1, int(getattr(_CFG, field)))
        except Exception:
            return max(1, int(default))
    return max(1, int(default))

def _parse_payload_date(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(float(value), tz=timezone.utc)
        except Exception:
            return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        # Accept ISO strings; normalize "Z" to "+00:00" for fromisoformat.
        s2 = s.replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s2)
        except Exception:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    return None

def _freshness_emoji(payload: Dict[str, Any]) -> str:
    dt = _parse_payload_date(payload.get("date"))
    if not dt:
        return ""
    age_h = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)

    green_h = _coerce_hours_env("FRESHNESS_GREEN_HOURS", 24)
    yellow_h = _coerce_hours_env("FRESHNESS_YELLOW_HOURS", 36)
    orange_h = _coerce_hours_env("FRESHNESS_ORANGE_HOURS", 48)
    red_h = _coerce_hours_env("FRESHNESS_RED_HOURS", 72)

    if age_h < green_h:
        return "🟢"
    if age_h < yellow_h:
        return "🟡"
    if age_h < orange_h:
        return "🟠"
    if age_h < red_h:
        return "🔴"
    return "🔴"

def _freshness_tier(payload: Dict[str, Any]) -> tuple[str, str]:
    """Return a (emoji, label) tuple describing freshness/open-likelihood."""
    dt = _parse_payload_date(payload.get("date"))
    if not dt:
        return ("", "Unknown")
    age_h = max(0.0, (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).total_seconds() / 3600.0)

    green_h = _coerce_hours_env("FRESHNESS_GREEN_HOURS", 24)
    yellow_h = _coerce_hours_env("FRESHNESS_YELLOW_HOURS", 36)
    orange_h = _coerce_hours_env("FRESHNESS_ORANGE_HOURS", 48)
    red_h = _coerce_hours_env("FRESHNESS_RED_HOURS", 72)

    if age_h < green_h:
        return ("🟢", "Likely open")
    if age_h < yellow_h:
        return ("🟡", "Probably open")
    if age_h < orange_h:
        return ("🟠", "Uncertain")
    if age_h < red_h:
        return ("🔴", "Likely closed")
    return ("🔴", "Likely closed")

def _flatten_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        out: list[str] = []
        for item in value:
            out.extend(_flatten_text_list(item))
        return out
    s = str(value).strip()
    return [s] if s else []

def _join_text(value: Any, sep: str = ", ") -> str:
    parts = _flatten_text_list(value)
    # de-dup while preserving order
    seen = set()
    uniq: list[str] = []
    for p in parts:
        if p in seen:
            continue
        seen.add(p)
        uniq.append(p)
    return sep.join(uniq)

def _format_day_key(day: str) -> str:
    d = (day or '').strip().lower()
    mapping = {
        'monday': 'Mon',
        'tuesday': 'Tue',
        'wednesday': 'Wed',
        'thursday': 'Thu',
        'friday': 'Fri',
        'saturday': 'Sat',
        'sunday': 'Sun',
    }
    return mapping.get(d, day)

def _format_time_slots_value(value: Any) -> str:
    if not value:
        return ''

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, dict):
        parts = []
        for day, slots in value.items():
            if not slots:
                continue
            if isinstance(slots, (list, tuple)):
                slots_str = ', '.join(str(s).strip() for s in slots if str(s).strip())
            else:
                slots_str = str(slots).strip()
            if slots_str:
                parts.append(f"{_format_day_key(str(day))}: {slots_str}")
        return '; '.join(parts)

    return str(value).strip()

def _truncate_middle(text: str, max_len: int) -> str:
    if max_len <= 0:
        return ''
    if len(text) <= max_len:
        return text
    if max_len <= 3:
        return text[:max_len]
    keep = max_len - 3
    head = keep // 2
    tail = keep - head
    return text[:head] + '...' + text[-tail:]

