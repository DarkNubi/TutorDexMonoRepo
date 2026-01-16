import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import time
from typing import Any, Dict, Optional, List

import redis

from shared.config import load_backend_config

def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _json_loads(value: Optional[str]) -> Any:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return s


def _safe_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        return float(s)
    except Exception:
        return None


def _clamp_float(value: Optional[float], *, lo: float, hi: float) -> Optional[float]:
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _as_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    if isinstance(value, (list, tuple, set)):
        out: List[str] = []
        for item in value:
            out.extend(_as_text_list(item))
        # de-dup preserve order
        seen = set()
        uniq: List[str] = []
        for x in out:
            k = x.strip()
            if not k or k in seen:
                continue
            seen.add(k)
            uniq.append(k)
        return uniq
    v = str(value).strip()
    return [v] if v else []


@dataclass(frozen=True)
class RedisConfig:
    url: str
    prefix: str = "tutordex"


def load_redis_config() -> RedisConfig:
    # Prefer the local docker-compose Redis service when running inside Docker.
    in_docker = Path("/.dockerenv").exists()
    default_url = "redis://redis:6379/0" if in_docker else "redis://localhost:6379/0"
    cfg = load_backend_config()
    return RedisConfig(
        url=str(cfg.redis_url or default_url).strip() or default_url,
        prefix=str(cfg.redis_prefix or "tutordex").strip() or "tutordex",
    )


class TutorStore:
    def __init__(self, cfg: Optional[RedisConfig] = None):
        self.cfg = cfg or load_redis_config()
        self.r = redis.Redis.from_url(self.cfg.url, decode_responses=True)
        # In-memory fallbacks for local tests/dev when Redis isn't running.
        self._mem_tutors: Dict[str, Dict[str, str]] = {}
        self._mem_tutor_ids: set[str] = set()
        self._mem_link_codes: Dict[str, tuple[str, float]] = {}

    def _now_s(self) -> float:
        return float(time.time())

    def _redis_failed(self) -> bool:
        try:
            self.r.ping()
            return False
        except Exception:
            return True

    def _tutor_key(self, tutor_id: str) -> str:
        return f"{self.cfg.prefix}:tutor:{tutor_id}"

    def _tutors_set_key(self) -> str:
        return f"{self.cfg.prefix}:tutors"

    def _tg_link_key(self, code: str) -> str:
        return f"{self.cfg.prefix}:tg_link:{code}"

    def upsert_tutor(
        self,
        tutor_id: str,
        *,
        chat_id: Optional[str] = None,
        postal_code: Optional[str] = None,
        postal_lat: Optional[float] = None,
        postal_lon: Optional[float] = None,
        dm_max_distance_km: Optional[float] = None,
        subjects: Any = None,
        levels: Any = None,
        subject_pairs: Any = None,
        assignment_types: Any = None,
        tutor_kinds: Any = None,
        learning_modes: Any = None,
        teaching_locations: Any = None,
        contact_phone: Optional[str] = None,
        contact_telegram_handle: Optional[str] = None,
        desired_assignments_per_day: Optional[int] = None,
    ) -> Dict[str, Any]:
        key = self._tutor_key(tutor_id)
        # Important: Do not overwrite existing fields when the caller omits them.
        # This prevents the website "Save Profile" from accidentally clearing `chat_id` (Telegram linking)
        # or other preferences by sending a partial payload.
        doc: Dict[str, Any] = {"tutor_id": tutor_id, "updated_at": _utc_now_iso()}
        clear_postal_coords = False

        if chat_id is not None:
            doc["chat_id"] = str(chat_id).strip()

        if postal_code is not None:
            normalized = str(postal_code).strip()
            if not normalized:
                doc["postal_code"] = ""
                clear_postal_coords = True
            else:
                doc["postal_code"] = normalized
                if postal_lat is not None and postal_lon is not None:
                    doc["postal_lat"] = str(float(postal_lat))
                    doc["postal_lon"] = str(float(postal_lon))
                else:
                    clear_postal_coords = True

        if dm_max_distance_km is not None:
            # Clamp to avoid pathological values.
            km = _clamp_float(dm_max_distance_km, lo=0.5, hi=50.0)
            if km is not None:
                doc["dm_max_distance_km"] = str(float(km))

        if subjects is not None:
            doc["subjects"] = _json_dumps(_as_text_list(subjects))
        if levels is not None:
            doc["levels"] = _json_dumps(_as_text_list(levels))
        if subject_pairs is not None:
            doc["subject_pairs"] = _json_dumps(subject_pairs or [])
        if assignment_types is not None:
            doc["assignment_types"] = _json_dumps(_as_text_list(assignment_types))
        if tutor_kinds is not None:
            doc["tutor_kinds"] = _json_dumps(_as_text_list(tutor_kinds))
        if learning_modes is not None:
            doc["learning_modes"] = _json_dumps(_as_text_list(learning_modes))
        if teaching_locations is not None:
            doc["teaching_locations"] = _json_dumps(_as_text_list(teaching_locations))
        if contact_phone is not None:
            doc["contact_phone"] = str(contact_phone).strip()
        if contact_telegram_handle is not None:
            doc["contact_telegram_handle"] = str(contact_telegram_handle).strip()
        if desired_assignments_per_day is not None:
            doc["desired_assignments_per_day"] = str(int(desired_assignments_per_day))

        try:
            pipe = self.r.pipeline()
            pipe.hset(key, mapping=doc)
            if clear_postal_coords:
                pipe.hdel(key, "postal_lat", "postal_lon")
                if postal_code is not None and not str(postal_code).strip():
                    pipe.hdel(key, "postal_code")
            pipe.sadd(self._tutors_set_key(), tutor_id)
            pipe.execute()
        except Exception:
            raw = dict(self._mem_tutors.get(tutor_id) or {})
            raw.update({k: str(v) for k, v in doc.items()})
            if clear_postal_coords:
                raw.pop("postal_lat", None)
                raw.pop("postal_lon", None)
                if postal_code is not None and not str(postal_code).strip():
                    raw.pop("postal_code", None)
            self._mem_tutors[tutor_id] = raw
            self._mem_tutor_ids.add(tutor_id)
        return {"ok": True, "tutor_id": tutor_id}

    def set_chat_id(self, tutor_id: str, chat_id: str, telegram_username: Optional[str] = None) -> Dict[str, Any]:
        key = self._tutor_key(tutor_id)
        mapping: Dict[str, Any] = {"chat_id": str(chat_id).strip(), "updated_at": _utc_now_iso()}
        if telegram_username is not None:
            u = str(telegram_username).strip().lstrip("@")
            mapping["contact_telegram_handle"] = f"@{u}" if u else ""
        try:
            self.r.hset(key, mapping=mapping)
            self.r.sadd(self._tutors_set_key(), tutor_id)
        except Exception:
            raw = dict(self._mem_tutors.get(tutor_id) or {})
            raw.update({k: str(v) for k, v in mapping.items()})
            self._mem_tutors[tutor_id] = raw
            self._mem_tutor_ids.add(tutor_id)
        return {"ok": True, "tutor_id": tutor_id}

    def create_telegram_link_code(self, tutor_id: str, *, ttl_seconds: int = 600) -> Dict[str, Any]:
        now = self._now_s()
        for _ in range(5):
            code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
            if not code:
                continue
            key = self._tg_link_key(code)
            try:
                if self.r.set(key, tutor_id, nx=True, ex=int(ttl_seconds)):
                    return {"ok": True, "code": code, "ttl_seconds": int(ttl_seconds)}
            except Exception:
                # fallback: in-memory with expiry
                existing = self._mem_link_codes.get(code)
                if existing and existing[1] > now:
                    continue
                self._mem_link_codes[code] = (str(tutor_id), now + float(ttl_seconds))
                return {"ok": True, "code": code, "ttl_seconds": int(ttl_seconds)}
        return {"ok": False, "error": "failed_to_allocate_code"}

    def consume_telegram_link_code(self, code: str) -> Optional[str]:
        key = self._tg_link_key(code)
        try:
            pipe = self.r.pipeline()
            pipe.get(key)
            pipe.delete(key)
            tutor_id, _ = pipe.execute()
            if tutor_id is None:
                return None
            return str(tutor_id)
        except Exception:
            now = self._now_s()
            v = self._mem_link_codes.pop(str(code), None)
            if not v:
                return None
            tutor_id, expires_at = v
            if float(expires_at) <= now:
                return None
            return str(tutor_id)

    def get_tutor(self, tutor_id: str) -> Optional[Dict[str, Any]]:
        key = self._tutor_key(tutor_id)
        try:
            raw = self.r.hgetall(key)
        except Exception:
            raw = dict(self._mem_tutors.get(tutor_id) or {})
        if not raw:
            return None
        
        # Parse desired_assignments_per_day with default of 10
        desired_per_day = 10
        if raw.get("desired_assignments_per_day"):
            try:
                desired_per_day = int(raw.get("desired_assignments_per_day"))
            except Exception:
                desired_per_day = 10
        
        return {
            "tutor_id": raw.get("tutor_id") or tutor_id,
            "chat_id": raw.get("chat_id"),
            "postal_code": raw.get("postal_code") or "",
            "postal_lat": _safe_float(raw.get("postal_lat")),
            "postal_lon": _safe_float(raw.get("postal_lon")),
            "dm_max_distance_km": _safe_float(raw.get("dm_max_distance_km")) or 5.0,
            "subjects": _json_loads(raw.get("subjects")) or [],
            "levels": _json_loads(raw.get("levels")) or [],
            "subject_pairs": _json_loads(raw.get("subject_pairs")) or [],
            "assignment_types": _json_loads(raw.get("assignment_types")) or _json_loads(raw.get("types")) or [],
            "tutor_kinds": _json_loads(raw.get("tutor_kinds")) or [],
            "learning_modes": _json_loads(raw.get("learning_modes")) or [],
            "teaching_locations": _json_loads(raw.get("teaching_locations")) or [],
            "contact_phone": raw.get("contact_phone") or "",
            "contact_telegram_handle": raw.get("contact_telegram_handle") or "",
            "desired_assignments_per_day": desired_per_day,
            "updated_at": raw.get("updated_at"),
        }

    def delete_tutor(self, tutor_id: str) -> bool:
        key = self._tutor_key(tutor_id)
        try:
            self.r.delete(key)
            self.r.srem(self._tutors_set_key(), tutor_id)
        except Exception:
            self._mem_tutors.pop(tutor_id, None)
            self._mem_tutor_ids.discard(tutor_id)
        return True

    def list_tutor_ids(self, *, limit: int = 5000) -> List[str]:
        try:
            ids = list(self.r.smembers(self._tutors_set_key()))
        except Exception:
            ids = list(self._mem_tutor_ids)
        return ids[:limit]
