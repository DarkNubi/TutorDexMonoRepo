import os
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from TutorDexBackend.redis_store import TutorStore


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _norm_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip().lower()


def _as_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    if isinstance(value, (list, tuple, set)):
        out: List[str] = []
        for item in value:
            out.extend(_as_list(item))
        return out
    v = str(value).strip()
    return [v] if v else []


def _canonical_type(value: Any) -> str:
    t = _norm_text(value)
    if not t:
        return ""
    if "centre" in t or "center" in t:
        return "tuition centre"
    if "private" in t or "home" in t:
        return "private"
    return t


def _payload_to_query(payload: Dict[str, Any]) -> Dict[str, Any]:
    parsed = payload.get("parsed") or {}
    return {
        "subjects": parsed.get("subjects") or [],
        "levels": parsed.get("level"),
        "types": parsed.get("type"),
        "learning_modes": parsed.get("learning_mode"),
        "tutor_type": parsed.get("tutor_type"),
    }


@dataclass(frozen=True)
class MatchResult:
    tutor_id: str
    chat_id: str
    score: int
    reasons: List[str]


def score_tutor(tutor: Dict[str, Any], query: Dict[str, Any]) -> Tuple[int, List[str]]:
    reasons: List[str] = []
    score = 0

    q_subjects = {_norm_text(s) for s in _as_list(query.get("subjects")) if _norm_text(s)}
    q_levels = {_norm_text(s) for s in _as_list(query.get("levels")) if _norm_text(s)}
    q_types = {_canonical_type(s) for s in _as_list(query.get("types")) if _canonical_type(s)}
    q_modes = {_norm_text(s) for s in _as_list(query.get("learning_modes")) if _norm_text(s)}
    q_tutor_types = {_norm_text(s) for s in _as_list(query.get("tutor_type")) if _norm_text(s)}

    t_subjects = {_norm_text(s) for s in _as_list(tutor.get("subjects")) if _norm_text(s)}
    t_levels = {_norm_text(s) for s in _as_list(tutor.get("levels")) if _norm_text(s)}
    t_types = {_canonical_type(s) for s in _as_list(tutor.get("assignment_types")) if _canonical_type(s)}
    t_kinds = {_norm_text(s) for s in _as_list(tutor.get("tutor_kinds")) if _norm_text(s)}
    t_modes = {_norm_text(s) for s in _as_list(tutor.get("learning_modes")) if _norm_text(s)}

    if q_subjects and t_subjects and (q_subjects & t_subjects):
        score += 3
        reasons.append("subject")

    if q_levels and t_levels and (q_levels & t_levels):
        score += 2
        reasons.append("level")

    if q_types and t_types and (q_types & t_types):
        score += 1
        reasons.append("type")

    if q_modes and t_modes and (q_modes & t_modes):
        score += 1
        reasons.append("learning_mode")

    if q_tutor_types and t_kinds and (q_tutor_types & t_kinds):
        score += 1
        reasons.append("tutor_type")

    return score, reasons


def match_from_payload(store: TutorStore, payload: Dict[str, Any]) -> List[MatchResult]:
    query = _payload_to_query(payload)
    min_score = _env_int("MATCH_MIN_SCORE", 3)

    results: List[MatchResult] = []
    for tutor_id in store.list_tutor_ids():
        tutor = store.get_tutor(tutor_id)
        if not tutor:
            continue
        chat_id = tutor.get("chat_id")
        if not chat_id:
            continue
        score, reasons = score_tutor(tutor, query)
        if score >= min_score:
            results.append(MatchResult(tutor_id=tutor_id, chat_id=str(chat_id), score=score, reasons=reasons))

    results.sort(key=lambda r: (r.score, r.tutor_id), reverse=True)
    return results
