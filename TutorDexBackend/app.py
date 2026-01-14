"""
TutorDex Backend API.

FastAPI service providing HTTP endpoints for the TutorDex website.
Refactored to extract services for better organization and maintainability.
"""
import time
import uuid
import logging
from datetime import timezone
from typing import Any, Dict, List, Optional
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

# Core dependencies
from TutorDexBackend.redis_store import TutorStore
from TutorDexBackend.matching import match_from_payload
from TutorDexBackend.supabase_store import SupabaseStore
from TutorDexBackend.logging_setup import setup_logging
from TutorDexBackend.geocoding import geocode_sg_postal_code, normalize_sg_postal_code
from TutorDexBackend.metrics import metrics_payload, observe_request
from TutorDexBackend.otel import setup_otel
from TutorDexBackend.sentry_init import setup_sentry

# Services and utilities
from TutorDexBackend.services.auth_service import AuthService
from TutorDexBackend.services.health_service import HealthService
from TutorDexBackend.services.cache_service import CacheService
from TutorDexBackend.services.telegram_service import TelegramService
from TutorDexBackend.services.analytics_service import AnalyticsService
from TutorDexBackend.utils.config_utils import (
    get_app_env,
    is_production,
    get_redis_prefix,
    get_bot_token_for_edits,
)
from TutorDexBackend.utils.request_utils import (
    get_client_ip,
    parse_traceparent,
    clean_optional_string,
)
from TutorDexBackend.utils.database_utils import count_matching_assignments
from shared.config import load_backend_config


# Setup logging and monitoring
setup_logging()
logger = logging.getLogger("tutordex_backend")
setup_sentry(service_name="tutordex-backend")
setup_otel()

# Initialize FastAPI app and core stores
app = FastAPI(title="TutorDex Backend", version="0.1.0")
store = TutorStore()
sb = SupabaseStore()
_CFG = load_backend_config()

# Initialize services
_auth_service = AuthService()
_health_service = HealthService(store, sb)
_cache_service = CacheService(store)
_telegram_service = TelegramService(store)
_analytics_service = AnalyticsService(sb, store)

# Configure CORS
_cors_origins = str(_CFG.cors_allow_origins or "*").strip()
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
    """Validate production configuration and log startup info."""
    # Fail fast on dangerous misconfig in production
    _auth_service.validate_production_config()
    
    logger.info(
        "startup",
        extra={
            "auth_required": _auth_service.is_auth_required(),
            "app_env": get_app_env(),
            "supabase_enabled": sb.enabled(),
            "redis_prefix": getattr(getattr(store, "cfg", None), "prefix", None),
        },
    )


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    """Access logging middleware with request ID tracking and structured logs."""
    request_id = (
        request.headers.get("x-request-id")
        or request.headers.get("X-Request-Id")
        or str(uuid.uuid4())
    )
    start = time.perf_counter()
    status_code = 500
    trace_id, span_id = parse_traceparent(
        request.headers.get("traceparent") or request.headers.get("Traceparent")
    )

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
            observe_request(
                method=request.method,
                path=request.url.path,
                status_code=int(status_code),
                latency_s=float(latency_s)
            )
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


# ============================================================================
# Pydantic Models
# ============================================================================

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
    desired_assignments_per_day: Optional[int] = Field(None, description="Target number of assignments per day (default: 10)")


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
    tutor_types: Optional[List[Dict[str, Any]]] = None
    rate_breakdown: Optional[Dict[str, Any]] = None
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


# ============================================================================
# Health & Metrics Endpoints
# ============================================================================

@app.get("/metrics")
def metrics() -> Response:
    """Prometheus metrics endpoint."""
    data, content_type = metrics_payload()
    return Response(content=data, media_type=content_type)


@app.get("/health")
def health() -> Dict[str, Any]:
    """Basic health check."""
    return _health_service.basic_health()


@app.get("/health/redis")
def health_redis() -> Dict[str, Any]:
    """Redis connectivity check."""
    return _health_service.redis_health()


@app.get("/health/supabase")
def health_supabase() -> Dict[str, Any]:
    """Supabase connectivity check."""
    return _health_service.supabase_health()


@app.get("/health/full")
def health_full() -> Dict[str, Any]:
    """Aggregate health check for all core services."""
    return _health_service.full_health()


@app.get("/health/collector")
def health_collector() -> Dict[str, Any]:
    """Collector service health check."""
    return _health_service.collector_health()


@app.get("/health/worker")
def health_worker() -> Dict[str, Any]:
    """Worker service health check."""
    return _health_service.worker_health()


@app.get("/health/dependencies")
def health_dependencies() -> Dict[str, Any]:
    """Alias for full health check (backward compatibility)."""
    return _health_service.dependencies_health()


@app.get("/health/webhook")
def health_webhook() -> Dict[str, Any]:
    """Telegram webhook status check."""
    bot_token = get_bot_token_for_edits()
    return _health_service.webhook_health(bot_token)


@app.get("/contracts/assignment-row.schema.json")
def assignment_row_contract() -> Response:
    """Assignment row contract schema."""
    path = (Path(__file__).resolve().parent / "contracts" / "assignment_row.schema.json").resolve()
    body = path.read_text(encoding="utf8")
    return Response(content=body, media_type="application/schema+json")


# ============================================================================
# Public Assignment Endpoints
# ============================================================================

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
    show_duplicates: Optional[bool] = True,
    tutor_type: Optional[str] = None,
) -> Response:
    """
    Public assignment listing endpoint.
    
    Supports filtering, sorting, pagination, and caching for anonymous users.
    """
    if not sb.enabled():
        raise HTTPException(status_code=503, detail="supabase_disabled")
    
    # Parse and validate parameters
    lim = max(1, min(int(limit), 200))
    cursor_last_seen_s = clean_optional_string(cursor_last_seen)
    sort_s = (sort or "newest").strip().lower()
    if sort_s not in {"newest", "distance"}:
        raise HTTPException(status_code=400, detail="invalid_sort")
    
    # Check if user is anonymous and apply protections
    uid_hint = _auth_service.get_uid_from_request(request)
    is_anon = uid_hint is None
    if is_anon:
        await _cache_service.enforce_rate_limit(request, "assignments")
        lim = min(lim, _cache_service.get_public_limit_cap())
    
    # Validate cursor parameters
    if cursor_last_seen_s and cursor_id is None:
        raise HTTPException(status_code=400, detail="cursor_id_required")
    if sort_s == "distance" and cursor_last_seen_s and cursor_distance_km is None:
        raise HTTPException(status_code=400, detail="cursor_distance_km_required")
    
    # Determine user for distance calculations
    uid: Optional[str] = None
    if sort_s == "distance":
        uid = _auth_service.require_uid(request)
    else:
        uid = uid_hint
        if uid:
            try:
                request.state.uid = uid
            except Exception:
                pass
    
    # Check cache for anonymous users
    cache_ttl_s = _cache_service.get_cache_ttl("assignments") if is_anon else 0
    cache_eligible = bool(
        is_anon
        and cache_ttl_s > 0
        and sort_s == "newest"
        and cursor_last_seen_s is None
        and cursor_id is None
        and cursor_distance_km is None
    )
    
    cache_key = ""
    if cache_eligible:
        try:
            q_items = list(request.query_params.multi_items())
        except Exception:
            q_items = []
        # Adjust limit to reflect actual cap
        q_items = [(k, v) for (k, v) in q_items if str(k) != "limit"]
        q_items.append(("limit", str(lim)))
        cache_key = _cache_service.build_cache_key_for_request(
            request,
            namespace="pubcache:assignments",
            extra_items=[("limit", str(lim))]
        )
        cached = await _cache_service.get_cached(cache_key)
        if cached:
            return JSONResponse(
                content=cached,
                headers={
                    "Cache-Control": f"public, max-age={int(cache_ttl_s)}",
                    "X-Cache": "HIT",
                },
            )
    
    # Get tutor coordinates for distance calculations
    tutor_lat: Optional[float] = None
    tutor_lon: Optional[float] = None
    if uid:
        t = store.get_tutor(uid) or {}
        tutor_lat = t.get("postal_lat")
        tutor_lon = t.get("postal_lon")
        # Fallback to Supabase preferences
        if (tutor_lat is None or tutor_lon is None) and sb.enabled():
            user_id = sb.upsert_user(firebase_uid=uid, email=None, name=None)
            if user_id:
                prefs = sb.get_preferences(user_id=user_id)
                if prefs:
                    tutor_lat = prefs.get("postal_lat") if prefs.get("postal_lat") is not None else tutor_lat
                    tutor_lon = prefs.get("postal_lon") if prefs.get("postal_lon") is not None else tutor_lon
    
    if sort_s == "distance" and (tutor_lat is None or tutor_lon is None):
        raise HTTPException(status_code=400, detail="postal_required_for_distance")
    
    # Query assignments
    result = sb.list_open_assignments_v2(
        limit=lim,
        sort=sort_s,
        tutor_lat=float(tutor_lat) if tutor_lat is not None else None,
        tutor_lon=float(tutor_lon) if tutor_lon is not None else None,
        cursor_last_seen=cursor_last_seen_s,
        cursor_id=cursor_id,
        cursor_distance_km=float(cursor_distance_km) if cursor_distance_km is not None else None,
        level=clean_optional_string(level),
        specific_student_level=clean_optional_string(specific_student_level),
        subject=clean_optional_string(subject),
        subject_general=clean_optional_string(subject_general),
        subject_canonical=clean_optional_string(subject_canonical),
        agency_name=clean_optional_string(agency_name),
        learning_mode=clean_optional_string(learning_mode),
        location_query=clean_optional_string(location),
        min_rate=int(min_rate) if min_rate is not None else None,
        show_duplicates=bool(show_duplicates) if show_duplicates is not None else True,
        tutor_type=clean_optional_string(tutor_type),
    )
    if not result:
        raise HTTPException(status_code=500, detail="list_assignments_failed")
    
    # Build response with pagination cursors
    items = result.get("items") or []
    total = int(result.get("total") or 0)
    next_cursor_last_seen_out: Optional[str] = None
    next_cursor_id_out: Optional[int] = None
    next_cursor_distance_km_out: Optional[float] = None
    
    if items and len(items) >= lim:
        last = items[-1] or {}
        if sort_s == "distance":
            next_cursor_last_seen_out = clean_optional_string(last.get("last_seen"))
        else:
            next_cursor_last_seen_out = clean_optional_string(
                last.get("published_at") or last.get("created_at") or last.get("last_seen")
            )
        try:
            next_cursor_id_out = int(last.get("id")) if last.get("id") is not None else None
        except Exception:
            next_cursor_id_out = None
        
        if sort_s == "distance":
            try:
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
    
    # Cache result for anonymous users
    if cache_eligible and cache_key:
        await _cache_service.set_cached(cache_key, payload, ttl_s=int(cache_ttl_s))
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
    Public facets endpoint for assignment filters.
    
    Returns aggregated counts for filter options.
    """
    if not sb.enabled():
        raise HTTPException(status_code=503, detail="supabase_disabled")
    
    uid_hint = _auth_service.get_uid_from_request(request)
    is_anon = uid_hint is None
    if is_anon:
        await _cache_service.enforce_rate_limit(request, "facets")
    
    # Check cache for anonymous users
    cache_ttl_s = _cache_service.get_cache_ttl("facets") if is_anon else 0
    cache_key = ""
    if is_anon and cache_ttl_s > 0:
        cache_key = _cache_service.build_cache_key_for_request(request, namespace="pubcache:facets")
        cached = await _cache_service.get_cached(cache_key)
        if cached:
            return JSONResponse(
                content=cached,
                headers={
                    "Cache-Control": f"public, max-age={int(cache_ttl_s)}",
                    "X-Cache": "HIT",
                },
            )
    
    facets = sb.open_assignment_facets(
        level=clean_optional_string(level),
        specific_student_level=clean_optional_string(specific_student_level),
        subject=clean_optional_string(subject),
        subject_general=clean_optional_string(subject_general),
        subject_canonical=clean_optional_string(subject_canonical),
        agency_name=clean_optional_string(agency_name),
        learning_mode=clean_optional_string(learning_mode),
        location_query=clean_optional_string(location),
        min_rate=int(min_rate) if min_rate is not None else None,
    )
    if facets is None:
        raise HTTPException(status_code=500, detail="facets_failed")
    
    payload = AssignmentFacetsResponse(ok=True, facets=facets).model_dump()
    if cache_key and cache_ttl_s > 0:
        await _cache_service.set_cached(cache_key, payload, ttl_s=int(cache_ttl_s))
        return JSONResponse(
            content=payload,
            headers={
                "Cache-Control": f"public, max-age={int(cache_ttl_s)}",
                "X-Cache": "MISS",
            },
        )
    return JSONResponse(content=payload)


# ============================================================================
# Duplicate Detection Endpoints
# ============================================================================

@app.get("/assignments/{assignment_id}/duplicates")
async def get_assignment_duplicates(
    request: Request,
    assignment_id: int,
) -> Response:
    """Get all duplicates for an assignment."""
    if not sb.enabled():
        raise HTTPException(status_code=503, detail="supabase_disabled")
    
    try:
        # Get the assignment
        assignment_query = f"assignments?id=eq.{assignment_id}&select=id,duplicate_group_id,is_primary_in_group,duplicate_confidence_score&limit=1"
        assignment_resp = sb.client.get(assignment_query, timeout=10)
        
        if assignment_resp.status_code != 200:
            logger.error(f"Failed to fetch assignment {assignment_id}: {assignment_resp.status_code}")
            raise HTTPException(status_code=500, detail="fetch_failed")
        
        assignments = assignment_resp.json()
        if not assignments:
            raise HTTPException(status_code=404, detail="assignment_not_found")
        
        assignment = assignments[0]
        duplicate_group_id = assignment.get("duplicate_group_id")
        
        # If no duplicate group, return empty duplicates list
        if not duplicate_group_id:
            return JSONResponse(content={
                "ok": True,
                "assignment_id": assignment_id,
                "duplicate_group_id": None,
                "is_primary": True,
                "confidence_score": None,
                "duplicates": []
            })
        
        # Get all assignments in the duplicate group
        duplicates_query = (
            f"assignments?duplicate_group_id=eq.{duplicate_group_id}"
            f"&status=eq.open"
            f"&select=id,agency_name,assignment_code,is_primary_in_group,duplicate_confidence_score,published_at,postal_code,subjects_canonical,signals_levels,rate_min,rate_max"
            f"&order=is_primary_in_group.desc,duplicate_confidence_score.desc.nullslast,published_at.asc"
        )
        duplicates_resp = sb.client.get(duplicates_query, timeout=10)
        
        if duplicates_resp.status_code != 200:
            logger.error(f"Failed to fetch duplicates for group {duplicate_group_id}: {duplicates_resp.status_code}")
            raise HTTPException(status_code=500, detail="fetch_duplicates_failed")
        
        duplicates = duplicates_resp.json()
        
        return JSONResponse(content={
            "ok": True,
            "assignment_id": assignment_id,
            "duplicate_group_id": duplicate_group_id,
            "is_primary": assignment.get("is_primary_in_group", True),
            "confidence_score": float(assignment["duplicate_confidence_score"]) if assignment.get("duplicate_confidence_score") else None,
            "duplicates": duplicates
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching duplicates for assignment {assignment_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="internal_error")


@app.get("/duplicate-groups/{group_id}")
async def get_duplicate_group(
    request: Request,
    group_id: int,
) -> Response:
    """Get detailed information about a duplicate group."""
    if not sb.enabled():
        raise HTTPException(status_code=503, detail="supabase_disabled")
    
    try:
        # Get group metadata
        group_query = f"assignment_duplicate_groups?id=eq.{group_id}&select=*&limit=1"
        group_resp = sb.client.get(group_query, timeout=10)
        
        if group_resp.status_code != 200:
            logger.error(f"Failed to fetch duplicate group {group_id}: {group_resp.status_code}")
            raise HTTPException(status_code=500, detail="fetch_failed")
        
        groups = group_resp.json()
        if not groups:
            raise HTTPException(status_code=404, detail="group_not_found")
        
        group = groups[0]
        
        # Get all assignments in the group
        assignments_query = (
            f"assignments?duplicate_group_id=eq.{group_id}"
            f"&status=eq.open"
            f"&select=id,agency_name,assignment_code,is_primary_in_group,duplicate_confidence_score,published_at,postal_code,subjects_canonical,signals_levels,rate_min,rate_max,message_link"
            f"&order=is_primary_in_group.desc,duplicate_confidence_score.desc.nullslast,published_at.asc"
        )
        assignments_resp = sb.client.get(assignments_query, timeout=10)
        
        if assignments_resp.status_code != 200:
            logger.error(f"Failed to fetch assignments for group {group_id}: {assignments_resp.status_code}")
            raise HTTPException(status_code=500, detail="fetch_assignments_failed")
        
        assignments = assignments_resp.json()
        
        return JSONResponse(content={
            "ok": True,
            "group": {
                "id": group["id"],
                "primary_assignment_id": group.get("primary_assignment_id"),
                "member_count": group.get("member_count", 0),
                "avg_confidence_score": float(group["avg_confidence_score"]) if group.get("avg_confidence_score") else None,
                "status": group.get("status", "active"),
                "created_at": group.get("created_at"),
                "updated_at": group.get("updated_at"),
            },
            "assignments": assignments
        })
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching duplicate group {group_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="internal_error")


# ============================================================================
# Admin Endpoints - Tutor Management
# ============================================================================

@app.put("/tutors/{tutor_id}")
def upsert_tutor(request: Request, tutor_id: str, req: TutorUpsert) -> Dict[str, Any]:
    """Admin endpoint to upsert tutor preferences."""
    _auth_service.require_admin(request)
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
        desired_assignments_per_day=req.desired_assignments_per_day,
    )


@app.get("/tutors/{tutor_id}")
def get_tutor(request: Request, tutor_id: str) -> Dict[str, Any]:
    """Admin endpoint to get tutor preferences."""
    _auth_service.require_admin(request)
    tutor = store.get_tutor(tutor_id)
    if not tutor:
        raise HTTPException(status_code=404, detail="tutor_not_found")
    return tutor


@app.delete("/tutors/{tutor_id}")
def delete_tutor(request: Request, tutor_id: str) -> Dict[str, Any]:
    """Admin endpoint to delete tutor."""
    _auth_service.require_admin(request)
    store.delete_tutor(tutor_id)
    return {"ok": True}


@app.post("/match/payload")
def match_payload(request: Request, req: MatchPayloadRequest) -> Dict[str, Any]:
    """Admin endpoint to match assignment payload to tutors."""
    _auth_service.require_admin(request)
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
                "rating": r.rating,
                "rate_min": r.rate_min,
                "rate_max": r.rate_max,
            }
            for r in results
        ],
        "chat_ids": [r.chat_id for r in results],
    }


# ============================================================================
# User Endpoints - Profile & Preferences
# ============================================================================

@app.get("/me")
def me(request: Request) -> Dict[str, Any]:
    """Get current user info."""
    uid = _auth_service.require_uid(request)
    return {"ok": True, "uid": uid}


@app.get("/me/tutor")
def me_get_tutor(request: Request) -> Dict[str, Any]:
    """Get current user's tutor preferences."""
    uid = _auth_service.require_uid(request)
    tutor = store.get_tutor(uid) or {"tutor_id": uid, "desired_assignments_per_day": 10}
    
    # Merge with Supabase preferences if available
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
                        "desired_assignments_per_day": prefs.get("desired_assignments_per_day") if prefs.get("desired_assignments_per_day") is not None else tutor.get("desired_assignments_per_day", 10),
                        "updated_at": prefs.get("updated_at") or tutor.get("updated_at"),
                    }
                )
    
    return tutor


@app.post("/me/assignments/match-counts")
def me_assignment_match_counts(request: Request, req: MatchCountsRequest) -> Dict[str, Any]:
    """Get count of matching assignments for user's preferences."""
    _ = _auth_service.require_uid(request)
    if not sb.enabled():
        raise HTTPException(status_code=503, detail="supabase_disabled")
    
    levels = [str(x).strip() for x in (req.levels or []) if str(x).strip()]
    specific_student_levels = [str(x).strip() for x in (req.specific_student_levels or []) if str(x).strip()]
    subjects_canonical = [str(x).strip() for x in (req.subjects_canonical or req.subjects or []) if str(x).strip()]
    subjects_general = [str(x).strip() for x in (req.subjects_general or []) if str(x).strip()]
    
    # Keep requests bounded (DoS safety + avoids giant URLs)
    levels = levels[:50]
    specific_student_levels = specific_student_levels[:100]
    subjects_canonical = subjects_canonical[:200]
    subjects_general = subjects_general[:50]
    
    if not levels and not specific_student_levels and not subjects_canonical and not subjects_general:
        raise HTTPException(status_code=400, detail="empty_preferences")
    
    counts: Dict[str, Any] = {}
    for d in (7, 14, 30):
        c = count_matching_assignments(
            sb,
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
    """Update current user's tutor preferences."""
    uid = _auth_service.require_uid(request)
    
    # Geocode postal code if provided
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
    
    # Update Redis store
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
        desired_assignments_per_day=req.desired_assignments_per_day,
    )
    
    # Update Supabase preferences
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
            if req.desired_assignments_per_day is not None:
                prefs["desired_assignments_per_day"] = req.desired_assignments_per_day
            sb.upsert_preferences(
                user_id=user_id,
                prefs=prefs,
            )
    
    return {"ok": True, "tutor_id": uid}


@app.post("/me/telegram/link-code")
def me_telegram_link_code(request: Request) -> Dict[str, Any]:
    """Generate Telegram link code for current user."""
    uid = _auth_service.require_uid(request)
    return store.create_telegram_link_code(uid, ttl_seconds=600)


# ============================================================================
# Analytics & Tracking Endpoints
# ============================================================================

@app.post("/track")
async def track_click(request: Request, req: ClickTrackRequest) -> Dict[str, Any]:
    """
    Click tracking endpoint (DISABLED).
    
    This endpoint now returns a no-op response as click tracking is disabled.
    """
    return {
        "ok": True,
        "tracked": False,
        "clicks": None,
        "external_id": (req.assignment_external_id or "").strip() or None,
    }


@app.post("/analytics/event")
def analytics_event(request: Request, req: AnalyticsEventRequest) -> Dict[str, Any]:
    """Record analytics event."""
    uid = _auth_service.require_uid(request)
    if not sb.enabled():
        return {"ok": False, "skipped": True, "reason": "supabase_disabled"}
    
    user_id = sb.upsert_user(firebase_uid=uid, email=None, name=None)
    assignment_id = None
    if req.assignment_external_id:
        assignment_id = sb.resolve_assignment_id(
            external_id=req.assignment_external_id,
            agency_name=req.agency_name
        )
    
    _analytics_service.insert_analytics_event(
        user_id=user_id,
        assignment_id=assignment_id,
        event_type=req.event_type,
        meta=req.meta or {"external_id": req.assignment_external_id, "agency_name": req.agency_name}
    )
    return {"ok": True}


# ============================================================================
# Telegram Integration Endpoints
# ============================================================================

@app.post("/telegram/link-code")
def telegram_link_code(request: Request, req: TelegramLinkCodeRequest) -> Dict[str, Any]:
    """Admin endpoint to generate Telegram link code for any user."""
    _auth_service.require_admin(request)
    ttl = max(60, min(3600, int(req.ttl_seconds or 600)))
    return store.create_telegram_link_code(req.tutor_id, ttl_seconds=ttl)


@app.post("/telegram/claim")
def telegram_claim(request: Request, req: TelegramClaimRequest) -> Dict[str, Any]:
    """Admin endpoint to claim Telegram link code."""
    _auth_service.require_admin(request)
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
    """
    Telegram webhook callback endpoint (DISABLED).
    
    This endpoint now returns a no-op response as click tracking is disabled.
    Webhook callbacks require click tracking to be enabled.
    """
    return {"ok": True, "external_id": None, "has_url": False, "disabled": True}
