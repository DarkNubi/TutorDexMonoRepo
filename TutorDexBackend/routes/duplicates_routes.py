from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, Response

from TutorDexBackend.runtime import logger, sb

router = APIRouter()


@router.get("/assignments/{assignment_id}/duplicates")
async def get_assignment_duplicates(request: Request, assignment_id: int) -> Response:
    if not sb.enabled():
        raise HTTPException(status_code=503, detail="supabase_disabled")

    try:
        assignment_query = (
            f"assignments?id=eq.{assignment_id}&select=id,duplicate_group_id,is_primary_in_group,duplicate_confidence_score&limit=1"
        )
        assignment_resp = sb.client.get(assignment_query, timeout=10)

        if assignment_resp.status_code != 200:
            logger.error(f"Failed to fetch assignment {assignment_id}: {assignment_resp.status_code}")
            raise HTTPException(status_code=500, detail="fetch_failed")

        assignments = assignment_resp.json()
        if not assignments:
            raise HTTPException(status_code=404, detail="assignment_not_found")

        assignment = assignments[0]
        group_id = assignment.get("duplicate_group_id")
        if not group_id:
            return JSONResponse(
                content={
                    "ok": True,
                    "assignment_id": assignment_id,
                    "duplicate_group_id": None,
                    "duplicates": [],
                }
            )

        duplicates_query = f"assignments?duplicate_group_id=eq.{group_id}&select=*"
        duplicates_resp = sb.client.get(duplicates_query, timeout=10)
        if duplicates_resp.status_code != 200:
            logger.error(f"Failed to fetch duplicates for group {group_id}: {duplicates_resp.status_code}")
            raise HTTPException(status_code=500, detail="fetch_duplicates_failed")

        duplicates = duplicates_resp.json()
        return JSONResponse(
            content={
                "ok": True,
                "assignment_id": assignment_id,
                "duplicate_group_id": group_id,
                "duplicates": duplicates,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching duplicates for assignment {assignment_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="internal_error")


@router.get("/duplicate-groups/{group_id}")
async def get_duplicate_group(request: Request, group_id: int) -> Response:
    if not sb.enabled():
        raise HTTPException(status_code=503, detail="supabase_disabled")

    try:
        group_query = f"duplicate_groups?id=eq.{group_id}&select=*"
        group_resp = sb.client.get(group_query, timeout=10)
        if group_resp.status_code != 200:
            logger.error(f"Failed to fetch duplicate group {group_id}: {group_resp.status_code}")
            raise HTTPException(status_code=500, detail="fetch_group_failed")

        groups = group_resp.json()
        if not groups:
            raise HTTPException(status_code=404, detail="group_not_found")

        group = groups[0]
        assignments_query = f"assignments?duplicate_group_id=eq.{group_id}&select=*"
        assignments_resp = sb.client.get(assignments_query, timeout=10)
        if assignments_resp.status_code != 200:
            logger.error(f"Failed to fetch assignments for group {group_id}: {assignments_resp.status_code}")
            raise HTTPException(status_code=500, detail="fetch_assignments_failed")

        assignments = assignments_resp.json()

        return JSONResponse(
            content={
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
                "assignments": assignments,
            }
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching duplicate group {group_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="internal_error")

