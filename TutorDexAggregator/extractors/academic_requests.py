from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

try:
    from ..canonicalization.academic import canonicalize_level_token, canonicalize_specific_level, canonicalize_stream_token  # type: ignore
    from .subjects_matcher import SubjectMatch, extract_subjects  # type: ignore
    from ..taxonomy.canonicalize_subjects import canonicalize_subjects as canonicalize_subjects_v2  # type: ignore
except Exception:
    from canonicalization.academic import canonicalize_level_token, canonicalize_specific_level, canonicalize_stream_token  # type: ignore
    from extractors.subjects_matcher import SubjectMatch, extract_subjects  # type: ignore
    from taxonomy.canonicalize_subjects import canonicalize_subjects as canonicalize_subjects_v2  # type: ignore


@dataclass(frozen=True)
class Token:
    kind: str  # specific_level|level|stream|subject
    value: str
    start: int
    end: int
    matched_text: str


_SPEC_PRIMARY_RE = re.compile(r"(?i)\b(?:p\.?|pri|primary)\s*([1-6])\b")
_SPEC_SECONDARY_RE = re.compile(r"(?i)\b(?:s\.?|sec|secondary)\s*([1-5])\b")
_SPEC_JC_RE = re.compile(r"(?i)\b(?:jc|j\.?)\s*([1-2])\b")
_SPEC_K_RE = re.compile(r"(?i)\b(?:k)\s*([1-2])\b")
_SPEC_NURSERY_RE = re.compile(r"(?i)\b(?:nur(?:sery)?|n)\s*([1-2])\b")

# IB/IGCSE patterns are conservative: require explicit IB/IGCSE near the year/grade.
_IB_YEAR_RE = re.compile(r"(?i)\bib\s*(?:year\s*)?(\d{1,2})\b")
_IGCSE_GRADE_RE = re.compile(r"(?i)\bigcse\s*(?:grade|year)\s*(\d{1,2})\b")

_LEVEL_ONLY_RE = re.compile(
    r"(?i)\b("
    r"pre[-\s]?school|preschool|kindergarten|nursery|child\s*care|"
    r"pri(?:mary)?(?:\s+school)?|psle|"
    r"sec(?:ondary)?(?:\s+school)?|o[-\s]?levels?|n[-\s]?levels?|"
    r"jc|junior\s+college|a[-\s]?levels?|pre[-\s]?(?:u|uni|university)|pre[-\s]?university|"
    r"ib|international\s+baccalaureate|ib\s*dp|ibdp|ib\s*diploma|diploma\s+programme|diploma\s+program|"
    r"igcse|cambridge\s+igcse|"
    r"poly|polytechnic"
    r")\b"
)

_STREAM_RE = re.compile(
    r"(?i)\b("
    r"g\s*[1-3]|h\s*[1-3]|"
    r"express|exp|"
    r"na|nt|ip|foundation|"
    r"normal\s+(?:academic|acad|technical|tech)|"
    r"integrated\s+programme|integrated\s+program|"
    r"(?:higher|standard)\s+level|hl|sl|"
    r"sbb|subject\s+based\s+banding|"
    r"(?:arts|science|commerce)\s+stream"
    r")\b"
)


def _tokenize_levels_and_streams(text: str) -> List[Token]:
    s = str(text or "")
    out: List[Token] = []

    for m in _SPEC_PRIMARY_RE.finditer(s):
        lvl, spec = canonicalize_specific_level(kind="primary", number=m.group(1))
        if lvl and spec:
            out.append(Token("specific_level", spec, m.start(), m.end(), m.group(0)))
    for m in _SPEC_SECONDARY_RE.finditer(s):
        lvl, spec = canonicalize_specific_level(kind="secondary", number=m.group(1))
        if lvl and spec:
            out.append(Token("specific_level", spec, m.start(), m.end(), m.group(0)))
    for m in _SPEC_JC_RE.finditer(s):
        lvl, spec = canonicalize_specific_level(kind="jc", number=m.group(1))
        if lvl and spec:
            out.append(Token("specific_level", spec, m.start(), m.end(), m.group(0)))
    for m in _SPEC_K_RE.finditer(s):
        lvl, spec = canonicalize_specific_level(kind="k", number=m.group(1))
        if lvl and spec:
            out.append(Token("specific_level", spec, m.start(), m.end(), m.group(0)))
    for m in _SPEC_NURSERY_RE.finditer(s):
        lvl, spec = canonicalize_specific_level(kind="nursery", number=m.group(1))
        if lvl and spec:
            out.append(Token("specific_level", spec, m.start(), m.end(), m.group(0)))

    for m in _IB_YEAR_RE.finditer(s):
        lvl, spec = canonicalize_specific_level(kind="ib", number=m.group(1))
        if lvl and spec:
            out.append(Token("specific_level", spec, m.start(), m.end(), m.group(0)))

    for m in _IGCSE_GRADE_RE.finditer(s):
        lvl, spec = canonicalize_specific_level(kind="igcse", number=m.group(1))
        if lvl and spec:
            out.append(Token("specific_level", spec, m.start(), m.end(), m.group(0)))

    for m in _LEVEL_ONLY_RE.finditer(s):
        canon = canonicalize_level_token(m.group(1))
        if canon:
            out.append(Token("level", canon, m.start(), m.end(), m.group(0)))

    for m in _STREAM_RE.finditer(s):
        canon = canonicalize_stream_token(m.group(1))
        if canon:
            out.append(Token("stream", canon, m.start(), m.end(), m.group(0)))

    return out


def _specific_to_level(specific: str) -> Optional[str]:
    ss = str(specific or "").strip()
    if not ss:
        return None
    if ss.startswith("Primary "):
        return "Primary"
    if ss.startswith("Secondary "):
        return "Secondary"
    if ss.startswith("JC "):
        return "Junior College"
    if ss.startswith("Kindergarten "):
        return "Pre-School"
    if ss.startswith("Nursery "):
        return "Pre-School"
    if ss.startswith("IB Year "):
        return "IB"
    if ss.startswith("IGCSE "):
        return "IGCSE"
    return None


def _resolve_overlaps(tokens: List[Token]) -> List[Token]:
    # Prefer longer tokens on the same start (e.g., "Secondary 4" over "Secondary").
    ordered = sorted(tokens, key=lambda t: (t.start, -(t.end - t.start), t.kind))
    chosen: List[Token] = []
    cur_end = -1
    for t in ordered:
        if t.start < cur_end:
            continue
        chosen.append(t)
        cur_end = t.end
    return sorted(chosen, key=lambda t: (t.start, t.end))


def parse_academic_requests(
    *,
    text: str,
) -> Dict[str, Any]:
    """
    Deterministically parse academic tokens from text and build:
    - rollups (subjects/levels/specific_student_levels/streams)
    - academic_requests[] (per-slot breakdown) without guessing
    - evidence snippets/spans
    """
    s = str(text or "")
    subjects = extract_subjects(s)
    level_stream_tokens = _tokenize_levels_and_streams(s)

    tokens: List[Token] = []
    tokens.extend(level_stream_tokens)
    for sm in subjects:
        tokens.append(Token("subject", sm.canonical, sm.start, sm.end, sm.matched_text))

    tokens = _resolve_overlaps(tokens)

    rollup_subjects: List[str] = []
    rollup_levels: List[str] = []
    rollup_specific: List[str] = []
    rollup_streams: List[str] = []

    def _add_uniq(lst: List[str], v: Optional[str]) -> None:
        if not v:
            return
        key = v.lower()
        if any(x.lower() == key for x in lst):
            return
        lst.append(v)

    # Context machine
    current_level: Optional[str] = None
    current_specific: Optional[str] = None
    current_stream: Optional[str] = None

    requests: List[Dict[str, Any]] = []
    current_req: Optional[Dict[str, Any]] = None

    def _start_request(level: Optional[str], specific: Optional[str], stream: Optional[str]) -> Dict[str, Any]:
        req = {
            "level": level,
            "specific_student_level": specific,
            "stream": stream,
            "subjects": [],
        }
        requests.append(req)
        return req

    ambiguous = False

    for t in tokens:
        if t.kind == "specific_level":
            current_specific = t.value
            current_level = _specific_to_level(current_specific)
            current_stream = None
            _add_uniq(rollup_specific, current_specific)
            _add_uniq(rollup_levels, current_level)
            current_req = _start_request(current_level, current_specific, current_stream)
            continue

        if t.kind == "level":
            # If the level token is inside a specific level token we already captured, overlap resolution should have removed it.
            current_level = t.value
            current_specific = None
            current_stream = None
            _add_uniq(rollup_levels, current_level)
            current_req = _start_request(current_level, current_specific, current_stream)
            continue

        if t.kind == "stream":
            _add_uniq(rollup_streams, t.value)
            if current_req is None:
                ambiguous = True
                continue
            # If stream changes after subjects already attached, start a new request with same level/specific.
            if current_stream and current_stream != t.value and current_req.get("subjects"):
                current_stream = t.value
                current_req = _start_request(current_level, current_specific, current_stream)
            else:
                current_stream = t.value
                current_req["stream"] = current_stream
            continue

        if t.kind == "subject":
            _add_uniq(rollup_subjects, t.value)
            if current_req is None:
                ambiguous = True
                continue
            subs: List[str] = current_req.get("subjects") if isinstance(current_req.get("subjects"), list) else []
            if not any(str(x).lower() == t.value.lower() for x in subs):
                subs.append(t.value)
                current_req["subjects"] = subs
            continue

    # If no explicit levels were found but we did find specific levels (shouldn't happen), derive levels.
    for spec in list(rollup_specific):
        _add_uniq(rollup_levels, _specific_to_level(spec))

    academic_requests: Optional[List[Dict[str, Any]]] = None
    usable = [r for r in requests if isinstance(r.get("subjects"), list) and len(r.get("subjects") or []) > 0]
    if usable:
        academic_requests = usable
    else:
        academic_requests = None

    # v2 taxonomy canonicalization (stable codes) for downstream filtering.
    # This is intentionally conservative: if multiple levels appear, prefer the combined IB/IGCSE
    # bucket when both appear; otherwise pass None to avoid level-specific guessing.
    level_for_taxonomy: Optional[str] = None
    if len(rollup_levels) == 1:
        level_for_taxonomy = rollup_levels[0]
    elif "IB" in rollup_levels and "IGCSE" in rollup_levels:
        level_for_taxonomy = "IB/IGCSE"

    canon_res = canonicalize_subjects_v2(level=level_for_taxonomy, subjects=rollup_subjects)
    subjects_canonical = canon_res.get("subjects_canonical") if isinstance(canon_res, dict) else []
    subjects_general = canon_res.get("subjects_general") if isinstance(canon_res, dict) else []
    canonicalization_version = canon_res.get("canonicalization_version") if isinstance(canon_res, dict) else None
    canonicalization_debug = canon_res.get("debug") if isinstance(canon_res, dict) else None

    evidence = {
        "source_text_chars": len(s),
        "tokens": [
            {"kind": t.kind, "value": t.value, "start": t.start, "end": t.end, "text": t.matched_text}
            for t in tokens[:60]
        ],
    }

    confidence_flags = {
        "ambiguous_academic_mapping": bool(ambiguous),
    }

    return {
        "subjects": rollup_subjects,
        "subjects_canonical": subjects_canonical or [],
        "subjects_general": subjects_general or [],
        "canonicalization_version": int(canonicalization_version) if isinstance(canonicalization_version, (int, float)) else None,
        "canonicalization_debug": canonicalization_debug if isinstance(canonicalization_debug, dict) else None,
        "levels": rollup_levels,
        "specific_student_levels": rollup_specific,
        "streams": rollup_streams,
        "academic_requests": academic_requests,
        "evidence": evidence,
        "confidence_flags": confidence_flags,
    }
