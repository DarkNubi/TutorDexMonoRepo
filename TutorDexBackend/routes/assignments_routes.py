from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from TutorDexBackend.models import AssignmentFacetsResponse, AssignmentListResponse
from TutorDexBackend.runtime import auth_service, cache_service, logger, sb, store
from TutorDexBackend.utils.request_utils import clean_optional_string

router = APIRouter()


@router.get("/assignments", response_model=AssignmentListResponse)
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
    if not sb.enabled():
        raise HTTPException(status_code=503, detail="supabase_disabled")

    lim = max(1, min(int(limit), 200))
    cursor_last_seen_s = clean_optional_string(cursor_last_seen)
    sort_s = (sort or "newest").strip().lower()
    if sort_s not in {"newest", "distance"}:
        raise HTTPException(status_code=400, detail="invalid_sort")

    uid_hint = auth_service.get_uid_from_request(request)
    is_anon = uid_hint is None
    if is_anon:
        await cache_service.enforce_rate_limit(request, "assignments")
        lim = min(lim, cache_service.get_public_limit_cap())

    uid = None
    if not is_anon:
        uid = auth_service.require_uid(request)

    cache_ttl_s = cache_service.get_cache_ttl("assignments") if is_anon else 0
    cache_key = ""
    cache_eligible = is_anon and cache_ttl_s > 0
    if cache_eligible:
        q_items = list(request.query_params.multi_items())
        q_items = [(k, v) for (k, v) in q_items if str(k) != "limit"]
        q_items.append(("limit", str(lim)))
        cache_key = cache_service.build_cache_key_for_request(
            request,
            namespace="pubcache:assignments",
            extra_items=[("limit", str(lim))],
        )
        cached = await cache_service.get_cached(cache_key)
        if cached:
            return JSONResponse(
                content=cached,
                headers={
                    "Cache-Control": f"public, max-age={int(cache_ttl_s)}",
                    "X-Cache": "HIT",
                },
            )

    tutor_lat: Optional[float] = None
    tutor_lon: Optional[float] = None
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
            next_cursor_last_seen_out = clean_optional_string(last.get("published_at") or last.get("created_at") or last.get("last_seen"))
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

    if cache_eligible and cache_key:
        await cache_service.set_cached(cache_key, payload, ttl_s=int(cache_ttl_s))
        return JSONResponse(
            content=payload,
            headers={
                "Cache-Control": f"public, max-age={int(cache_ttl_s)}",
                "X-Cache": "MISS",
            },
        )

    return JSONResponse(content=payload)


@router.get("/assignments/facets", response_model=AssignmentFacetsResponse)
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
    if not sb.enabled():
        raise HTTPException(status_code=503, detail="supabase_disabled")

    uid_hint = auth_service.get_uid_from_request(request)
    is_anon = uid_hint is None
    if is_anon:
        await cache_service.enforce_rate_limit(request, "facets")

    cache_ttl_s = cache_service.get_cache_ttl("facets") if is_anon else 0
    cache_key = ""
    if is_anon and cache_ttl_s > 0:
        cache_key = cache_service.build_cache_key_for_request(request, namespace="pubcache:facets")
        cached = await cache_service.get_cached(cache_key)
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
        await cache_service.set_cached(cache_key, payload, ttl_s=int(cache_ttl_s))
        return JSONResponse(
            content=payload,
            headers={
                "Cache-Control": f"public, max-age={int(cache_ttl_s)}",
                "X-Cache": "MISS",
            },
        )
    return JSONResponse(content=payload)

