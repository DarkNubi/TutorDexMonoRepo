import os
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple, Protocol


class TutorStore(Protocol):
    def list_tutor_ids(self) -> List[str]: ...
    def get_tutor(self, tutor_id: str) -> Optional[Dict[str, Any]]: ...


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
    meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
    signals_meta = meta.get("signals") if isinstance(meta.get("signals"), dict) else None
    signals_obj = None
    if signals_meta and signals_meta.get("ok") is True and isinstance(signals_meta.get("signals"), dict):
        signals_obj = signals_meta.get("signals")

    # Hardened pipeline: deterministic match rollups live in `meta.signals`.
    subjects: Any = []
    levels: Any = []
    if isinstance(signals_obj, dict):
        subjects = signals_obj.get("subjects") or []
        levels = signals_obj.get("levels") or []

    lm_val = parsed.get("learning_mode") if isinstance(parsed, dict) else None
    if isinstance(lm_val, dict):
        learning_modes = lm_val.get("mode") or lm_val.get("raw_text")
    else:
        learning_modes = lm_val

    return {
        "subjects": subjects or [],
        "levels": levels or [],
        "types": [],
        "learning_modes": learning_modes,
        "tutor_type": [],
    }


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _learning_mode_is_online_only(payload: Dict[str, Any]) -> bool:
    parsed = payload.get("parsed") or {}
    lm_val = parsed.get("learning_mode") if isinstance(parsed, dict) else None
    if isinstance(lm_val, dict):
        lm = _norm_text(lm_val.get("mode") or lm_val.get("raw_text"))
    else:
        lm = _norm_text(lm_val)
    return lm == "online"


def _extract_assignment_coords(payload: Dict[str, Any]) -> Tuple[Optional[float], Optional[float]]:
    parsed = payload.get("parsed") or {}
    lat = _safe_float(parsed.get("postal_lat") if isinstance(parsed, dict) else None)
    lon = _safe_float(parsed.get("postal_lon") if isinstance(parsed, dict) else None)
    if lat is None:
        lat = _safe_float(payload.get("assignment_postal_lat"))
    if lon is None:
        lon = _safe_float(payload.get("assignment_postal_lon"))
    return lat, lon


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


@dataclass(frozen=True)
class MatchResult:
    tutor_id: str
    chat_id: str
    score: int
    reasons: List[str]
    distance_km: Optional[float] = None


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

    assignment_lat, assignment_lon = _extract_assignment_coords(payload)
    include_distance = (
        not _learning_mode_is_online_only(payload)
        and assignment_lat is not None
        and assignment_lon is not None
    )

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
            distance_km: Optional[float] = None
            if include_distance:
                tutor_lat = _safe_float(tutor.get("postal_lat"))
                tutor_lon = _safe_float(tutor.get("postal_lon"))
                if tutor_lat is not None and tutor_lon is not None:
                    try:
                        distance_km = _haversine_km(tutor_lat, tutor_lon, float(assignment_lat), float(assignment_lon))
                    except Exception:
                        distance_km = None

            results.append(
                MatchResult(
                    tutor_id=tutor_id,
                    chat_id=str(chat_id),
                    score=score,
                    reasons=reasons,
                    distance_km=distance_km,
                )
            )

    results.sort(key=lambda r: (r.score, r.tutor_id), reverse=True)
    return results
