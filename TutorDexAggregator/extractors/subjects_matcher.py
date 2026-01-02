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


@lru_cache(maxsize=2)
def _load_taxonomy() -> Dict[str, object]:
    p = _repo_root() / "taxonomy" / "subjects_taxonomy_v1.json"
    raw = p.read_text(encoding="utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        return {}
    return data


@lru_cache(maxsize=4)
def _canonical_subject_names() -> List[str]:
    """
    Canonical subject names are the keys used by the taxonomy mapping (level + subject name).
    These match the current LLM subject strings in this repo.
    """
    data = _load_taxonomy()
    mapping = data.get("mapping") if isinstance(data.get("mapping"), dict) else {}
    by_level = mapping.get("by_level_subject_name_to_codes") if isinstance(mapping.get("by_level_subject_name_to_codes"), dict) else {}
    names: List[str] = []
    for _lvl, m in by_level.items():
        if not isinstance(m, dict):
            continue
        for k in m.keys():
            s = _safe_str(k)
            if s and s not in names:
                names.append(s)
    # Prefer longer matches first to avoid matching "Chinese" inside "Higher Chinese".
    names.sort(key=lambda x: (-len(x), x.lower()))
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
    esc = esc.replace(r"\ ", r"\s+")
    esc = esc.replace(r"\/", r"\s*/\s*")
    esc = esc.replace(r"\&", r"\s*&\s*")
    esc = esc.replace(r"\-", r"[-\s]*")
    # Common in abbreviations: "E.Maths", "A.Maths", "Sci." (treat as optional separators).
    esc = esc.replace(r"\.", r"[.\s]*")
    return esc


@lru_cache(maxsize=2)
def _subject_phrase_patterns() -> List[Tuple[re.Pattern[str], str]]:
    pats: List[Tuple[re.Pattern[str], str]] = []
    for name in _canonical_subject_names():
        frag = _escape_phrase(name)
        if not frag:
            continue
        # Use word boundaries at edges to reduce false positives.
        pat = re.compile(rf"(?i)\b{frag}\b")
        pats.append((pat, name))
    return pats


def _load_subject_aliases() -> Dict[str, str]:
    """
    Subject synonym mapping for common abbreviations/variants.
    """
    try:
        # When imported as a package module (e.g., `TutorDexAggregator.extractors.*`).
        from TutorDexAggregator.taxonomy.subject_aliases_v1 import SUBJECT_ALIASES  # type: ignore

        if isinstance(SUBJECT_ALIASES, dict):
            out: Dict[str, str] = {}
            for k, v in SUBJECT_ALIASES.items():
                ks = _safe_str(k)
                vs = _safe_str(v)
                if ks and vs:
                    out[str(ks).lower()] = str(vs)
            return out
    except Exception:
        try:
            # When running from `TutorDexAggregator/` with that folder on sys.path.
            from taxonomy.subject_aliases_v1 import SUBJECT_ALIASES  # type: ignore

            if isinstance(SUBJECT_ALIASES, dict):
                out2: Dict[str, str] = {}
                for k, v in SUBJECT_ALIASES.items():
                    ks = _safe_str(k)
                    vs = _safe_str(v)
                    if ks and vs:
                        out2[str(ks).lower()] = str(vs)
                return out2
        except Exception:
            pass

    # Minimal fallback aliases (keep small).
    return {"eng": "English", "math": "Maths", "sci": "Science", "chi": "Chinese", "emath": "E Maths", "amath": "A Maths", "gp": "General Paper", "pw": "Project Work"}


@lru_cache(maxsize=2)
def _alias_patterns() -> List[Tuple[re.Pattern[str], str]]:
    aliases = _load_subject_aliases()
    items = sorted(aliases.items(), key=lambda kv: (-len(kv[0]), kv[0]))
    pats: List[Tuple[re.Pattern[str], str]] = []
    for raw_key, canonical in items:
        esc = re.escape(raw_key)
        esc = esc.replace(r"\ ", r"\s+")
        esc = esc.replace(r"\-", r"[-\s]*")
        esc = esc.replace(r"\.", r"[.\s]*")
        pat = re.compile(rf"(?i)\b{esc}\b")
        pats.append((pat, canonical))
    return pats


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
