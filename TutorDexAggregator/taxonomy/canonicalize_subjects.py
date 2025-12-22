import json
import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


logger = logging.getLogger("taxonomy")

HERE = Path(__file__).resolve().parent
DEFAULT_TAXONOMY_PATH = HERE / "subjects_taxonomy_v1.json"


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def subject_taxonomy_enabled() -> bool:
    return _truthy(os.environ.get("SUBJECT_TAXONOMY_ENABLED"))


def subject_taxonomy_debug_enabled() -> bool:
    return _truthy(os.environ.get("SUBJECT_TAXONOMY_DEBUG"))


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _coerce_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for x in value:
            out.extend(_coerce_text_list(x))
        seen = set()
        uniq: List[str] = []
        for t in out:
            s = str(t).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            uniq.append(s)
        return uniq
    v = str(value).strip()
    return [v] if v else []


@lru_cache(maxsize=4)
def _load_taxonomy(path: str) -> Dict[str, Any]:
    p = Path(path)
    raw = p.read_text(encoding="utf-8", errors="replace")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("taxonomy must be a JSON object")
    return data


def _taxonomy_path() -> str:
    p = _safe_str(os.environ.get("SUBJECT_TAXONOMY_PATH"))
    if p:
        return str(Path(p))
    return str(DEFAULT_TAXONOMY_PATH)


def _resolve_level_key(level: Optional[str], mapping: Dict[str, Any]) -> Optional[str]:
    lvl = _safe_str(level)
    if not lvl:
        return None
    if lvl in mapping:
        return lvl
    if lvl in {"IGCSE", "International Baccalaureate"} and "IB/IGCSE" in mapping:
        return "IB/IGCSE"
    return None


def _build_code_to_parent(taxonomy: Dict[str, Any]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for item in taxonomy.get("canonical_subjects") or []:
        if not isinstance(item, dict):
            continue
        code = _safe_str(item.get("code"))
        parent = _safe_str(item.get("parent"))
        if code and parent:
            out[code] = parent
    return out


def canonicalize_subjects(*, level: Optional[str], subjects: Any) -> Dict[str, Any]:
    """
    Deterministically maps current LLM output (level + subjects[]) into:
    - subjects_canonical: stable codes (advanced)
    - subjects_general: parent rollups (broad)
    """
    taxonomy_path = _taxonomy_path()
    try:
        taxonomy = _load_taxonomy(taxonomy_path)
    except Exception as e:
        return {
            "ok": False,
            "error": f"taxonomy_load_failed: {e}",
            "subjects_canonical": [],
            "subjects_general": [],
            "canonicalization_version": 1,
            "debug": {"taxonomy_path": taxonomy_path},
        }

    version = taxonomy.get("version") or 1
    mapping = ((taxonomy.get("mapping") or {}).get("by_level_subject_name_to_codes")) or {}
    if not isinstance(mapping, dict):
        mapping = {}

    code_to_parent = _build_code_to_parent(taxonomy)
    level_key = _resolve_level_key(level, mapping)
    input_subjects = _coerce_text_list(subjects)

    canonical: List[str] = []
    general: List[str] = []
    unmapped: List[str] = []

    per_level = mapping.get(level_key or "") if level_key else None
    if not isinstance(per_level, dict):
        per_level = None

    for s in input_subjects:
        codes = None
        if per_level is not None:
            codes = per_level.get(s)
        if not codes and level_key not in {None, "IB/IGCSE"} and "IB/IGCSE" in mapping:
            # Defensive fallback for older rows where IB/IGCSE subjects were emitted under a different level.
            ib = mapping.get("IB/IGCSE")
            if isinstance(ib, dict):
                codes = ib.get(s)

        codes_list = _coerce_text_list(codes)
        if not codes_list:
            unmapped.append(s)
            continue

        for code in codes_list:
            if code not in canonical:
                canonical.append(code)
            parent = code_to_parent.get(code)
            if parent and parent not in general:
                general.append(parent)

    debug = {
        "taxonomy_version": int(version) if isinstance(version, (int, float)) else 1,
        "taxonomy_path": taxonomy_path,
        "level_in": _safe_str(level),
        "level_key": level_key,
        "unmapped_subjects": unmapped[:25],
    }

    return {
        "ok": True,
        "subjects_canonical": canonical,
        "subjects_general": general,
        "canonicalization_version": int(version) if isinstance(version, (int, float)) else 1,
        "debug": debug,
    }


def canonicalize_subjects_for_assignment_row(row: Dict[str, Any]) -> Tuple[List[str], List[str], int, Dict[str, Any]]:
    """
    Convenience wrapper for assignment rows built from payloads.
    """
    res = canonicalize_subjects(level=_safe_str(row.get("level")), subjects=row.get("subjects") or row.get("subject"))
    canon = _coerce_text_list(res.get("subjects_canonical"))
    general = _coerce_text_list(res.get("subjects_general"))
    ver = int(res.get("canonicalization_version") or 1)
    dbg = res.get("debug") if isinstance(res.get("debug"), dict) else {}
    if not res.get("ok"):
        dbg = {**dbg, "ok": False, "error": _safe_str(res.get("error"))}
    return canon, general, ver, dbg

