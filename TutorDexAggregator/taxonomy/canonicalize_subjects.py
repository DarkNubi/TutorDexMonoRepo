import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from functools import lru_cache

from shared.config import load_aggregator_config
from shared.observability.exception_handler import swallow_exception


logger = logging.getLogger("taxonomy")

HERE = Path(__file__).resolve().parent
DEFAULT_TAXONOMY_PATH = HERE / "subjects_taxonomy_v2.json"

# Allow importing the repo-root `shared/` python package when running from `TutorDexAggregator/`.
try:
    import sys

    ROOT = HERE.parents[1]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
except Exception as e:
    swallow_exception(e, context="taxonomy_loading", extra={"module": __name__})

try:
    from shared.taxonomy.subjects.canonicalizer import canonicalize_subjects as _canonicalize_subjects_v2  # type: ignore
except Exception as e:  # pragma: no cover
    _canonicalize_subjects_v2 = None  # type: ignore
    logger.warning("shared_taxonomy_import_failed error=%s", e)
@lru_cache(maxsize=1)
def _cfg():
    return load_aggregator_config()


def subject_taxonomy_enabled() -> bool:
    return bool(_cfg().subject_taxonomy_enabled)


def subject_taxonomy_debug_enabled() -> bool:
    return bool(_cfg().subject_taxonomy_debug)


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


def _taxonomy_path() -> str:
    p = _safe_str(_cfg().subject_taxonomy_path)
    if p:
        return str(Path(p))
    return str(DEFAULT_TAXONOMY_PATH)


def canonicalize_subjects(*, level: Optional[str], subjects: Any) -> Dict[str, Any]:
    """
    Deterministically maps (level + subjects[]) into v2 taxonomy codes:
    - subjects_canonical: stable codes (advanced)
    - subjects_general: general category rollups (broad)
    """
    taxonomy_path = _taxonomy_path()
    if _canonicalize_subjects_v2 is None:
        return {
            "ok": False,
            "error": "shared_taxonomy_unavailable",
            "subjects_canonical": [],
            "subjects_general": [],
            "canonicalization_version": 2,
            "debug": {"taxonomy_path": taxonomy_path},
        }

    res = _canonicalize_subjects_v2(level=level, subjects=subjects, taxonomy_path=taxonomy_path)
    # Keep output contract stable for callers inside the aggregator.
    canon = _coerce_text_list(res.get("subjects_canonical"))
    general = _coerce_text_list(res.get("subjects_general"))
    ver = int(res.get("canonicalization_version") or 2)
    dbg = res.get("debug") if isinstance(res.get("debug"), dict) else {}
    ok = bool(res.get("ok"))
    if not ok:
        return {
            "ok": False,
            "error": _safe_str(res.get("error")) or "canonicalization_failed",
            "subjects_canonical": canon,
            "subjects_general": general,
            "canonicalization_version": ver,
            "debug": {"taxonomy_path": taxonomy_path, **dbg},
        }
    return {
        "ok": True,
        "subjects_canonical": canon,
        "subjects_general": general,
        "canonicalization_version": ver,
        "debug": {"taxonomy_path": taxonomy_path, **dbg},
    }


def canonicalize_subjects_for_assignment_row(row: Dict[str, Any]) -> Tuple[List[str], List[str], int, Dict[str, Any]]:
    """
    Convenience wrapper for assignment rows built from payloads.
    """
    res = canonicalize_subjects(level=_safe_str(row.get("level")), subjects=row.get("subjects") or row.get("subject"))
    canon = _coerce_text_list(res.get("subjects_canonical"))
    general = _coerce_text_list(res.get("subjects_general"))
    ver = int(res.get("canonicalization_version") or 2)
    dbg = res.get("debug") if isinstance(res.get("debug"), dict) else {}
    if not res.get("ok"):
        dbg = {**dbg, "ok": False, "error": _safe_str(res.get("error"))}
    return canon, general, ver, dbg
