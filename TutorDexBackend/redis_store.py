import os
import json
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

import redis


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip()


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
    return RedisConfig(
        url=_env("REDIS_URL", "redis://localhost:6379/0"),
        prefix=_env("REDIS_PREFIX", "tutordex"),
    )


class TutorStore:
    def __init__(self, cfg: Optional[RedisConfig] = None):
        self.cfg = cfg or load_redis_config()
        self.r = redis.Redis.from_url(self.cfg.url, decode_responses=True)

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
        subjects: Any = None,
        levels: Any = None,
        subject_pairs: Any = None,
        assignment_types: Any = None,
        tutor_kinds: Any = None,
        learning_modes: Any = None,
        teaching_locations: Any = None,
        contact_phone: Optional[str] = None,
        contact_telegram_handle: Optional[str] = None,
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

        pipe = self.r.pipeline()
        pipe.hset(key, mapping=doc)
        if clear_postal_coords:
            pipe.hdel(key, "postal_lat", "postal_lon")
            if postal_code is not None and not str(postal_code).strip():
                pipe.hdel(key, "postal_code")
        pipe.sadd(self._tutors_set_key(), tutor_id)
        pipe.execute()
        return {"ok": True, "tutor_id": tutor_id}

    def set_chat_id(self, tutor_id: str, chat_id: str, telegram_username: Optional[str] = None) -> Dict[str, Any]:
        key = self._tutor_key(tutor_id)
        mapping: Dict[str, Any] = {"chat_id": str(chat_id).strip(), "updated_at": _utc_now_iso()}
        if telegram_username is not None:
            u = str(telegram_username).strip().lstrip("@")
            mapping["contact_telegram_handle"] = f"@{u}" if u else ""
        self.r.hset(key, mapping=mapping)
        self.r.sadd(self._tutors_set_key(), tutor_id)
        return {"ok": True, "tutor_id": tutor_id}

    def create_telegram_link_code(self, tutor_id: str, *, ttl_seconds: int = 600) -> Dict[str, Any]:
        for _ in range(5):
            code = secrets.token_urlsafe(6).replace("-", "").replace("_", "")[:8]
            if not code:
                continue
            key = self._tg_link_key(code)
            if self.r.set(key, tutor_id, nx=True, ex=int(ttl_seconds)):
                return {"ok": True, "code": code, "ttl_seconds": int(ttl_seconds)}
        return {"ok": False, "error": "failed_to_allocate_code"}

    def consume_telegram_link_code(self, code: str) -> Optional[str]:
        key = self._tg_link_key(code)
        pipe = self.r.pipeline()
        pipe.get(key)
        pipe.delete(key)
        tutor_id, _ = pipe.execute()
        if tutor_id is None:
            return None
        return str(tutor_id)

    def get_tutor(self, tutor_id: str) -> Optional[Dict[str, Any]]:
        key = self._tutor_key(tutor_id)
        raw = self.r.hgetall(key)
        if not raw:
            return None
        return {
            "tutor_id": raw.get("tutor_id") or tutor_id,
            "chat_id": raw.get("chat_id"),
            "postal_code": raw.get("postal_code") or "",
            "postal_lat": _safe_float(raw.get("postal_lat")),
            "postal_lon": _safe_float(raw.get("postal_lon")),
            "subjects": _json_loads(raw.get("subjects")) or [],
            "levels": _json_loads(raw.get("levels")) or [],
            "subject_pairs": _json_loads(raw.get("subject_pairs")) or [],
            "assignment_types": _json_loads(raw.get("assignment_types")) or _json_loads(raw.get("types")) or [],
            "tutor_kinds": _json_loads(raw.get("tutor_kinds")) or [],
            "learning_modes": _json_loads(raw.get("learning_modes")) or [],
            "teaching_locations": _json_loads(raw.get("teaching_locations")) or [],
            "contact_phone": raw.get("contact_phone") or "",
            "contact_telegram_handle": raw.get("contact_telegram_handle") or "",
            "updated_at": raw.get("updated_at"),
        }

    def delete_tutor(self, tutor_id: str) -> bool:
        key = self._tutor_key(tutor_id)
        self.r.delete(key)
        self.r.srem(self._tutors_set_key(), tutor_id)
        return True

    def list_tutor_ids(self, *, limit: int = 5000) -> List[str]:
        ids = list(self.r.smembers(self._tutors_set_key()))
        return ids[:limit]
