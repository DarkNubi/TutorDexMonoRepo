from __future__ import annotations

import json
import re
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


HERE = Path(__file__).resolve().parent
DEFAULT_TAXONOMY_PATH = HERE / "subjects_taxonomy_v2.json"


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


_SPACE_RE = re.compile(r"\s+")
_PUNCT_TO_SPACE_RE = re.compile(r"[\\/_&.,()\\[\\]{}:;|]+")
_DROP_RE = re.compile(r"[^a-z0-9+#\\s-]+")


def normalize_subject_label(value: str) -> str:
    """
    Deterministic, punctuation-tolerant normalization:
    - lowercase
    - treat common separators/punctuation as spaces
    - keep '+' and '#' for 'C++' / 'C#'
    """
    s = str(value or "").strip().lower()
    if not s:
        return ""
    s = s.replace("–", "-").replace("—", "-")
    s = _PUNCT_TO_SPACE_RE.sub(" ", s)
    s = _DROP_RE.sub(" ", s)
    s = s.replace("-", " ")
    s = _SPACE_RE.sub(" ", s).strip()
    return s


def normalize_level_label(value: str) -> str:
    return normalize_subject_label(value)


@lru_cache(maxsize=4)
def _load_taxonomy(path: str) -> Dict[str, Any]:
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("taxonomy must be a JSON object")
    return data


@lru_cache(maxsize=4)
def _taxonomy_index(path: str) -> Tuple[Dict[str, str], Dict[str, str], Dict[str, Dict[str, List[str]]], int]:
    """
    Returns:
    - code_to_general_category
    - normalized_alias_to_subject_key
    - by_level_subject_key mapping
    - taxonomy version
    """
    taxonomy = _load_taxonomy(path)

    version = taxonomy.get("version")
    try:
        version_i = int(version)
    except Exception:
        version_i = 2

    code_to_cat: Dict[str, str] = {}
    for item in taxonomy.get("canonical_subjects") or []:
        if not isinstance(item, dict):
            continue
        code = _safe_str(item.get("code"))
        cat = _safe_str(item.get("general_category_code"))
        if code and cat:
            code_to_cat[code] = cat

    alias_to_key: Dict[str, str] = {}
    raw_aliases = taxonomy.get("subject_aliases")
    if isinstance(raw_aliases, dict):
        for raw, key in raw_aliases.items():
            rk = normalize_subject_label(str(raw))
            sk = _safe_str(key)
            if rk and sk:
                alias_to_key[rk] = sk

    mappings = taxonomy.get("mappings") if isinstance(taxonomy.get("mappings"), dict) else {}
    by_level = mappings.get("by_level_subject_key") if isinstance(mappings.get("by_level_subject_key"), dict) else {}
    by_level_subject_key: Dict[str, Dict[str, List[str]]] = {}
    for lvl, m in by_level.items():
        if not isinstance(m, dict):
            continue
        out: Dict[str, List[str]] = {}
        for k, v in m.items():
            kk = _safe_str(k)
            if not kk:
                continue
            vals: List[str] = []
            if isinstance(v, str):
                if v.strip():
                    vals = [v.strip()]
            elif isinstance(v, list):
                for item in v:
                    if isinstance(item, str) and item.strip():
                        vals.append(item.strip())
            if vals:
                out[kk] = vals
        by_level_subject_key[str(lvl)] = out

    return code_to_cat, alias_to_key, by_level_subject_key, version_i


def _resolve_level(level: Optional[str], taxonomy: Dict[str, Any]) -> Optional[str]:
    lvl = _safe_str(level)
    if not lvl:
        return None
    nl = normalize_level_label(lvl)
    aliases = taxonomy.get("level_aliases")
    if isinstance(aliases, dict):
        resolved = aliases.get(nl)
        if isinstance(resolved, str) and resolved.strip():
            return resolved.strip()
    # If already a canonical level code, keep it.
    levels = taxonomy.get("levels")
    if isinstance(levels, list) and lvl in levels:
        return lvl
    return None


def _dedupe_keep_order(items: Iterable[str]) -> List[str]:
    seen: set[str] = set()
    out: List[str] = []
    for x in items:
        s = str(x).strip()
        if not s:
            continue
        if s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def _maybe_parse_ib_math_subject_key(normalized_label: str) -> Optional[str]:
    """
    Conservative: only returns a key when AA/AI + (SL/HL|unknown) is explicitly present.
    """
    s = normalized_label
    if "math" not in s:
        return None
    if "aa" in s:
        if "hl" in s:
            return "IB_MATH_AA_HL"
        if "sl" in s:
            return "IB_MATH_AA_SL"
        return "IB_MATH_AA_UNKNOWN"
    if "ai" in s:
        if "hl" in s:
            return "IB_MATH_AI_HL"
        if "sl" in s:
            return "IB_MATH_AI_SL"
        return "IB_MATH_AI_UNKNOWN"
    return None


def canonicalize_subjects(
    *,
    level: Optional[str],
    subjects: Any,
    taxonomy_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Deterministically maps (level, subjects[]) -> stable subject codes + general rollups.

    This function never guesses advanced tracks; it uses only:
    - normalization
    - exact alias index lookups
    - level-aware mapping tables
    """
    path = str(Path(taxonomy_path).resolve()) if taxonomy_path else str(DEFAULT_TAXONOMY_PATH)
    try:
        taxonomy = _load_taxonomy(path)
    except Exception as e:
        return {
            "ok": False,
            "error": f"taxonomy_load_failed: {e}",
            "subjects_canonical": [],
            "subjects_general": [],
            "canonicalization_version": 2,
            "debug": {"taxonomy_path": path},
        }

    code_to_cat, alias_to_key, by_level, version = _taxonomy_index(path)
    level_code = _resolve_level(level, taxonomy)

    input_subjects: List[str] = []
    if subjects is None:
        input_subjects = []
    elif isinstance(subjects, str):
        s = subjects.strip()
        input_subjects = [s] if s else []
    elif isinstance(subjects, (list, tuple, set)):
        for x in subjects:
            xs = _safe_str(x)
            if xs:
                input_subjects.append(xs)
    else:
        xs = _safe_str(subjects)
        if xs:
            input_subjects = [xs]

    canonical: List[str] = []
    general: List[str] = []
    unmapped: List[str] = []
    resolved_subject_keys: List[str] = []

    lvl_map = by_level.get(level_code or "")
    any_map = by_level.get("ANY") or {}

    for raw in input_subjects:
        norm = normalize_subject_label(raw)
        if not norm:
            continue

        subject_key = alias_to_key.get(norm)
        if not subject_key:
            subject_key = _maybe_parse_ib_math_subject_key(norm)
        if not subject_key:
            unmapped.append(raw)
            continue

        resolved_subject_keys.append(subject_key)

        codes = None
        if isinstance(lvl_map, dict):
            codes = lvl_map.get(subject_key)
        if not codes and isinstance(any_map, dict):
            codes = any_map.get(subject_key)
        if not codes:
            unmapped.append(raw)
            continue

        for code in codes:
            if code not in canonical:
                canonical.append(code)
            cat = code_to_cat.get(code)
            if cat and cat not in general:
                general.append(cat)

    return {
        "ok": True,
        "subjects_canonical": canonical,
        "subjects_general": general,
        "canonicalization_version": int(version),
        "debug": {
            "taxonomy_path": path,
            "taxonomy_version": int(version),
            "level_in": _safe_str(level),
            "level_code": level_code,
            "input_subjects": input_subjects[:50],
            "resolved_subject_keys": _dedupe_keep_order(resolved_subject_keys)[:50],
            "unmapped_subjects": unmapped[:50],
        },
    }


def canonicalize_tutorcity_subject_ids(
    *,
    level_label: Optional[str],
    subject_ids: Any,
    subject_id_to_label: Dict[str, str],
    taxonomy_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    TutorCity-specific helper: IDs -> labels -> canonical codes.
    """
    ids: List[str] = []
    if subject_ids is None:
        ids = []
    elif isinstance(subject_ids, str):
        s = subject_ids.strip()
        ids = [s] if s else []
    elif isinstance(subject_ids, (list, tuple, set)):
        ids = [str(x).strip() for x in subject_ids if str(x).strip()]
    else:
        s = str(subject_ids).strip()
        ids = [s] if s else []

    labels: List[str] = []
    unmapped_ids: List[str] = []
    for sid in ids:
        lbl = subject_id_to_label.get(str(sid))
        if lbl:
            labels.append(lbl)
        else:
            unmapped_ids.append(str(sid))

    res = canonicalize_subjects(level=level_label, subjects=labels, taxonomy_path=taxonomy_path)
    dbg = res.get("debug") if isinstance(res.get("debug"), dict) else {}
    dbg = dict(dbg)
    dbg.update({"source": "tutorcity_ids", "subject_ids": ids, "subject_labels": labels, "unmapped_subject_ids": unmapped_ids})
    res["debug"] = dbg
    return res


def file_sha256(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()

