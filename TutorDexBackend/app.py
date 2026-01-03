import os
import time
import uuid
import logging
import asyncio
import hashlib
import json
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from TutorDexBackend.redis_store import TutorStore
from TutorDexBackend.matching import match_from_payload
from TutorDexBackend.supabase_store import SupabaseStore
from TutorDexBackend.firebase_auth import firebase_admin_status, verify_bearer_token
from TutorDexBackend.logging_setup import setup_logging
from TutorDexBackend.geocoding import geocode_sg_postal_code, normalize_sg_postal_code
from TutorDexBackend.metrics import metrics_payload, observe_request
from TutorDexBackend.otel import setup_otel


setup_logging()
logger = logging.getLogger("tutordex_backend")
setup_otel()

app = FastAPI(title="TutorDex Backend", version="0.1.0")
store = TutorStore()
sb = SupabaseStore()


def _app_env() -> str:
    return (os.environ.get("APP_ENV") or os.environ.get("ENV") or "dev").strip().lower()


def _is_prod() -> bool:
    return _app_env() in {"prod", "production"}


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
async def _startup_log() -> None:
    # Fail fast on dangerous misconfig in production.
    if _is_prod() and not (os.environ.get("ADMIN_API_KEY") or "").strip():
        raise RuntimeError("ADMIN_API_KEY is required when APP_ENV=prod")

    logger.info(
        "startup",
        extra={
            "auth_required": _auth_required(),
            "app_env": _app_env(),
            "supabase_enabled": sb.enabled(),
            "redis_prefix": getattr(getattr(store, "cfg", None), "prefix", None),
        },
    )


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _bot_token_for_edits() -> str:
    return (os.environ.get("TRACKING_EDIT_BOT_TOKEN") or os.environ.get("GROUP_BOT_TOKEN") or "").strip()


def _client_ip(request: Request) -> str:
    xff = (request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For") or "").strip()
    if xff:
        first = xff.split(",", 1)[0].strip()
        return first or "unknown"
    return getattr(getattr(request, "client", None), "host", None) or "unknown"


def _hash_ip(ip: str) -> str:
    try:
        return hashlib.sha256(str(ip).encode("utf-8")).hexdigest()[:16]
    except Exception:
        return "unknown"


_CLICK_COOLDOWN_LOCAL: Dict[str, float] = {}
_CLICK_COOLDOWN_LOCK = asyncio.Lock()


async def _should_increment_click(request: Request, *, external_id: str) -> bool:
    cooldown_s = max(0, _env_int("CLICK_TRACKING_IP_COOLDOWN_SECONDS", 10))
    if cooldown_s <= 0:
        return True

    ip_hash = _hash_ip(_client_ip(request))
    prefix = getattr(getattr(store, "cfg", None), "prefix", None) or "tutordex"
    key = f"{prefix}:click_cd:{external_id}:{ip_hash}"

    try:
        ok = store.r.set(key, "1", nx=True, ex=int(cooldown_s))
        return bool(ok)
    except Exception:
        pass

    now = time.time()
    async with _CLICK_COOLDOWN_LOCK:
        expires_at = float(_CLICK_COOLDOWN_LOCAL.get(key) or 0.0)
        if expires_at > now:
            return False
        _CLICK_COOLDOWN_LOCAL[key] = now + float(cooldown_s)
        if len(_CLICK_COOLDOWN_LOCAL) > 5000:
            for k, exp in list(_CLICK_COOLDOWN_LOCAL.items())[:1000]:
                if float(exp) <= now:
                    _CLICK_COOLDOWN_LOCAL.pop(k, None)
    return True


async def _resolve_original_url(*, external_id: Optional[str], destination_url: Optional[str]) -> Optional[str]:
    if destination_url:
        url = destination_url.strip()
        if url:
            return url

    ext = (external_id or "").strip()
    if not ext or not sb.enabled():
        return None

    try:
        bm = sb.get_broadcast_message(external_id=ext)
    except Exception:
        bm = None
    if bm:
        url = str(bm.get("original_url") or "").strip()
        if url:
            return url
    return None


async def _telegram_answer_callback_query(*, callback_query_id: str, url: Optional[str]) -> None:
    token = _bot_token_for_edits()
    if not token or not callback_query_id:
        return

    import requests  # local import to avoid startup cost

    body: Dict[str, Any] = {"callback_query_id": callback_query_id}
    if url:
        body["url"] = url

    try:
        await asyncio.to_thread(
            lambda: requests.post(
                f"https://api.telegram.org/bot{token}/answerCallbackQuery", json=body, timeout=10
            )
        )
    except Exception:
        logger.exception("telegram_answer_callback_failed", extra={"callback_query_id": callback_query_id})

def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_traceparent(value: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    """
    Parse W3C traceparent: version-traceid-spanid-flags
    Example: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
    """
    s = (value or "").strip()
    if not s:
        return None, None
    parts = s.split("-")
    if len(parts) != 4:
        return None, None
    trace_id = parts[1].strip().lower()
    span_id = parts[2].strip().lower()
    if len(trace_id) != 32 or len(span_id) != 16:
        return None, None
    return trace_id, span_id


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    request_id = (
        request.headers.get("x-request-id")
        or request.headers.get("X-Request-Id")
        or str(uuid.uuid4())
    )
    start = time.perf_counter()
    status_code = 500
    trace_id, span_id = _parse_traceparent(request.headers.get("traceparent") or request.headers.get("Traceparent"))

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
        latency_s = time.perf_counter() - start
        latency_ms = latency_s * 1000.0
        client_ip = getattr(getattr(request, "client", None), "host", None)
        uid = getattr(getattr(request, "state", None), "uid", None)
        try:
            observe_request(method=request.method, path=request.url.path, status_code=int(status_code), latency_s=float(latency_s))
        except Exception:
            pass
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
                "trace_id": trace_id or "-",
                "span_id": span_id or "-",
            },
        )


@app.get("/metrics")
def metrics() -> Response:
    data, content_type = metrics_payload()
    return Response(content=data, media_type=content_type)


class TutorUpsert(BaseModel):
    chat_id: Optional[str] = Field(None, description="Telegram chat id to DM (required to receive DMs)")
    postal_code: Optional[str] = None
    subjects: Optional[List[str]] = None
    levels: Optional[List[str]] = None
    subject_pairs: Optional[List[Dict[str, str]]] = None
    assignment_types: Optional[List[str]] = None
    tutor_kinds: Optional[List[str]] = None
    learning_modes: Optional[List[str]] = None
    teaching_locations: Optional[List[str]] = None
    contact_phone: Optional[str] = None
    contact_telegram_handle: Optional[str] = None


class MatchPayloadRequest(BaseModel):
    payload: Dict[str, Any]


class TelegramLinkCodeRequest(BaseModel):
    tutor_id: str
    ttl_seconds: Optional[int] = 600


class TelegramClaimRequest(BaseModel):
    code: str
    chat_id: str
    telegram_username: Optional[str] = None


class AnalyticsEventRequest(BaseModel):
    event_type: str
    assignment_external_id: Optional[str] = None
    agency_name: Optional[str] = None
    meta: Optional[Dict[str, Any]] = None


class ClickTrackRequest(BaseModel):
    event_type: str
    assignment_external_id: Optional[str] = None
    destination_type: Optional[str] = None
    destination_url: Optional[str] = None
    timestamp_ms: Optional[int] = None
    meta: Optional[Dict[str, Any]] = None


class AssignmentListResponse(BaseModel):
    ok: bool = True
    total: int = 0
    items: List[Dict[str, Any]] = Field(default_factory=list)
    next_cursor_last_seen: Optional[str] = None
    next_cursor_id: Optional[int] = None
    next_cursor_distance_km: Optional[float] = None


class AssignmentFacetsResponse(BaseModel):
    ok: bool = True
    facets: Dict[str, Any] = Field(default_factory=dict)


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


def _check_url_ok(url: str, *, timeout_s: float = 2.0) -> Dict[str, Any]:
    import requests  # local import

    try:
        resp = requests.get(url, timeout=timeout_s)
        ok = resp.status_code < 400
        body = None
        try:
            body = resp.json()
        except Exception:
            body = None
        return {"ok": ok, "status_code": resp.status_code, "body": body}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.get("/health/collector")
def health_collector() -> Dict[str, Any]:
    # Binary liveness only: use metrics/logs for diagnosis.
    res = _check_url_ok("http://collector-tail:9001/health/collector")
    return {"ok": bool(res.get("ok")), "collector": res}


@app.get("/health/worker")
def health_worker() -> Dict[str, Any]:
    res = _check_url_ok("http://aggregator-worker:9002/health/worker")
    return {"ok": bool(res.get("ok")), "worker": res}


@app.get("/health/dependencies")
def health_dependencies() -> Dict[str, Any]:
    # Keep compatibility with callers expecting a dependencies endpoint.
    return health_full()


def _clean_opt_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip()
    return v or None


@app.get("/assignments", response_model=AssignmentListResponse)
def list_assignments(
    request: Request,
    limit: int = 50,
    sort: Optional[str] = None,
    cursor_last_seen: Optional[str] = None,
    cursor_id: Optional[int] = None,
    cursor_distance_km: Optional[float] = None,
    level: Optional[str] = None,
    specific_student_level: Optional[str] = None,
    subject: Optional[str] = None,
    subject_general: Optional[str] = None,
    subject_canonical: Optional[str] = None,
    agency_name: Optional[str] = None,
    learning_mode: Optional[str] = None,
    location: Optional[str] = None,
    min_rate: Optional[int] = None,
) -> AssignmentListResponse:
    """
    Public listing endpoint for the website.
    Requires DB RPC `public.list_open_assignments` (see TutorDexAggregator/supabase sqls).
    """
    _ = request
    if not sb.enabled():
        raise HTTPException(status_code=503, detail="supabase_disabled")

    lim = int(limit)
    if lim < 1:
        lim = 1
    if lim > 200:
        lim = 200

    cursor_last_seen_s = _clean_opt_str(cursor_last_seen)
    sort_s = (sort or "newest").strip().lower()
    if sort_s not in {"newest", "distance"}:
        raise HTTPException(status_code=400, detail="invalid_sort")

    if cursor_last_seen_s and cursor_id is None:
        raise HTTPException(status_code=400, detail="cursor_id_required")

    if sort_s == "distance":
        if cursor_last_seen_s and cursor_distance_km is None:
            raise HTTPException(status_code=400, detail="cursor_distance_km_required")

    tutor_lat: Optional[float] = None
    tutor_lon: Optional[float] = None
    # If we have a logged-in tutor (bearer token present), we compute `distance_km` even for `sort=newest`
    # so the UI can show distance badges without forcing distance ordering.
    uid: Optional[str] = None
    if sort_s == "distance":
        uid = _require_uid(request)
    else:
        uid = _get_uid_from_request(request)
        if uid:
            try:
                request.state.uid = uid
            except Exception:
                pass

    if uid:
        t = store.get_tutor(uid) or {}
        tutor_lat = t.get("postal_lat")
        tutor_lon = t.get("postal_lon")
        if (tutor_lat is None or tutor_lon is None) and sb.enabled():
            user_id = sb.upsert_user(firebase_uid=uid, email=None, name=None)
            if user_id:
                prefs = sb.get_preferences(user_id=user_id)
                if prefs:
                    tutor_lat = prefs.get("postal_lat") if prefs.get("postal_lat") is not None else tutor_lat
                    tutor_lon = prefs.get("postal_lon") if prefs.get("postal_lon") is not None else tutor_lon

    if sort_s == "distance" and (tutor_lat is None or tutor_lon is None):
        raise HTTPException(status_code=400, detail="postal_required_for_distance")

    result = sb.list_open_assignments_v2(
        limit=lim,
        sort=sort_s,
        tutor_lat=float(tutor_lat) if tutor_lat is not None else None,
        tutor_lon=float(tutor_lon) if tutor_lon is not None else None,
        cursor_last_seen=cursor_last_seen_s,
        cursor_id=cursor_id,
        cursor_distance_km=float(cursor_distance_km) if cursor_distance_km is not None else None,
        level=_clean_opt_str(level),
        specific_student_level=_clean_opt_str(specific_student_level),
        subject=_clean_opt_str(subject),
        subject_general=_clean_opt_str(subject_general),
        subject_canonical=_clean_opt_str(subject_canonical),
        agency_name=_clean_opt_str(agency_name),
        learning_mode=_clean_opt_str(learning_mode),
        location_query=_clean_opt_str(location),
        min_rate=int(min_rate) if min_rate is not None else None,
    )
    if not result:
        raise HTTPException(status_code=500, detail="list_assignments_failed")

    items = result.get("items") or []
    total = int(result.get("total") or 0)
    next_cursor_last_seen_out: Optional[str] = None
    next_cursor_id_out: Optional[int] = None
    next_cursor_distance_km_out: Optional[float] = None
    if items and len(items) >= lim:
        last = items[-1] or {}
        next_cursor_last_seen_out = _clean_opt_str(last.get("last_seen"))
        try:
            next_cursor_id_out = int(last.get("id")) if last.get("id") is not None else None
        except Exception:
            next_cursor_id_out = None

        if sort_s == "distance":
            try:
                # This matches DB `distance_sort_key = coalesce(distance_km, 1e9)`
                dk = last.get("distance_sort_key")
                if dk is None:
                    dk = last.get("distance_km")
                next_cursor_distance_km_out = float(dk) if dk is not None else 1e9
            except Exception:
                next_cursor_distance_km_out = 1e9

    return AssignmentListResponse(
        ok=True,
        total=total,
        items=items,
        next_cursor_last_seen=next_cursor_last_seen_out,
        next_cursor_id=next_cursor_id_out,
        next_cursor_distance_km=next_cursor_distance_km_out,
    )


@app.get("/assignments/facets", response_model=AssignmentFacetsResponse)
def assignment_facets(
    request: Request,
    level: Optional[str] = None,
    specific_student_level: Optional[str] = None,
    subject: Optional[str] = None,
    subject_general: Optional[str] = None,
    subject_canonical: Optional[str] = None,
    agency_name: Optional[str] = None,
    learning_mode: Optional[str] = None,
    location: Optional[str] = None,
    min_rate: Optional[int] = None,
) -> AssignmentFacetsResponse:
    """
    Public facets endpoint for the website.
    Requires DB RPC `public.open_assignment_facets` (see TutorDexAggregator/supabase sqls).
    """
    _ = request
    if not sb.enabled():
        raise HTTPException(status_code=503, detail="supabase_disabled")

    facets = sb.open_assignment_facets(
        level=_clean_opt_str(level),
        specific_student_level=_clean_opt_str(specific_student_level),
        subject=_clean_opt_str(subject),
        subject_general=_clean_opt_str(subject_general),
        subject_canonical=_clean_opt_str(subject_canonical),
        agency_name=_clean_opt_str(agency_name),
        learning_mode=_clean_opt_str(learning_mode),
        location_query=_clean_opt_str(location),
        min_rate=int(min_rate) if min_rate is not None else None,
    )
    if facets is None:
        raise HTTPException(status_code=500, detail="facets_failed")
    return AssignmentFacetsResponse(ok=True, facets=facets)


def _auth_required() -> bool:
    return str(os.environ.get("AUTH_REQUIRED") or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def _admin_key() -> str:
    return (os.environ.get("ADMIN_API_KEY") or "").strip()


def _require_admin(request: Request) -> None:
    key = _admin_key()
    if not key:
        # In dev, allow missing key for easier local iteration.
        if not _is_prod():
            return
        raise HTTPException(status_code=500, detail="admin_api_key_missing")
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
    header = request.headers.get("authorization") or request.headers.get("Authorization") or ""
    if not header:
        if _auth_required():
            raise HTTPException(status_code=401, detail="missing_bearer_token")
        raise HTTPException(status_code=401, detail="unauthorized_or_auth_disabled")

    parts = header.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        if _auth_required():
            raise HTTPException(status_code=401, detail="invalid_authorization_header")
        raise HTTPException(status_code=401, detail="unauthorized_or_auth_disabled")

    decoded = verify_bearer_token(parts[1])
    uid = decoded.get("uid") if decoded else None
    if uid:
        try:
            request.state.uid = uid
        except Exception:
            pass
        return uid

    if _auth_required():
        st = firebase_admin_status()
        if not st.get("enabled"):
            raise HTTPException(status_code=500, detail="auth_required_but_firebase_admin_disabled")
        if not st.get("ready"):
            raise HTTPException(status_code=503, detail="firebase_admin_init_failed")
        raise HTTPException(status_code=401, detail="invalid_bearer_token")

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
            {
                "tutor_id": r.tutor_id,
                "chat_id": r.chat_id,
                "score": r.score,
                "reasons": r.reasons,
                "distance_km": r.distance_km,
            }
            for r in results
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
                        "postal_code": prefs.get("postal_code") if prefs.get("postal_code") is not None else tutor.get("postal_code") or "",
                        "postal_lat": prefs.get("postal_lat") if prefs.get("postal_lat") is not None else tutor.get("postal_lat"),
                        "postal_lon": prefs.get("postal_lon") if prefs.get("postal_lon") is not None else tutor.get("postal_lon"),
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

    postal_code: Optional[str] = None
    postal_lat: Optional[float] = None
    postal_lon: Optional[float] = None
    if "postal_code" in getattr(req, "model_fields_set", set()):
        postal_code = normalize_sg_postal_code(req.postal_code)
        if postal_code is None:
            raise HTTPException(status_code=400, detail="invalid_postal_code")
        if postal_code:
            coords = geocode_sg_postal_code(postal_code)
            if coords:
                postal_lat, postal_lon = coords

    store.upsert_tutor(
        uid,
        chat_id=req.chat_id,
        postal_code=postal_code,
        postal_lat=postal_lat,
        postal_lon=postal_lon,
        subjects=req.subjects,
        levels=req.levels,
        subject_pairs=req.subject_pairs,
        assignment_types=req.assignment_types,
        tutor_kinds=req.tutor_kinds,
        learning_modes=req.learning_modes,
        teaching_locations=req.teaching_locations,
        contact_phone=req.contact_phone,
        contact_telegram_handle=req.contact_telegram_handle,
    )

    if sb.enabled():
        user_id = sb.upsert_user(firebase_uid=uid, email=None, name=None)
        if user_id:
            prefs: Dict[str, Any] = {
                "subjects": req.subjects,
                "levels": req.levels,
                "subject_pairs": req.subject_pairs,
                "assignment_types": req.assignment_types,
                "tutor_kinds": req.tutor_kinds,
                "learning_modes": req.learning_modes,
            }
            if "postal_code" in getattr(req, "model_fields_set", set()):
                prefs["postal_code"] = postal_code
                prefs["postal_lat"] = postal_lat
                prefs["postal_lon"] = postal_lon
            sb.upsert_preferences(
                user_id=user_id,
                prefs=prefs,
            )

    return {"ok": True, "tutor_id": uid}


@app.post("/me/telegram/link-code")
def me_telegram_link_code(request: Request) -> Dict[str, Any]:
    uid = _require_uid(request)
    return store.create_telegram_link_code(uid, ttl_seconds=600)


@app.post("/track")
async def track_click(request: Request, req: ClickTrackRequest) -> Dict[str, Any]:
    external_id = (req.assignment_external_id or "").strip()
    destination_url = await _resolve_original_url(
        external_id=external_id, destination_url=req.destination_url
    )

    tracked = False
    clicks: Optional[int] = None
    if external_id and destination_url and sb.enabled():
        try:
            should_inc = await _should_increment_click(request, external_id=external_id)
        except Exception:
            should_inc = True
        if should_inc:
            clicks = sb.increment_assignment_clicks(
                external_id=external_id, original_url=destination_url, delta=1
            )
            tracked = True

    return {
        "ok": True,
        "tracked": tracked,
        "clicks": int(clicks) if clicks is not None else None,
        "external_id": external_id or None,
    }


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

    username = (req.telegram_username or "").strip() or None
    return store.set_chat_id(tutor_id, req.chat_id, telegram_username=username)


@app.post("/telegram/callback")
async def telegram_callback(request: Request) -> Dict[str, Any]:
    try:
        update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="invalid_payload")

    cq = (update or {}).get("callback_query") or {}
    data = str(cq.get("data") or "").strip()
    if not data:
        return {"ok": False, "reason": "no_callback"}

    if not data.startswith("open:"):
        return {"ok": False, "reason": "unsupported_callback"}

    external_id = data.split(":", 1)[1].strip() if ":" in data else ""
    original_url = await _resolve_original_url(external_id=external_id, destination_url=None)

    if external_id and original_url and sb.enabled():
        try:
            if await _should_increment_click(request, external_id=external_id):
                sb.increment_assignment_clicks(
                    external_id=external_id, original_url=original_url, delta=1
                )
        except Exception:
            logger.exception("telegram_callback_increment_failed", extra={"external_id": external_id})

    await _telegram_answer_callback_query(callback_query_id=str(cq.get("id") or ""), url=original_url)

    return {"ok": True, "external_id": external_id or None, "has_url": bool(original_url)}
