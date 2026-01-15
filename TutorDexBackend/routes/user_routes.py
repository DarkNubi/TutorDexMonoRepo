from __future__ import annotations

from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request

from TutorDexBackend.geocoding import geocode_sg_postal_code, normalize_sg_postal_code
from TutorDexBackend.models import MatchCountsRequest, TutorUpsert
from TutorDexBackend.runtime import auth_service, sb, store
from TutorDexBackend.utils.database_utils import count_matching_assignments

router = APIRouter()


@router.get("/me")
def me(request: Request) -> Dict[str, Any]:
    uid = auth_service.require_uid(request)
    return {"ok": True, "uid": uid}


@router.get("/me/tutor")
def me_get_tutor(request: Request) -> Dict[str, Any]:
    uid = auth_service.require_uid(request)
    tutor = store.get_tutor(uid) or {"tutor_id": uid, "desired_assignments_per_day": 10}

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
                        "dm_max_distance_km": prefs.get("dm_max_distance_km")
                        if prefs.get("dm_max_distance_km") is not None
                        else tutor.get("dm_max_distance_km", 5.0),
                        "subjects": prefs.get("subjects") or tutor.get("subjects") or [],
                        "levels": prefs.get("levels") or tutor.get("levels") or [],
                        "subject_pairs": prefs.get("subject_pairs") or tutor.get("subject_pairs") or [],
                        "assignment_types": prefs.get("assignment_types") or tutor.get("assignment_types") or [],
                        "tutor_kinds": prefs.get("tutor_kinds") or tutor.get("tutor_kinds") or [],
                        "learning_modes": prefs.get("learning_modes") or tutor.get("learning_modes") or [],
                        "desired_assignments_per_day": prefs.get("desired_assignments_per_day")
                        if prefs.get("desired_assignments_per_day") is not None
                        else tutor.get("desired_assignments_per_day", 10),
                        "updated_at": prefs.get("updated_at") or tutor.get("updated_at"),
                    }
                )

    return tutor


@router.post("/me/assignments/match-counts")
def me_assignment_match_counts(request: Request, req: MatchCountsRequest) -> Dict[str, Any]:
    _ = auth_service.require_uid(request)
    if not sb.enabled():
        raise HTTPException(status_code=503, detail="supabase_disabled")

    levels = [str(x).strip() for x in (req.levels or []) if str(x).strip()]
    specific_student_levels = [str(x).strip() for x in (req.specific_student_levels or []) if str(x).strip()]
    subjects_canonical = [str(x).strip() for x in (req.subjects_canonical or req.subjects or []) if str(x).strip()]
    subjects_general = [str(x).strip() for x in (req.subjects_general or []) if str(x).strip()]

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


@router.put("/me/tutor")
def me_upsert_tutor(request: Request, req: TutorUpsert) -> Dict[str, Any]:
    uid = auth_service.require_uid(request)

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
        dm_max_distance_km=req.dm_max_distance_km,
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
            if "dm_max_distance_km" in getattr(req, "model_fields_set", set()):
                prefs["dm_max_distance_km"] = req.dm_max_distance_km
            if req.desired_assignments_per_day is not None:
                prefs["desired_assignments_per_day"] = req.desired_assignments_per_day
            sb.upsert_preferences(user_id=user_id, prefs=prefs)

    return {"ok": True, "tutor_id": uid}


@router.post("/me/telegram/link-code")
def me_telegram_link_code(request: Request) -> Dict[str, Any]:
    uid = auth_service.require_uid(request)
    return store.create_telegram_link_code(uid, ttl_seconds=600)
