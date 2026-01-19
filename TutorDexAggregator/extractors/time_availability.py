"""
Deterministic time-availability extraction from Telegram tuition posts.

This module is designed to REPLACE the LLM-provided `time_availability` when enabled.

Contract (matches prompt semantics):
{
  "explicit": { monday..sunday: [ "HH:MM-HH:MM" ] },
  "estimated": { monday..sunday: [ "HH:MM-HH:MM" ] },
  "note": "verbatim snippet" | null
}

Policy decisions (documented in `docs/time_availability.md`):
- "weekdays at 7:30pm" (day-set keyword + concrete time) => ESTIMATED for Mon–Fri with "19:30-19:30"
- Day ranges like "Mon-Fri" are treated as ESTIMATED even if paired with a concrete time.
- Negations (e.g. "No Sunday before 3pm") are not represented in the schema; we still emit the
  corresponding estimated window and attach a parse warning.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


DAYS: Tuple[str, ...] = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_DAY_INDEX: Dict[str, int] = {d: i for i, d in enumerate(DAYS)}


def _empty_time_availability() -> Dict[str, Any]:
    def _m() -> Dict[str, List[str]]:
        return {d: [] for d in DAYS}

    return {"explicit": _m(), "estimated": _m(), "note": None}


def _dedupe_append(target: List[str], value: str) -> None:
    v = value.strip()
    if not v:
        return
    if v in target:
        return
    target.append(v)


def _hhmm(h: int, m: int) -> str:
    return f"{int(h):02d}:{int(m):02d}"


def _to_window(start: Tuple[int, int], end: Tuple[int, int]) -> str:
    return f"{_hhmm(*start)}-{_hhmm(*end)}"


def _parse_time_hhmm(token: str) -> Optional[Tuple[int, int]]:
    """
    Parse a single time token into (hour24, minute).

    Accepts:
    - 7pm, 7:30pm, 11:45am
    - 19:30
    - 730pm, 0730pm, 1930 (treated as 19:30)
    """
    s = str(token or "").strip().lower().replace(" ", "")
    if not s:
        return None

    # 24h with colon: 19:30
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if m:
        hh, mm = int(m.group(1)), int(m.group(2))
        if 0 <= hh <= 23 and 0 <= mm <= 59:
            return hh, mm
        return None

    # am/pm with optional minutes: 7pm, 7:30pm
    m = re.fullmatch(r"(\d{1,2})(?::(\d{2}))?([ap]m)", s)
    if m:
        hh = int(m.group(1))
        mm = int(m.group(2) or "0")
        ap = m.group(3)
        if not (1 <= hh <= 12 and 0 <= mm <= 59):
            return None
        if ap == "am":
            hh24 = 0 if hh == 12 else hh
        else:
            hh24 = 12 if hh == 12 else hh + 12
        return hh24, mm

    # Compact hhmm with optional am/pm: 730pm, 1930
    m = re.fullmatch(r"(\d{3,4})([ap]m)?", s)
    if m:
        digits = m.group(1)
        ap = m.group(2)
        if len(digits) == 3:
            hh = int(digits[0])
            mm = int(digits[1:])
        else:
            hh = int(digits[:2])
            mm = int(digits[2:])
        if not (0 <= hh <= 23 and 0 <= mm <= 59):
            return None
        if ap is None:
            return hh, mm
        # Interpret as 12-hour if am/pm present.
        if not (1 <= hh <= 12):
            return None
        if ap == "am":
            hh24 = 0 if hh == 12 else hh
        else:
            hh24 = 12 if hh == 12 else hh + 12
        return hh24, mm

    return None


_DAY_TOKEN_RE = re.compile(
    r"(?i)\b(mon(?:day)?s?|tue(?:s|sday)?s?|wed(?:s|nesday)?s?|thu(?:rs|rsday)?s?|fri(?:day)?s?|sat(?:urday)?s?|sun(?:day)?s?)\b"
)

_DAY_RANGE_RE = re.compile(
    r"(?i)\b(mon(?:day)?s?|tue(?:s|sday)?s?|wed(?:s|nesday)?s?|thu(?:rs|rsday)?s?|fri(?:day)?s?|sat(?:urday)?s?|sun(?:day)?s?)\s*(?:-|to)\s*(mon(?:day)?s?|tue(?:s|sday)?s?|wed(?:s|nesday)?s?|thu(?:rs|rsday)?s?|fri(?:day)?s?|sat(?:urday)?s?|sun(?:day)?s?)\b"
)

_WEEKDAYS_RE = re.compile(r"(?i)\bweekdays?\b")
_WEEKENDS_RE = re.compile(r"(?i)\bweekends?\b")
_ALL_DAYS_RE = re.compile(r"(?i)\b(daily|every\s*day|everyday|all\s+days)\b")


def _canon_day_token(tok: str) -> Optional[str]:
    t = str(tok or "").strip().lower()
    if t.endswith("s"):
        t = t[:-1]
    if t.startswith("mon"):
        return "monday"
    if t.startswith("tue"):
        return "tuesday"
    if t.startswith("wed"):
        return "wednesday"
    if t.startswith("thu"):
        return "thursday"
    if t.startswith("fri"):
        return "friday"
    if t.startswith("sat"):
        return "saturday"
    if t.startswith("sun"):
        return "sunday"
    return None


def _expand_range(a: str, b: str) -> List[str]:
    da = _canon_day_token(a)
    db = _canon_day_token(b)
    if not da or not db:
        return []
    ia, ib = _DAY_INDEX[da], _DAY_INDEX[db]
    if ia <= ib:
        return list(DAYS[ia : ib + 1])
    # Wrap-around ranges are ambiguous in this domain; refuse.
    return []


@dataclass(frozen=True)
class _DayInfo:
    days: List[str]
    broad: bool  # weekdays/weekends
    ranged: bool  # mon-fri style range


def _extract_days(line: str) -> _DayInfo:
    s = str(line or "")
    broad = False
    ranged = False

    days: List[str] = []

    if _ALL_DAYS_RE.search(s):
        broad = True
        days.extend(list(DAYS))

    if _WEEKDAYS_RE.search(s):
        broad = True
        days.extend(["monday", "tuesday", "wednesday", "thursday", "friday"])

    if _WEEKENDS_RE.search(s):
        broad = True
        days.extend(["saturday", "sunday"])

    # Ranges like Mon-Fri, Tue to Thu (treated as estimated policy-wise).
    for m in _DAY_RANGE_RE.finditer(s):
        expanded = _expand_range(m.group(1), m.group(2))
        if expanded:
            ranged = True
            for d in expanded:
                if d not in days:
                    days.append(d)

    # Individual day tokens (Mon, Tue & Thu). Avoid double-counting when ranges already expanded.
    for m in _DAY_TOKEN_RE.finditer(s):
        d = _canon_day_token(m.group(1))
        if d and d not in days:
            days.append(d)

    # Preserve order by weekday index (stable, deterministic).
    days = sorted(days, key=lambda d: _DAY_INDEX.get(d, 999))
    return _DayInfo(days=days, broad=broad, ranged=ranged)


_TIME_RANGE_AMPM_AMPM_RE = re.compile(
    r"(?i)\b(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*(?:-|to)\s*(\d{1,2})(?::(\d{2}))?\s*([ap]m)\b"
)
_TIME_RANGE_AMPM_RE = re.compile(
    r"(?i)\b(\d{1,2})(?::(\d{2}))?\s*([ap]m)\s*(?:-|to)\s*(\d{1,2})(?::(\d{2}))?\b"
)
_TIME_RANGE_24H_RE = re.compile(r"\b(\d{1,2}):(\d{2})\s*(?:-|to)\s*(\d{1,2}):(\d{2})\b")
_TIME_RANGE_COMPACT_AMPM_RE = re.compile(r"(?i)\b(\d{3,4})\s*([ap]m)\s*(?:-|to)\s*(\d{3,4})\s*([ap]m)\b")
_TIME_RANGE_COMPACT_RE = re.compile(r"\b(\d{3,4})\s*(?:-|to)\s*(\d{3,4})\b")

_RELATIVE_RE = re.compile(
    r"(?i)\b(after|from|before)\s+(\d{1,2}(?::\d{2})?\s*[ap]m|\d{3,4}\s*[ap]m|\d{1,2}:\d{2}|\d{3,4})\b"
)

_FUZZY_RE = re.compile(r"(?i)\b(morning|afternoon|evening|night)\b")
_NOTE_HINT_RE = re.compile(r"(?i)\b(tbc|to be confirmed|flexible|tutor to propose|to be discussed)\b")

_NEGATION_NEAR_TIME_RE = re.compile(r"(?i)\b(no|not|exclude|except)\b")


@dataclass
class _Event:
    kind: str  # explicit_range|explicit_single|relative_after|relative_before|fuzzy|note
    window: Optional[str]
    span: Tuple[int, int]  # in normalized line
    evidence: str


def _events_in_line(line: str) -> List[_Event]:
    """
    Extract time-related events in a line, returning spans relative to the line.
    """
    s = str(line or "")
    out: List[_Event] = []
    covered: List[Tuple[int, int]] = []

    def _mark(span: Tuple[int, int]) -> None:
        covered.append(span)

    def _is_covered(span: Tuple[int, int]) -> bool:
        for a, b in covered:
            if not (span[1] <= a or span[0] >= b):
                return True
        return False

    # 1) Explicit time ranges (highest priority).
    for rx in (_TIME_RANGE_AMPM_AMPM_RE, _TIME_RANGE_COMPACT_AMPM_RE, _TIME_RANGE_24H_RE, _TIME_RANGE_AMPM_RE, _TIME_RANGE_COMPACT_RE):
        for m in rx.finditer(s):
            span = (m.start(), m.end())
            if _is_covered(span):
                continue

            window: Optional[str] = None
            if rx is _TIME_RANGE_AMPM_AMPM_RE:
                start = _parse_time_hhmm(f"{m.group(1)}:{m.group(2) or '00'}{m.group(3)}")
                end = _parse_time_hhmm(f"{m.group(4)}:{m.group(5) or '00'}{m.group(6)}")
                if start and end:
                    window = _to_window(start, end)
            elif rx is _TIME_RANGE_AMPM_RE:
                # Assume end uses same am/pm as start if missing.
                start = _parse_time_hhmm(f"{m.group(1)}:{m.group(2) or '00'}{m.group(3)}")
                end_tok = f"{m.group(4)}:{m.group(5) or '00'}{m.group(3)}"
                end = _parse_time_hhmm(end_tok)
                if start and end:
                    window = _to_window(start, end)
            elif rx is _TIME_RANGE_24H_RE:
                start = _parse_time_hhmm(f"{m.group(1)}:{m.group(2)}")
                end = _parse_time_hhmm(f"{m.group(3)}:{m.group(4)}")
                if start and end:
                    window = _to_window(start, end)
            elif rx is _TIME_RANGE_COMPACT_AMPM_RE:
                start = _parse_time_hhmm(f"{m.group(1)}{m.group(2)}")
                end = _parse_time_hhmm(f"{m.group(3)}{m.group(4)}")
                if start and end:
                    window = _to_window(start, end)
            elif rx is _TIME_RANGE_COMPACT_RE:
                start = _parse_time_hhmm(m.group(1))
                end = _parse_time_hhmm(m.group(2))
                if start and end:
                    window = _to_window(start, end)

            if window:
                out.append(_Event(kind="explicit_range", window=window, span=span, evidence=s[span[0] : span[1]]))
                _mark(span)

    # 2) Relative phrases (estimated only when no explicit end is given).
    for m in _RELATIVE_RE.finditer(s):
        span = (m.start(), m.end())
        if _is_covered(span):
            continue
        kw = str(m.group(1) or "").strip().lower()
        t = _parse_time_hhmm(m.group(2))
        if not t:
            continue
        if kw in {"after", "from"}:
            window = _to_window(t, (23, 0))
            out.append(_Event(kind="relative_after", window=window, span=span, evidence=s[span[0] : span[1]]))
            _mark(span)
        elif kw == "before":
            window = _to_window((8, 0), t)
            out.append(_Event(kind="relative_before", window=window, span=span, evidence=s[span[0] : span[1]]))
            _mark(span)

    # 3) Fuzzy phrases (morning/afternoon/evening/night).
    for m in _FUZZY_RE.finditer(s):
        span = (m.start(), m.end())
        if _is_covered(span):
            continue
        word = str(m.group(1) or "").strip().lower()
        fixed: Dict[str, str] = {
            "morning": "08:00-12:00",
            "afternoon": "12:00-17:00",
            "evening": "16:00-21:00",
            "night": "19:00-23:00",
        }
        window = fixed.get(word)
        if window:
            out.append(_Event(kind="fuzzy", window=window, span=span, evidence=s[span[0] : span[1]]))
            _mark(span)

    # 4) Note hints: tbc/flexible/etc. (never create windows; only note evidence).
    for m in _NOTE_HINT_RE.finditer(s):
        span = (m.start(), m.end())
        if _is_covered(span):
            continue
        out.append(_Event(kind="note", window=None, span=span, evidence=s[span[0] : span[1]]))
        _mark(span)

    # 5) Explicit single times (day + time => explicit unless broad/ranged).
    # Only add singles when they aren't part of ranges/relative already.
    single_re = re.compile(r"(?i)\b(\d{1,2}(?::\d{2})?\s*[ap]m|\d{3,4}\s*[ap]m|\d{1,2}:\d{2}|\d{3,4})\b")
    for m in single_re.finditer(s):
        span = (m.start(), m.end())
        if _is_covered(span):
            continue
        t = _parse_time_hhmm(m.group(1))
        if not t:
            continue
        window = _to_window(t, t)  # single time => start=end (no inferred duration)
        out.append(_Event(kind="explicit_single", window=window, span=span, evidence=s[span[0] : span[1]]))
        _mark(span)

    return out


def _best_effort_original(raw_text: str, normalized_substring: str) -> str:
    """
    For meta/debugging only: try to recover a raw substring; fall back to normalized.
    """
    raw = str(raw_text or "")
    needle = str(normalized_substring or "")
    if not raw or not needle:
        return needle
    try:
        idx = raw.lower().find(needle.lower())
        if idx >= 0:
            return raw[idx : idx + len(needle)]
    except Exception:
        pass
    return needle


def extract_time_availability(raw_text: str, normalized_text: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Returns:
      (time_availability_obj, meta)
    """
    raw_text = str(raw_text or "")
    normalized_text = str(normalized_text or "")

    out = _empty_time_availability()
    meta: Dict[str, Any] = {"matched_spans": [], "rules_fired": [], "parse_warnings": []}

    if not normalized_text.strip():
        return out, meta

    explicit = out["explicit"]
    estimated = out["estimated"]

    note_candidates: List[Tuple[int, int]] = []  # spans in normalized_text

    def _looks_like_timing_header(s: str) -> bool:
        return bool(re.search(r"(?i)\b(timing|available|availability|avail|preferably|preferred)\b", s or ""))

    def _split_clauses(line: str) -> List[Tuple[str, int]]:
        """
        Split a line into independent clauses for simpler day/time association.

        We split only on separators with surrounding whitespace to avoid breaking URLs like `https://...`.
        """
        s = str(line or "")
        if not s.strip():
            return []
        parts: List[Tuple[str, int]] = []
        last = 0
        for m in re.finditer(r"(?:(?<=\s)/(?=\s)|(?<=\s)\|(?=\s))", s):
            seg = s[last : m.start()]
            if seg.strip():
                parts.append((seg, last))
            last = m.end()
        tail = s[last:]
        if tail.strip():
            parts.append((tail, last))
        return parts or [(s, 0)]

    # Iterate line-by-line to keep evidence spans meaningful and conservative.
    offset = 0
    pending_days: List[str] = []
    pending_context_hint = False
    for line in normalized_text.splitlines():
        line_start = offset
        offset += len(line) + 1  # +1 for '\n'

        if not line.strip():
            continue

        header_hint = _looks_like_timing_header(line)
        line_day_info = _extract_days(line)
        line_events = _events_in_line(line)
        line_windows = [ev for ev in line_events if ev.window]

        # Carry-over: if a prior line contained only days (no windows) under a timing-ish header,
        # and the current line contains time windows but no days, apply windows to the pending days.
        if pending_days and pending_context_hint and (not line_day_info.days) and line_windows:
            for ev in line_windows:
                if not ev.window:
                    continue
                estimated_kind = ev.kind in {"relative_after", "relative_before", "fuzzy"}
                target_map = estimated if estimated_kind else explicit
                typ = "estimated" if estimated_kind else "explicit"
                for d in pending_days:
                    _dedupe_append(target_map[d], ev.window)

                s0, s1 = line_start + ev.span[0], line_start + ev.span[1]
                meta["matched_spans"].append(
                    {
                        "type": typ,
                        "days": list(pending_days),
                        "original_substring": _best_effort_original(raw_text, normalized_text[s0:s1]),
                        "normalized_substring": normalized_text[s0:s1],
                        "start_idx": int(s0),
                        "end_idx": int(s1),
                        "window": ev.window,
                    }
                )
            meta["rules_fired"].append("carry_days_to_next_line")

            pending_days = []
            pending_context_hint = False

        for clause, clause_off in _split_clauses(line):
            clause_start = line_start + clause_off
            day_info = _extract_days(clause)
            events = _events_in_line(clause)
            windows_in_line = [ev for ev in events if ev.window]

            # Always capture note hints even when no days are present.
            for ev in events:
                if ev.kind == "note":
                    s0, s1 = clause_start + ev.span[0], clause_start + ev.span[1]
                    note_candidates.append((s0, s1))
                    meta["matched_spans"].append(
                        {
                            "type": "note",
                            "days": day_info.days,
                            "original_substring": _best_effort_original(raw_text, normalized_text[s0:s1]),
                            "normalized_substring": normalized_text[s0:s1],
                            "start_idx": int(s0),
                            "end_idx": int(s1),
                        }
                    )
                    meta["rules_fired"].append("note_hint")

            # If no day mentions, never assign to a day (conservative).
            if not day_info.days:
                continue

            if _NEGATION_NEAR_TIME_RE.search(clause) and any(ev.window for ev in events):
                meta["parse_warnings"].append("negation_detected_near_time")

            # Fixed estimated ranges for weekdays/weekends when no concrete time was provided.
            # This captures posts like "Available on weekdays" without needing the LLM.
            if day_info.broad and not windows_in_line:
                full = "08:00-23:00"
                for d in day_info.days:
                    _dedupe_append(estimated[d], full)
                # Evidence: prefer the keyword span.
                kw_match = _WEEKDAYS_RE.search(clause) or _WEEKENDS_RE.search(clause)
                if kw_match:
                    s0, s1 = clause_start + kw_match.start(), clause_start + kw_match.end()
                    meta["matched_spans"].append(
                        {
                            "type": "estimated",
                            "days": day_info.days,
                            "original_substring": _best_effort_original(raw_text, normalized_text[s0:s1]),
                            "normalized_substring": normalized_text[s0:s1],
                            "start_idx": int(s0),
                            "end_idx": int(s1),
                            "window": full,
                        }
                    )
                meta["rules_fired"].append("fixed_weekday_weekend_range")

            for ev in events:
                if not ev.window:
                    continue

                # Explicit vs estimated classification.
                estimated_kind = ev.kind in {"relative_after", "relative_before", "fuzzy"}
                if day_info.broad or day_info.ranged:
                    estimated_kind = True

                target_map = estimated if estimated_kind else explicit
                typ = "estimated" if estimated_kind else "explicit"

                if ev.kind == "explicit_range":
                    meta["rules_fired"].append("explicit_range")
                elif ev.kind == "explicit_single":
                    meta["rules_fired"].append("explicit_single_start_equals_end")
                elif ev.kind in {"relative_after", "relative_before"}:
                    meta["rules_fired"].append("relative_time_rule")
                elif ev.kind == "fuzzy":
                    meta["rules_fired"].append("fixed_fuzzy_range")

                for day in day_info.days:
                    _dedupe_append(target_map[day], ev.window)

                s0, s1 = clause_start + ev.span[0], clause_start + ev.span[1]
                meta["matched_spans"].append(
                    {
                        "type": typ,
                        "days": day_info.days,
                        "original_substring": _best_effort_original(raw_text, normalized_text[s0:s1]),
                        "normalized_substring": normalized_text[s0:s1],
                        "start_idx": int(s0),
                        "end_idx": int(s1),
                        "window": ev.window,
                    }
                )

        # If this line has multiple days and exactly one window, treat it as applying to the whole line's day list.
        # This fixes formats like: "MONDAY / THURSDAY / FRIDAY - AFTER 4PM" where clause splitting would
        # otherwise attach the window to only the last day.
        if line_day_info.days and len(line_windows) == 1:
            ev = line_windows[0]
            estimated_kind = ev.kind in {"relative_after", "relative_before", "fuzzy"}
            if line_day_info.broad or line_day_info.ranged:
                estimated_kind = True
            target_map = estimated if estimated_kind else explicit

            # If any of the days are missing this window in the chosen section, add it for all days.
            needs = False
            for d in line_day_info.days:
                if ev.window not in (target_map.get(d) or []):
                    needs = True
                    break
            if needs:
                typ = "estimated" if estimated_kind else "explicit"
                for d in line_day_info.days:
                    _dedupe_append(target_map[d], ev.window)
                s0, s1 = line_start + ev.span[0], line_start + ev.span[1]
                meta["matched_spans"].append(
                    {
                        "type": typ,
                        "days": list(line_day_info.days),
                        "original_substring": _best_effort_original(raw_text, normalized_text[s0:s1]),
                        "normalized_substring": normalized_text[s0:s1],
                        "start_idx": int(s0),
                        "end_idx": int(s1),
                        "window": ev.window,
                    }
                )
                meta["rules_fired"].append("single_time_applies_to_all_days_in_line")

        # Update pending days context for a potential next-line time.
        if line_day_info.days and not line_windows:
            pending_days = list(line_day_info.days)
            pending_context_hint = bool(pending_context_hint or header_hint)
        elif line_windows:
            pending_days = []
            pending_context_hint = False
        elif header_hint and not line_day_info.days:
            # A header-only line like "Timing:" can prime the following line(s).
            pending_context_hint = True

    # "Weekdays/weekends" with no time should produce estimated full-day windows.
    # (Only when those keywords appear; day_info.broad above sets broad but we didn't create events.)
    if _WEEKDAYS_RE.search(normalized_text):
        meta["rules_fired"].append("weekdays_keyword_seen")
    if _WEEKENDS_RE.search(normalized_text):
        meta["rules_fired"].append("weekends_keyword_seen")

    # If a note hint exists, choose the earliest one as note (must be a verbatim substring).
    if note_candidates:
        s0, s1 = sorted(note_candidates, key=lambda x: (x[0], x[1]))[0]
        note = normalized_text[s0:s1].strip()
        out["note"] = note or None

    # De-dupe rules fired for cleanliness.
    meta["rules_fired"] = sorted({str(x) for x in meta.get("rules_fired") or []})
    meta["parse_warnings"] = sorted({str(x) for x in meta.get("parse_warnings") or []})

    return out, meta
