from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request

from TutorDexBackend.matching import match_from_payload
from TutorDexBackend.models import MatchPayloadRequest, TutorUpsert
from TutorDexBackend.runtime import auth_service, store

router = APIRouter()


@router.put("/tutors/{tutor_id}")
def upsert_tutor(request: Request, tutor_id: str, req: TutorUpsert) -> Dict[str, Any]:
    auth_service.require_admin(request)
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


@router.get("/tutors/{tutor_id}")
def get_tutor(request: Request, tutor_id: str) -> Dict[str, Any]:
    auth_service.require_admin(request)
    tutor = store.get_tutor(tutor_id)
    if not tutor:
        raise HTTPException(status_code=404, detail="tutor_not_found")
    return tutor


@router.delete("/tutors/{tutor_id}")
def delete_tutor(request: Request, tutor_id: str) -> Dict[str, Any]:
    auth_service.require_admin(request)
    store.delete_tutor(tutor_id)
    return {"ok": True}


@router.post("/match/payload")
def match_payload(request: Request, req: MatchPayloadRequest) -> Dict[str, Any]:
    auth_service.require_admin(request)
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

