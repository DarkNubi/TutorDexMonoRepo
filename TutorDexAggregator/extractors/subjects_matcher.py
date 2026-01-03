from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


@dataclass(frozen=True)
class SubjectMatch:
    canonical: str
    start: int
    end: int
    matched_text: str
    source: str  # taxonomy|alias|custom


def _safe_str(value: object) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


_SPACE_RE = re.compile(r"\s+")
_PUNCT_TO_SPACE_RE = re.compile(r"[\\/_&.,()\\[\\]{}:;|]+")
_DROP_RE = re.compile(r"[^a-z0-9+#\\s-]+")


def _norm_label_key(value: str) -> str:
    s = str(value or "").strip().lower()
    if not s:
        return ""
    s = s.replace("–", "-").replace("—", "-")
    s = _PUNCT_TO_SPACE_RE.sub(" ", s)
    s = _DROP_RE.sub(" ", s)
    s = s.replace("-", " ")
    s = _SPACE_RE.sub(" ", s).strip()
    return s


@lru_cache(maxsize=2)
def _load_taxonomy() -> Dict[str, object]:
    p = _repo_root() / "taxonomy" / "subjects_taxonomy_v2.json"
    raw = p.read_text(encoding="utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {}
    return data


@lru_cache(maxsize=4)
def _canonical_subject_names() -> List[str]:
    """
    Match phrases are derived from taxonomy v2:
    - all configured `subject_aliases` keys (for punctuation/format robustness)
    - plus canonical subject labels (for explicit matches)
    """
    data = _load_taxonomy()
    aliases = data.get("subject_aliases") if isinstance(data.get("subject_aliases"), dict) else {}
    names: List[str] = []
    for k in aliases.keys():
        s = _safe_str(k)
        if s and s not in names:
            names.append(s)

    canon = data.get("canonical_subjects") if isinstance(data.get("canonical_subjects"), list) else []
    for item in canon:
        if not isinstance(item, dict):
            continue
        lbl = _safe_str(item.get("label"))
        if lbl and lbl not in names:
            names.append(lbl)
    # Prefer longer matches first to avoid matching "Chinese" inside "Higher Chinese".
    # Prefer longer matches first; for exact ties under case-insensitive comparison,
    # prefer "nicer" canonical casing (stable due to Python's lexicographic ordering).
    names.sort(key=lambda x: (-len(x), x.lower(), x))
    return names


def _escape_phrase(phrase: str) -> str:
    """
    Turn a canonical phrase into a regex fragment that tolerates punctuation/spacing.
    """
    p = phrase.strip()
    if not p:
        return ""
    # Escape first, then relax separators.
    esc = re.escape(p)
    # Treat whitespace in canonical phrases as a flexible separator:
    # allow dots/slashes/hyphens commonly used in abbreviations (e.g. "E.Maths", "A-Math").
    esc = esc.replace(r"\ ", r"[\s./-]+")
    esc = esc.replace(r"\/", r"\s*/\s*")
    esc = esc.replace(r"\&", r"\s*&\s*")
    esc = esc.replace(r"\-", r"[-\s]*")
    # Common in abbreviations: "E.Maths", "A.Maths", "Sci." (treat as optional separators).
    esc = esc.replace(r"\.", r"[.\s]*")
    return esc


@lru_cache(maxsize=2)
def _subject_phrase_patterns() -> List[Tuple[re.Pattern[str], str]]:
    pats: List[Tuple[re.Pattern[str], str]] = []
    norm_to_key, key_to_label = _alias_indexes()
    for name in _canonical_subject_names():
        frag = _escape_phrase(name)
        if not frag:
            continue
        # Use word boundaries at edges to reduce false positives.
        pat = re.compile(rf"(?i)\b{frag}\b")
        subject_key = norm_to_key.get(_norm_label_key(name))
        display = key_to_label.get(subject_key) if subject_key else None
        pats.append((pat, display or name))
    return pats


def _score_display_candidate(raw_alias: str) -> Tuple[int, int, int]:
    s = str(raw_alias or "").strip()
    if not s:
        return (0, 0, 0)
    has_upper = any(ch.isalpha() and ch.upper() == ch and ch.lower() != ch for ch in s)
    # Prefer non-abbreviations.
    longish = len(s) >= 6
    # Prefer more descriptive punctuation/spacing.
    has_sep = any(ch in s for ch in " /&()")
    return (1 if has_upper else 0, 1 if longish else 0, 1 if has_sep else 0)


@lru_cache(maxsize=2)
def _alias_indexes() -> Tuple[Dict[str, str], Dict[str, str]]:
    """
    Returns:
    - normalized alias -> subject_key
    - subject_key -> preferred display label (derived from the alias list)
    """
    data = _load_taxonomy()
    aliases = data.get("subject_aliases") if isinstance(data.get("subject_aliases"), dict) else {}
    display_map = data.get("subject_key_display_labels") if isinstance(data.get("subject_key_display_labels"), dict) else {}

    norm_to_key: Dict[str, str] = {}
    key_to_best: Dict[str, str] = {}
    key_to_best_score: Dict[str, Tuple[int, int, int, int, str]] = {}
    for raw_alias, key in aliases.items():
        a = _safe_str(raw_alias)
        k = _safe_str(key)
        if not a or not k:
            continue
        norm = _norm_label_key(a)
        if norm and norm not in norm_to_key:
            norm_to_key[norm] = k

        score = _score_display_candidate(a)
        # Prefer: score tuple, then longer, then lexicographically smaller.
        rank = (score[0], score[1], score[2], len(a), a)
        prev = key_to_best_score.get(k)
        if prev is None or rank > prev:
            key_to_best_score[k] = rank
            key_to_best[k] = a

    for k, v in display_map.items():
        kk = _safe_str(k)
        vv = _safe_str(v)
        if kk and vv:
            key_to_best[kk] = vv

    return norm_to_key, key_to_best


@lru_cache(maxsize=2)
def _alias_patterns() -> List[Tuple[re.Pattern[str], str]]:
    # v2 taxonomy embeds aliases directly into `_canonical_subject_names()` and patterns.
    return []


def _collect_matches(text: str, patterns: Iterable[Tuple[re.Pattern[str], str]], *, source: str) -> List[SubjectMatch]:
    out: List[SubjectMatch] = []
    s = str(text or "")
    for pat, canon in patterns:
        for m in pat.finditer(s):
            out.append(SubjectMatch(canonical=canon, start=m.start(), end=m.end(), matched_text=m.group(0), source=source))
    return out


def _resolve_overlaps(matches: List[SubjectMatch]) -> List[SubjectMatch]:
    # Sort by start asc, length desc.
    matches_sorted = sorted(matches, key=lambda m: (m.start, -(m.end - m.start), m.canonical.lower()))
    chosen: List[SubjectMatch] = []
    cur_end = -1
    for m in matches_sorted:
        if m.start < cur_end:
            continue
        chosen.append(m)
        cur_end = m.end
    # Return in document order.
    return sorted(chosen, key=lambda m: (m.start, m.end))


def extract_subjects(text: str) -> List[SubjectMatch]:
    """
    Extract canonical subject tokens from text, returning ordered non-overlapping matches.
    """
    s = str(text or "")
    if not s.strip():
        return []

    matches: List[SubjectMatch] = []
    matches.extend(_collect_matches(s, _subject_phrase_patterns(), source="taxonomy"))
    matches.extend(_collect_matches(s, _alias_patterns(), source="alias"))

    # Custom: IB English A "Language & Literature" pattern (common phrasing in posts).
    for m in re.finditer(r"(?i)\blanguage\s*&\s*literature\s*\(\s*english\s*\)", s):
        matches.append(
            SubjectMatch(
                canonical="English Literature (IB/IGCSE)",
                start=m.start(),
                end=m.end(),
                matched_text=m.group(0),
                source="custom",
            )
        )
    for m in re.finditer(r"(?i)\blanguage\s*&\s*literature\b", s):
        matches.append(SubjectMatch(canonical="English Literature (IB/IGCSE)", start=m.start(), end=m.end(), matched_text=m.group(0), source="custom"))

    if not matches:
        return []

    resolved = _resolve_overlaps(matches)
    return resolved
