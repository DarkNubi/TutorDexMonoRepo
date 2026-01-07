import os
import time
import uuid
import logging
import asyncio
import hashlib
import json
from datetime import datetime, timedelta, timezone
from urllib.parse import quote as _url_quote
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pathlib import Path

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
    if _is_prod() and not _auth_required():
        raise RuntimeError("AUTH_REQUIRED must be true when APP_ENV=prod")
    if _is_prod():
        st = firebase_admin_status()
        if not bool(st.get("enabled")):
            raise RuntimeError("FIREBASE_ADMIN_ENABLED must be true when APP_ENV=prod and AUTH_REQUIRED=true")
        if not bool(st.get("ready")):
            raise RuntimeError(f"Firebase Admin not ready in prod (check FIREBASE_ADMIN_CREDENTIALS_PATH). status={st}")

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

_RATE_LIMIT_LOCAL: Dict[str, tuple[int, float]] = {}
_RATE_LIMIT_LOCK = asyncio.Lock()

_PUBLIC_CACHE_LOCAL: Dict[str, tuple[str, float]] = {}
_PUBLIC_CACHE_LOCK = asyncio.Lock()


def _redis_prefix() -> str:
    return getattr(getattr(store, "cfg", None), "prefix", None) or "tutordex"


def _public_assignments_limit_cap() -> int:
    # Keep public listing bounded to reduce abuse/DB load.
    return max(1, _env_int("PUBLIC_ASSIGNMENTS_LIMIT_CAP", 50))


def _public_rpm_assignments() -> int:
    # Requests per minute for anonymous /assignments.
    return max(0, _env_int("PUBLIC_RPM_ASSIGNMENTS", 60))


def _public_rpm_facets() -> int:
    # Requests per minute for anonymous /assignments/facets.
    return max(0, _env_int("PUBLIC_RPM_FACETS", 120))


def _public_cache_ttl_assignments_s() -> int:
    return max(0, _env_int("PUBLIC_CACHE_TTL_ASSIGNMENTS_SECONDS", 15))


def _public_cache_ttl_facets_s() -> int:
    return max(0, _env_int("PUBLIC_CACHE_TTL_FACETS_SECONDS", 30))


def _canonical_query_string(items: List[tuple[str, str]]) -> str:
    # Stable query ordering => stable cache keys.
    items = [(str(k), str(v)) for k, v in (items or [])]
    items.sort(key=lambda kv: (kv[0], kv[1]))
    return "&".join([f"{k}={_url_quote(v)}" for k, v in items])


def _cache_key_from_items(path: str, items: List[tuple[str, str]], *, namespace: str) -> str:
    base = f"{path}?{_canonical_query_string(items)}"
    h = hashlib.sha256(base.encode("utf-8")).hexdigest()[:24]
    return f"{_redis_prefix()}:{namespace}:{h}"


async def _public_rate_limit_or_429(request: Request, *, endpoint: str, rpm: int) -> None:
    if rpm <= 0:
        return
    ip_hash = _hash_ip(_client_ip(request))
    bucket = int(time.time() // 60)
    key = f"{_redis_prefix()}:rl:{endpoint}:{ip_hash}:{bucket}"

    try:
        n = store.r.incr(key)
        if int(n) == 1:
            store.r.expire(key, 120)
        if int(n) > int(rpm):
            raise HTTPException(status_code=429, detail="rate_limited")
        return
    except HTTPException:
        raise
    except Exception:
        pass

    # Fallback if Redis isn't available (best-effort).
    now = time.time()
    async with _RATE_LIMIT_LOCK:
        n, expires_at = _RATE_LIMIT_LOCAL.get(key, (0, 0.0))
        if float(expires_at) <= now:
            n, expires_at = 0, now + 120.0
        n += 1
        _RATE_LIMIT_LOCAL[key] = (int(n), float(expires_at))
        if int(n) > int(rpm):
            raise HTTPException(status_code=429, detail="rate_limited")


async def _public_cache_get(key: str) -> Optional[Dict[str, Any]]:
    try:
        raw = store.r.get(key)
        if raw:
            return json.loads(raw)
    except Exception:
        pass

    now = time.time()
    async with _PUBLIC_CACHE_LOCK:
        raw, exp = _PUBLIC_CACHE_LOCAL.get(key, ("", 0.0))
        if raw and float(exp) > now:
            try:
                return json.loads(raw)
            except Exception:
                return None
        if float(exp) <= now:
            _PUBLIC_CACHE_LOCAL.pop(key, None)
    return None


async def _public_cache_set(key: str, payload: Dict[str, Any], *, ttl_s: int) -> None:
    if ttl_s <= 0:
        return
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    try:
        store.r.setex(key, int(ttl_s), raw)
        return
    except Exception:
        pass

    now = time.time()
    async with _PUBLIC_CACHE_LOCK:
        _PUBLIC_CACHE_LOCAL[key] = (raw, now + float(ttl_s))
        if len(_PUBLIC_CACHE_LOCAL) > 2000:
            for k, (_, exp) in list(_PUBLIC_CACHE_LOCAL.items())[:500]:
                if float(exp) <= now:
                    _PUBLIC_CACHE_LOCAL.pop(k, None)


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


class AssignmentRow(BaseModel):
    id: int
    external_id: Optional[str] = None
    message_link: Optional[str] = None
    agency_name: Optional[str] = None
    learning_mode: Optional[str] = None
    assignment_code: Optional[str] = None
    academic_display_text: Optional[str] = None
    address: Optional[List[str]] = None
    postal_code: Optional[List[str]] = None
    postal_code_estimated: Optional[List[str]] = None
    nearest_mrt: Optional[List[str]] = None
    region: Optional[str] = None
    nearest_mrt_computed: Optional[str] = None
    nearest_mrt_computed_line: Optional[str] = None
    nearest_mrt_computed_distance_m: Optional[int] = None
    lesson_schedule: Optional[List[str]] = None
    start_date: Optional[str] = None
    time_availability_note: Optional[str] = None
    rate_min: Optional[int] = None
    rate_max: Optional[int] = None
    rate_raw_text: Optional[str] = None
    signals_subjects: Optional[List[str]] = None
    signals_levels: Optional[List[str]] = None
    signals_specific_student_levels: Optional[List[str]] = None
    subjects_canonical: Optional[List[str]] = None
    subjects_general: Optional[List[str]] = None
    canonicalization_version: Optional[int] = None
    status: Optional[str] = None
    created_at: Optional[str] = None
    last_seen: Optional[str] = None
    freshness_tier: Optional[str] = None
    distance_km: Optional[float] = None
    distance_sort_key: Optional[float] = None
    postal_coords_estimated: Optional[bool] = None

    class Config:
        extra = "allow"


class AssignmentListResponse(BaseModel):
    ok: bool = True
    total: int = 0
    items: List[AssignmentRow] = Field(default_factory=list)
    next_cursor_last_seen: Optional[str] = None
    next_cursor_id: Optional[int] = None
    next_cursor_distance_km: Optional[float] = None


class AssignmentFacetsResponse(BaseModel):
    ok: bool = True
    facets: Dict[str, Any] = Field(default_factory=dict)


class MatchCountsRequest(BaseModel):
    levels: Optional[List[str]] = None
    specific_student_levels: Optional[List[str]] = None
    subjects: Optional[List[str]] = None
    subjects_canonical: Optional[List[str]] = None
    subjects_general: Optional[List[str]] = None


@app.get("/health")
def health() -> Dict[str, Any]:
    return {"ok": True}


@app.get("/contracts/assignment-row.schema.json")
def assignment_row_contract() -> Response:
    path = (Path(__file__).resolve().parent / "contracts" / "assignment_row.schema.json").resolve()
    body = path.read_text(encoding="utf8")
    return Response(content=body, media_type="application/schema+json")


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


def _pg_array_literal(items: List[str]) -> str:
    # PostgREST array operators expect a Postgres array literal, e.g. {"Junior College","IB"}.
    out: List[str] = []
    for raw in items or []:
        s = str(raw or "").strip()
        if not s:
            continue
        s = s.replace("\\", "\\\\").replace('"', '\\"')
        out.append(f'"{s}"')
    return "{" + ",".join(out) + "}"


def _count_from_content_range(value: Optional[str]) -> Optional[int]:
    if not value:
        return None
    # Example: "0-0/1234" or "*/1234"
    if "/" not in value:
        return None
    try:
        return int(value.split("/")[-1])
    except Exception:
        return None


def _count_matching_assignments(
    *,
    days: int,
    levels: List[str],
    specific_student_levels: List[str],
    subjects_canonical: List[str],
    subjects_general: List[str],
) -> Optional[int]:
    if not sb.enabled() or not sb.client:
        return None

    since = datetime.now(timezone.utc) - timedelta(days=int(days))
    since_iso = since.isoformat()

    # Count all assignments (open + closed) so this reflects historical volume for DM expectations.
    #
    # IMPORTANT: use `published_at` (source publish time), not `last_seen` (our processing time),
    # otherwise backfills/reprocesses inflate recent counts.
    q = f"assignments?select=id&published_at=gte.{_url_quote(since_iso, safe='')}&limit=0"
    if levels:
        arr = _pg_array_literal(levels)
        q += f"&signals_levels=ov.{_url_quote(arr, safe='')}"
    if specific_student_levels:
        arr = _pg_array_literal(specific_student_levels)
        q += f"&signals_specific_student_levels=ov.{_url_quote(arr, safe='')}"
    if subjects_canonical:
        arr = _pg_array_literal(subjects_canonical)
        q += f"&subjects_canonical=ov.{_url_quote(arr, safe='')}"
    if subjects_general:
        arr = _pg_array_literal(subjects_general)
        q += f"&subjects_general=ov.{_url_quote(arr, safe='')}"

    try:
        resp = sb.client.get(q, timeout=20, prefer="count=exact")
    except Exception:
        return None
    if resp.status_code >= 300:
        logger.warning("match_counts_query_failed status=%s body=%s", resp.status_code, resp.text[:300])
        return None
    return _count_from_content_range(resp.headers.get("content-range"))


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


@app.get("/health/webhook")
def health_webhook() -> Dict[str, Any]:
    """
    Check Telegram webhook status for the broadcast bot.
    
    Returns webhook information including URL, pending updates, and any errors.
    Useful for monitoring and troubleshooting inline button functionality.
    """
    token = _bot_token_for_edits()
    if not token:
        return {
            "ok": False,
            "error": "no_bot_token",
            "message": "GROUP_BOT_TOKEN not configured"
        }
    
    import requests  # local import
    
    try:
        resp = requests.get(
            f"https://api.telegram.org/bot{token}/getWebhookInfo",
            timeout=10
        )
        resp.raise_for_status()
        result = resp.json()
        
        if not result.get("ok"):
            return {
                "ok": False,
                "error": "telegram_api_error",
                "description": result.get("description", "Unknown error")
            }
        
        info = result.get("result", {})
        webhook_url = info.get("url", "")
        has_webhook = bool(webhook_url)
        
        # Determine health status
        ok = has_webhook and info.get("pending_update_count", 0) < 100
        if info.get("last_error_date"):
            ok = False
        
        return {
            "ok": ok,
            "has_webhook": has_webhook,
            "webhook_url": webhook_url or None,
            "pending_updates": info.get("pending_update_count", 0),
            "max_connections": info.get("max_connections"),
            "allowed_updates": info.get("allowed_updates", []),
            "last_error_date": info.get("last_error_date"),
            "last_error_message": info.get("last_error_message"),
            "has_custom_certificate": info.get("has_custom_certificate", False),
        }
    except requests.RequestException as e:
        return {
            "ok": False,
            "error": "request_failed",
            "message": str(e)
        }


def _clean_opt_str(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    v = str(value).strip()
    return v or None


@app.get("/assignments", response_model=AssignmentListResponse)
async def list_assignments(
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
) -> Response:
    """
    Public listing endpoint for the website.
    Requires DB RPC `public.list_open_assignments` (see TutorDexAggregator/supabase sqls).
    """
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

    # Anonymous protections: rate-limit + cap + short cache for the common "first page newest" query.
    uid_hint = _get_uid_from_request(request)
    is_anon = uid_hint is None
    if is_anon:
        await _public_rate_limit_or_429(request, endpoint="assignments", rpm=_public_rpm_assignments())
        lim = min(lim, _public_assignments_limit_cap())

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
        uid = uid_hint
        if uid:
            try:
                request.state.uid = uid
            except Exception:
                pass

    cache_ttl_s = _public_cache_ttl_assignments_s() if is_anon else 0
    cache_key = ""
    cache_eligible = bool(
        is_anon
        and cache_ttl_s > 0
        and sort_s == "newest"
        and cursor_last_seen_s is None
        and cursor_id is None
        and cursor_distance_km is None
    )
    if cache_eligible:
        try:
            q_items = list(request.query_params.multi_items())
        except Exception:
            q_items = []
        # Cache key should reflect the effective public cap, not the raw requested limit.
        q_items = [(k, v) for (k, v) in q_items if str(k) != "limit"]
        q_items.append(("limit", str(lim)))
        cache_key = _cache_key_from_items(str(request.url.path), q_items, namespace="pubcache:assignments")
        cached = await _public_cache_get(cache_key)
        if cached:
            return JSONResponse(
                content=cached,
                headers={
                    "Cache-Control": f"public, max-age={int(cache_ttl_s)}",
                    "X-Cache": "HIT",
                },
            )

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
        if sort_s == "distance":
            next_cursor_last_seen_out = _clean_opt_str(last.get("last_seen"))
        else:
            next_cursor_last_seen_out = _clean_opt_str(last.get("published_at") or last.get("created_at") or last.get("last_seen"))
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

    payload = AssignmentListResponse(
        ok=True,
        total=total,
        items=items,
        next_cursor_last_seen=next_cursor_last_seen_out,
        next_cursor_id=next_cursor_id_out,
        next_cursor_distance_km=next_cursor_distance_km_out,
    ).model_dump()

    if cache_eligible and cache_key:
        await _public_cache_set(cache_key, payload, ttl_s=int(cache_ttl_s))
        return JSONResponse(
            content=payload,
            headers={
                "Cache-Control": f"public, max-age={int(cache_ttl_s)}",
                "X-Cache": "MISS",
            },
        )

    return JSONResponse(content=payload)


@app.get("/assignments/facets", response_model=AssignmentFacetsResponse)
async def assignment_facets(
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
) -> Response:
    """
    Public facets endpoint for the website.
    Requires DB RPC `public.open_assignment_facets` (see TutorDexAggregator/supabase sqls).
    """
    if not sb.enabled():
        raise HTTPException(status_code=503, detail="supabase_disabled")

    uid_hint = _get_uid_from_request(request)
    is_anon = uid_hint is None
    if is_anon:
        await _public_rate_limit_or_429(request, endpoint="facets", rpm=_public_rpm_facets())

    cache_ttl_s = _public_cache_ttl_facets_s() if is_anon else 0
    cache_key = ""
    if is_anon and cache_ttl_s > 0:
        try:
            q_items = list(request.query_params.multi_items())
        except Exception:
            q_items = []
        cache_key = _cache_key_from_items(str(request.url.path), q_items, namespace="pubcache:facets")
        cached = await _public_cache_get(cache_key)
        if cached:
            return JSONResponse(
                content=cached,
                headers={
                    "Cache-Control": f"public, max-age={int(cache_ttl_s)}",
                    "X-Cache": "HIT",
                },
            )

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

    payload = AssignmentFacetsResponse(ok=True, facets=facets).model_dump()
    if cache_key and cache_ttl_s > 0:
        await _public_cache_set(cache_key, payload, ttl_s=int(cache_ttl_s))
        return JSONResponse(
            content=payload,
            headers={
                "Cache-Control": f"public, max-age={int(cache_ttl_s)}",
                "X-Cache": "MISS",
            },
        )
    return JSONResponse(content=payload)


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


@app.post("/me/assignments/match-counts")
def me_assignment_match_counts(request: Request, req: MatchCountsRequest) -> Dict[str, Any]:
    _ = _require_uid(request)
    if not sb.enabled():
        raise HTTPException(status_code=503, detail="supabase_disabled")

    levels = [str(x).strip() for x in (req.levels or []) if str(x).strip()]
    specific_student_levels = [str(x).strip() for x in (req.specific_student_levels or []) if str(x).strip()]
    subjects_canonical = [str(x).strip() for x in (req.subjects_canonical or req.subjects or []) if str(x).strip()]
    subjects_general = [str(x).strip() for x in (req.subjects_general or []) if str(x).strip()]

    # Keep requests bounded (DoS safety + avoids giant URLs).
    levels = levels[:50]
    specific_student_levels = specific_student_levels[:100]
    subjects_canonical = subjects_canonical[:200]
    subjects_general = subjects_general[:50]

    if not levels and not specific_student_levels and not subjects_canonical and not subjects_general:
        raise HTTPException(status_code=400, detail="empty_preferences")

    counts: Dict[str, Any] = {}
    for d in (7, 14, 30):
        c = _count_matching_assignments(
            days=d,
            levels=levels,
            specific_student_levels=specific_student_levels,
            subjects_canonical=subjects_canonical,
            subjects_general=subjects_general,
        )
        if c is None:
            raise HTTPException(status_code=500, detail="match_counts_failed")
        counts[str(d)] = int(c)

    return {
        "ok": True,
        "counts": counts,
        "window_field": "published_at",
        "status_filter": "any",
    }


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
    # CLICK TRACKING DISABLED: This endpoint now returns a no-op response
    return {
        "ok": True,
        "tracked": False,
        "clicks": None,
        "external_id": (req.assignment_external_id or "").strip() or None,
    }
    # external_id = (req.assignment_external_id or "").strip()
    # destination_url = await _resolve_original_url(
    #     external_id=external_id, destination_url=req.destination_url
    # )
    #
    # tracked = False
    # clicks: Optional[int] = None
    # if external_id and destination_url and sb.enabled():
    #     try:
    #         should_inc = await _should_increment_click(request, external_id=external_id)
    #     except Exception:
    #         should_inc = True
    #     if should_inc:
    #         clicks = sb.increment_assignment_clicks(
    #             external_id=external_id, original_url=destination_url, delta=1
    #         )
    #         tracked = True
    #
    # return {
    #     "ok": True,
    #     "tracked": tracked,
    #     "clicks": int(clicks) if clicks is not None else None,
    #     "external_id": external_id or None,
    # }


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


def _verify_telegram_webhook(request: Request) -> bool:
    """
    Verify Telegram webhook request using secret token.
    
    When a webhook is set with a secret_token, Telegram includes it in the
    X-Telegram-Bot-Api-Secret-Token header. We verify it matches our configured secret.
    
    Returns True if verification passes or no secret is configured (permissive mode).
    """
    configured_secret = (os.environ.get("WEBHOOK_SECRET_TOKEN") or "").strip()
    if not configured_secret:
        # No secret configured - allow requests (backward compatible)
        return True
    
    # FastAPI converts headers to lowercase. Telegram sends this as
    # "X-Telegram-Bot-Api-Secret-Token" per their webhook documentation,
    # but we access it as lowercase per FastAPI's normalization.
    header_secret = (request.headers.get("x-telegram-bot-api-secret-token") or "").strip()
    
    return header_secret == configured_secret


@app.post("/telegram/callback")
async def telegram_callback(request: Request) -> Dict[str, Any]:
    """
    Handle Telegram webhook callbacks for inline button interactions.
    
    CLICK TRACKING DISABLED: This endpoint now returns a no-op response.
    
    This endpoint receives callback queries when users click inline buttons
    in broadcast messages. Requires a webhook to be set up with Telegram.
    
    Setup:
        python TutorDexBackend/telegram_webhook_setup.py set --url https://yourdomain.com/telegram/callback
    """
    return {"ok": True, "external_id": None, "has_url": False, "disabled": True}
    # # Verify webhook secret token if configured
    # if not _verify_telegram_webhook(request):
    #     logger.warning(
    #         "telegram_callback_unauthorized",
    #         extra={"client_ip": _client_ip(request)}
    #     )
    #     raise HTTPException(status_code=401, detail="invalid_webhook_secret")
    #
    # try:
    #     update = await request.json()
    # except Exception:
    #     raise HTTPException(status_code=400, detail="invalid_payload")
    #
    # cq = (update or {}).get("callback_query") or {}
    # data = str(cq.get("data") or "").strip()
    # if not data:
    #     return {"ok": False, "reason": "no_callback"}
    #
    # if not data.startswith("open:"):
    #     return {"ok": False, "reason": "unsupported_callback"}
    #
    # external_id = data.split(":", 1)[1].strip() if ":" in data else ""
    # original_url = await _resolve_original_url(external_id=external_id, destination_url=None)
    #
    # if external_id and original_url and sb.enabled():
    #     try:
    #         if await _should_increment_click(request, external_id=external_id):
    #             sb.increment_assignment_clicks(
    #                 external_id=external_id, original_url=original_url, delta=1
    #             )
    #     except Exception:
    #         logger.exception("telegram_callback_increment_failed", extra={"external_id": external_id})
    #
    # await _telegram_answer_callback_query(callback_query_id=str(cq.get("id") or ""), url=original_url)
    #
    # return {"ok": True, "external_id": external_id or None, "has_url": bool(original_url)}
