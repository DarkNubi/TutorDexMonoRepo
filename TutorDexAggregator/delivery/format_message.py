from __future__ import annotations

from typing import Any, Dict

from agency_registry import get_agency_display_name

from delivery.config import _CFG
from delivery.format_utils import (
    _escape,
    _freshness_tier,
    _join_text,
    _truncate_middle,
)

def build_message_text(
    payload: Dict[str, Any],
    *,
    include_clicks: bool = True,
    clicks: int = 0,
    distance_km: Optional[float] = None,
    postal_coords_estimated: bool = False,
) -> str:
    """Build formatted message text for Telegram.
    
    When distance_km is provided, this is treated as a DM (no freshness, distance shown).
    When distance_km is None, this is treated as a broadcast (freshness shown, no distance).
    
    Args:
        payload: Assignment payload
        include_clicks: Whether to include click count (deprecated, unused)
        clicks: Number of clicks (deprecated, unused)
        distance_km: Distance to assignment location in kilometers (for DMs)
        postal_coords_estimated: Whether the distance is calculated from estimated postal code
    """
    parsed = payload.get('parsed') or {}
    academic_raw = _escape(_join_text(parsed.get("academic_display_text")))
    assignment_code = _escape(_join_text(parsed.get('assignment_code')))
    address = _escape(_join_text(parsed.get('address')))
    nearest_mrt = _escape(_join_text(parsed.get('nearest_mrt')))
    postal = _escape(_join_text(parsed.get("postal_code")))
    postal_estimated = _escape(_join_text(parsed.get("postal_code_estimated")))

    # v2 schema: lesson_schedule is an optional list of raw schedule snippets (authoritative-as-listed).
    lesson_schedule_lines: list[str] = []
    if isinstance(parsed.get("lesson_schedule"), list):
        for item in parsed.get("lesson_schedule") or []:
            if isinstance(item, str) and item.strip():
                lesson_schedule_lines.append(_escape(item.strip()))

    start_date = _escape(_join_text(parsed.get("start_date")))

    time_note_lines: list[str] = []
    if isinstance(parsed.get("time_availability"), dict):
        note = (parsed.get("time_availability") or {}).get("note")
        if isinstance(note, str) and note.strip():
            for ln in note.splitlines():
                s = ln.strip()
                if s:
                    time_note_lines.append(_escape(s))

    rate_line = ""
    if isinstance(parsed.get("rate"), dict):
        r = parsed.get("rate") or {}
        raw_rate = r.get("raw_text")
        if isinstance(raw_rate, str) and raw_rate.strip():
            rate_line = _escape(raw_rate.strip())
        else:
            rmin = r.get("min")
            rmax = r.get("max")
            try:
                if rmin is not None or rmax is not None:
                    if rmin is None:
                        rate_line = f"{float(rmax):.0f}"
                    elif rmax is None:
                        rate_line = f"{float(rmin):.0f}"
                    else:
                        rate_line = f"{float(rmin):.0f}-{float(rmax):.0f}"
            except Exception:
                rate_line = ""
    remarks = _escape(parsed.get('additional_remarks'))

    max_remarks = int(_CFG.broadcast_max_remarks_len)
    if remarks and len(remarks) > max_remarks:
        remarks = _escape(_truncate_middle(html.unescape(remarks), max_remarks))

    lines = []

    # Determine if this is a DM (has distance) or broadcast
    is_dm = distance_km is not None

    # Prefer a curated display name by channel ref; fall back to channel_title for non-Telegram sources.
    chat_ref = payload.get("channel_link") or payload.get("channel_username") or ""
    agency = get_agency_display_name(chat_ref, default="")
    if not agency:
        agency = str(payload.get("channel_title") or "").strip() or "Agency"

    # 1. Academic display text (MOST IMPORTANT - shows in notification)
    if academic_raw:
        lines.append(f"<b>{academic_raw}</b>")
    else:
        lines.append("<b>Tuition Assignment</b>")

    # 2. Rate (HIGH PRIORITY - tutors need to know pay immediately)
    if rate_line:
        lines.append(f"💰 {rate_line}")

    # 3. Distance (DM ONLY - personalized info, very important)
    if is_dm:
        try:
            km = float(distance_km)
        except Exception:
            km = None
        lm = parsed.get("learning_mode")
        if isinstance(lm, dict):
            learning_mode = str(lm.get("mode") or lm.get("raw_text") or "").strip().lower()
        else:
            learning_mode = str(lm or "").strip().lower()
        if km is not None and km >= 0 and learning_mode != "online":
            distance_text = f"~{km:.1f} km"
            if postal_coords_estimated:
                distance_text += " (estimated)"
            lines.append(f"📏 Distance: {distance_text}")

    # 4. Location (address and MRT)
    if address:
        lines.append(f"📍 {address}")
    if nearest_mrt:
        lines.append(f"🚇 {nearest_mrt}")
    if postal:
        lines.append(f"Postal: {postal}")
    elif postal_estimated:
        lines.append(f"Postal (estimated): {postal_estimated}")

    # 5. Freshness (BROADCAST ONLY - can't update DMs due to rate limits)
    if not is_dm:
        emoji, freshness_label = _freshness_tier(payload)
        if emoji:
            lines.append(f"{emoji} {freshness_label}")

    # 6. Start date
    if start_date:
        lines.append(f"🗓️ {start_date}")

    # 7. Lesson schedule (raw snippets)
    for item in lesson_schedule_lines:
        lines.append(f"📆 {item}")

    # 8. Time availability note (multi-line)
    for item in time_note_lines:
        lines.append(f"🕒 {item}")

    # 9. Assignment code (reference for communication)
    if assignment_code:
        lines.append(f"🆔 {assignment_code}")

    # 10. Remarks
    if remarks:
        lines.append(f"📝 {remarks}")

    # 11. Source line (always preceded by blank line for separation)
    channel = _escape(payload.get('channel_title') or payload.get('channel_username') or payload.get('channel_id'))
    source_parts: list[str] = []
    if agency:
        source_parts.append(agency)
    if channel and channel not in source_parts:
        source_parts.append(channel)
    if source_parts:
        lines.append("")  # Blank line before Source
        lines.append(f"🏷️ Source: {' | '.join(source_parts)}")

    # Do not include raw text excerpt or message id in the broadcast

    # Links + CTA hint
    footer_lines: list[str] = []
    footer = "\n".join(footer_lines).strip()

    max_len = int(_CFG.broadcast_max_message_len)

    # Try to keep within Telegram limits without breaking HTML tags.
    # Prune less important fields first (in this order):
    # 1. Remarks (📝), 2. Source (🏷️), 3. Time notes (🕒), 4. Schedule (📆), 5. Assignment code (🆔)
    # Non-prunable high-priority fields: academic text, rate (💰), location (📍/🚇), distance (📏), start date (🗓️)
    prunable_prefixes = ('📝 ', '🏷️ Source: ', '🕒 ', '📆 ', '🆔 ')
    while True:
        candidate = '\n'.join(lines + ([footer] if footer else []))
        if len(candidate) <= max_len:
            return candidate

        removed = False
        for idx in range(len(lines) - 1, -1, -1):
            if lines[idx].startswith(prunable_prefixes):
                lines.pop(idx)
                removed = True
                break
        if removed:
            continue

        # If we still exceed, drop footer first, then hard truncate the plain text part.
        if footer:
            footer = ''
            continue

        hard = '\n'.join(lines)
        if len(hard) <= max_len:
            return hard
        return _truncate_middle(hard, max_len)

