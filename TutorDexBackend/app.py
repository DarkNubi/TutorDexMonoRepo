import os
import time
import uuid
import logging
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from TutorDexBackend.redis_store import TutorStore
from TutorDexBackend.matching import match_from_payload
from TutorDexBackend.supabase_store import SupabaseStore
from TutorDexBackend.firebase_auth import verify_bearer_token
from TutorDexBackend.logging_setup import setup_logging


setup_logging()
logger = logging.getLogger("tutordex_backend")

app = FastAPI(title="TutorDex Backend", version="0.1.0")
store = TutorStore()
sb = SupabaseStore()

_cors_origins = (os.environ.get("CORS_ALLOW_ORIGINS") or "*").strip()
origins = ["*"] if _cors_origins == "*" else [o.strip() for o in _cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def _startup_log() -> None:
    logger.info(
        "startup",
        extra={
            "auth_required": _auth_required(),
            "supabase_enabled": sb.enabled(),
            "redis_prefix": getattr(getattr(store, "cfg", None), "prefix", None),
        },
    )

def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    request_id = (
        request.headers.get("x-request-id")
        or request.headers.get("X-Request-Id")
        or str(uuid.uuid4())
    )
    start = time.perf_counter()
    status_code = 500

    try:
        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        status_code = getattr(response, "status_code", 200) or 200
        return response
    except Exception:
        logger.exception(
            "http_exception",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
            },
        )
        raise
    finally:
        latency_ms = (time.perf_counter() - start) * 1000.0
        client_ip = getattr(getattr(request, "client", None), "host", None)
        uid = getattr(getattr(request, "state", None), "uid", None)
        logger.info(
            "http_request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": status_code,
                "latency_ms": round(latency_ms, 2),
                "client_ip": client_ip,
                "uid": uid,
            },
        )


class TutorUpsert(BaseModel):
    chat_id: Optional[str] = Field(None, description="Telegram chat id to DM (required to receive DMs)")
    subjects: Optional[List[str]] = None
    levels: Optional[List[str]] = None
    subject_pairs: Optional[List[Dict[str, str]]] = None
    assignment_types: Optional[List[str]] = None
    tutor_kinds: Optional[List[str]] = None
    learning_modes: Optional[List[str]] = None
    teaching_locations: Optional[List[str]] = None
    contact_phone: Optional[str] = None
    contact_telegram_handle: Optional[str] = None
    preferred_contact_modes: Optional[List[str]] = None


class MatchPayloadRequest(BaseModel):
    payload: Dict[str, Any]


class TelegramLinkCodeRequest(BaseModel):
    tutor_id: str
    ttl_seconds: Optional[int] = 600


class TelegramClaimRequest(BaseModel):
    code: str
    chat_id: str


class AnalyticsEventRequest(BaseModel):
    event_type: str
    assignment_external_id: Optional[str] = None
    agency_name: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True}


@app.get("/health/redis")
def health_redis() -> Dict[str, Any]:
    try:
        # `store.r` is a redis.Redis client (decode_responses=True)
        pong = bool(store.r.ping())
        return {"ok": pong}
    except Exception as e:
        logger.warning("health_redis_failed error=%s", e)
        return {"ok": False, "error": str(e)}


@app.get("/health/supabase")
def health_supabase() -> Dict[str, Any]:
    if not sb.enabled():
        return {"ok": False, "skipped": True, "reason": "supabase_disabled"}

    try:
        # Cheap PostgREST query to validate connectivity and auth.
        resp = sb.client.get("assignments?select=id&limit=1", timeout=10)  # type: ignore[union-attr]
        ok = resp.status_code < 400
        return {"ok": ok, "status_code": resp.status_code}
    except Exception as e:
        logger.warning("health_supabase_failed error=%s", e)
        return {"ok": False, "error": str(e)}


@app.get("/health/full")
def health_full() -> Dict[str, Any]:
    base = health()
    redis_h = health_redis()
    supabase_h = health_supabase()
    ok = bool(base.get("ok")) and bool(redis_h.get("ok")) and (bool(supabase_h.get("ok")) or bool(supabase_h.get("skipped")))
    return {"ok": ok, "base": base, "redis": redis_h, "supabase": supabase_h}


def _auth_required() -> bool:
    return str(os.environ.get("AUTH_REQUIRED") or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _admin_key() -> str:
    return (os.environ.get("ADMIN_API_KEY") or "").strip()


def _require_admin(request: Request) -> None:
    key = _admin_key()
    if not key:
        return
    provided = (request.headers.get("x-api-key") or request.headers.get("X-Api-Key") or "").strip()
    if provided != key:
        raise HTTPException(status_code=401, detail="admin_unauthorized")


def _get_uid_from_request(request: Request) -> Optional[str]:
    header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if not header:
        return None
    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    decoded = verify_bearer_token(parts[1])
    if not decoded:
        return None
    return decoded.get("uid")


def _require_uid(request: Request) -> str:
    uid = _get_uid_from_request(request)
    if uid:
        try:
            request.state.uid = uid
        except Exception:
            pass
        return uid
    if _auth_required():
        raise HTTPException(status_code=401, detail="unauthorized")
    raise HTTPException(status_code=401, detail="unauthorized_or_auth_disabled")


@app.put("/tutors/{tutor_id}")
def upsert_tutor(request: Request, tutor_id: str, req: TutorUpsert) -> Dict[str, Any]:
    _require_admin(request)
    return store.upsert_tutor(
        tutor_id,
        chat_id=req.chat_id,
        subjects=req.subjects,
        levels=req.levels,
        subject_pairs=getattr(req, "subject_pairs", None),
        assignment_types=req.assignment_types,
        tutor_kinds=req.tutor_kinds,
        learning_modes=req.learning_modes,
        teaching_locations=req.teaching_locations,
        contact_phone=req.contact_phone,
        contact_telegram_handle=req.contact_telegram_handle,
        preferred_contact_modes=req.preferred_contact_modes,
    )


@app.get("/tutors/{tutor_id}")
def get_tutor(request: Request, tutor_id: str) -> Dict[str, Any]:
    _require_admin(request)
    tutor = store.get_tutor(tutor_id)
    if not tutor:
        raise HTTPException(status_code=404, detail="tutor_not_found")
    return tutor


@app.delete("/tutors/{tutor_id}")
def delete_tutor(request: Request, tutor_id: str) -> Dict[str, Any]:
    _require_admin(request)
    store.delete_tutor(tutor_id)
    return {"ok": True}


@app.post("/match/payload")
def match_payload(request: Request, req: MatchPayloadRequest) -> Dict[str, Any]:
    _require_admin(request)
    results = match_from_payload(store, req.payload)
    return {
        "ok": True,
        "count": len(results),
        "matches": [
            {"tutor_id": r.tutor_id, "chat_id": r.chat_id, "score": r.score, "reasons": r.reasons} for r in results
        ],
        "chat_ids": [r.chat_id for r in results],
    }


@app.get("/me")
def me(request: Request) -> Dict[str, Any]:
    uid = _require_uid(request)
    return {"ok": True, "uid": uid}


@app.get("/me/tutor")
def me_get_tutor(request: Request) -> Dict[str, Any]:
    uid = _require_uid(request)
    tutor = store.get_tutor(uid) or {"tutor_id": uid}

    if sb.enabled():
        user_id = sb.upsert_user(firebase_uid=uid, email=None, name=None)
        if user_id:
            prefs = sb.get_preferences(user_id=user_id)
            if prefs:
                tutor = dict(tutor)
                tutor.update(
                    {
                        "subjects": prefs.get("subjects") or tutor.get("subjects") or [],
                        "levels": prefs.get("levels") or tutor.get("levels") or [],
                        "subject_pairs": prefs.get("subject_pairs") or tutor.get("subject_pairs") or [],
                        "assignment_types": prefs.get("assignment_types") or tutor.get("assignment_types") or [],
                        "tutor_kinds": prefs.get("tutor_kinds") or tutor.get("tutor_kinds") or [],
                        "learning_modes": prefs.get("learning_modes") or tutor.get("learning_modes") or [],
                        "updated_at": prefs.get("updated_at") or tutor.get("updated_at"),
                    }
                )

    return tutor


@app.put("/me/tutor")
def me_upsert_tutor(request: Request, req: TutorUpsert) -> Dict[str, Any]:
    uid = _require_uid(request)

    store.upsert_tutor(
        uid,
        chat_id=req.chat_id,
        subjects=req.subjects,
        levels=req.levels,
        subject_pairs=req.subject_pairs,
        assignment_types=req.assignment_types,
        tutor_kinds=req.tutor_kinds,
        learning_modes=req.learning_modes,
        teaching_locations=req.teaching_locations,
        contact_phone=req.contact_phone,
        contact_telegram_handle=req.contact_telegram_handle,
        preferred_contact_modes=req.preferred_contact_modes,
    )

    if sb.enabled():
        user_id = sb.upsert_user(firebase_uid=uid, email=None, name=None)
        if user_id:
            sb.upsert_preferences(
                user_id=user_id,
                prefs={
                    "subjects": req.subjects,
                    "levels": req.levels,
                    "subject_pairs": req.subject_pairs,
                    "assignment_types": req.assignment_types,
                    "tutor_kinds": req.tutor_kinds,
                    "learning_modes": req.learning_modes,
                    "teaching_locations": req.teaching_locations,
                    "contact_phone": req.contact_phone,
                    "contact_telegram_handle": req.contact_telegram_handle,
                    "preferred_contact_modes": req.preferred_contact_modes,
                },
            )

    return {"ok": True, "tutor_id": uid}


@app.post("/me/telegram/link-code")
def me_telegram_link_code(request: Request) -> Dict[str, Any]:
    uid = _require_uid(request)
    return store.create_telegram_link_code(uid, ttl_seconds=600)


@app.post("/analytics/event")
def analytics_event(request: Request, req: AnalyticsEventRequest) -> Dict[str, Any]:
    uid = _require_uid(request)
    if not sb.enabled():
        return {"ok": False, "skipped": True, "reason": "supabase_disabled"}

    user_id = sb.upsert_user(firebase_uid=uid, email=None, name=None)
    assignment_id = None
    if req.assignment_external_id:
        assignment_id = sb.resolve_assignment_id(external_id=req.assignment_external_id, agency_name=req.agency_name)

    sb.insert_event(
        user_id=user_id,
        assignment_id=assignment_id,
        event_type=req.event_type,
        meta=req.meta or {"external_id": req.assignment_external_id, "agency_name": req.agency_name},
    )
    return {"ok": True}


@app.post("/telegram/link-code")
def telegram_link_code(request: Request, req: TelegramLinkCodeRequest) -> Dict[str, Any]:
    _require_admin(request)
    ttl = int(req.ttl_seconds or 600)
    ttl = max(60, min(3600, ttl))
    return store.create_telegram_link_code(req.tutor_id, ttl_seconds=ttl)


@app.post("/telegram/claim")
def telegram_claim(request: Request, req: TelegramClaimRequest) -> Dict[str, Any]:
    _require_admin(request)
    code = (req.code or "").strip()
    if not code:
        raise HTTPException(status_code=400, detail="missing_code")
    tutor_id = store.consume_telegram_link_code(code)
    if not tutor_id:
        raise HTTPException(status_code=404, detail="invalid_or_expired_code")
    return store.set_chat_id(tutor_id, req.chat_id)
