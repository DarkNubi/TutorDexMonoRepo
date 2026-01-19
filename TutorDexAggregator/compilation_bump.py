"""
Bump assignments from compilation messages.

When a compilation message is detected, we extract assignment codes and
bump the corresponding assignments in the database to keep them fresh.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import requests

try:
    from logging_setup import log_event, setup_logging  # type: ignore
    from supabase_env import resolve_supabase_url  # type: ignore
except Exception:
    from TutorDexAggregator.logging_setup import log_event, setup_logging  # type: ignore
    from TutorDexAggregator.supabase_env import resolve_supabase_url  # type: ignore

setup_logging()
logger = logging.getLogger("compilation_bump")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _headers(key: str) -> Dict[str, str]:
    return {
        "apikey": key,
        "authorization": f"Bearer {key}",
        "content-type": "application/json",
        "prefer": "return=minimal",
    }


def bump_assignments_by_codes(
    assignment_codes: List[str],
    *,
    supabase_url: Optional[str] = None,
    supabase_key: Optional[str] = None,
    bump_min_seconds: int = 6 * 60 * 60,  # 6 hours default
) -> Dict[str, Any]:
    """
    Bump assignments by their assignment codes (external_id).
    
    This is used when a compilation message references multiple assignments
    by their codes. We bump each one to keep it fresh in the system.
    
    Args:
        assignment_codes: List of assignment codes to bump
        supabase_url: Supabase URL (defaults to env)
        supabase_key: Supabase service role key (defaults to env)
        bump_min_seconds: Minimum seconds between bumps (default: 6 hours)
        
    Returns:
        Dict with keys:
            - ok: bool
            - bumped: int (number of assignments bumped)
            - skipped: int (number skipped due to recent bump)
            - not_found: int (number of codes not found)
            - errors: List[str] (any error messages)
    """
    if not assignment_codes:
        return {"ok": True, "bumped": 0, "skipped": 0, "not_found": 0, "errors": []}

    # Resolve Supabase config
    if not supabase_url:
        supabase_url = resolve_supabase_url()
    if not supabase_key:
        from shared.config import load_aggregator_config

        supabase_key = load_aggregator_config().supabase_auth_key or ""

    if not supabase_url or not supabase_key:
        return {
            "ok": False,
            "bumped": 0,
            "skipped": 0,
            "not_found": 0,
            "errors": ["Missing Supabase configuration"],
        }

    now_iso = _utc_now_iso()
    bumped = 0
    skipped = 0
    not_found = 0
    errors = []

    for code in assignment_codes:
        try:
            # Find assignment by external_id (assignment code)
            resp = requests.get(
                f"{supabase_url}/rest/v1/assignments",
                headers=_headers(supabase_key),
                params={
                    "select": "id,external_id,last_seen,bump_count",
                    "external_id": f"eq.{code}",
                    "limit": 1,
                },
                timeout=10,
            )

            if resp.status_code >= 400:
                errors.append(f"Failed to fetch {code}: HTTP {resp.status_code}")
                continue

            rows = resp.json()
            if not rows:
                not_found += 1
                log_event(
                    logger,
                    logging.DEBUG,
                    "compilation_bump_not_found",
                    code=code,
                )
                continue

            assignment = rows[0]
            assignment_id = assignment.get("id")
            last_seen = assignment.get("last_seen")
            current_bump_count = int(assignment.get("bump_count") or 0)

            # Check if we should bump (time-based throttling)
            should_bump = True
            if last_seen:
                try:
                    last_seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                    elapsed = (datetime.now(timezone.utc) - last_seen_dt.astimezone(timezone.utc)).total_seconds()
                    should_bump = elapsed >= bump_min_seconds

                    if not should_bump:
                        skipped += 1
                        log_event(
                            logger,
                            logging.DEBUG,
                            "compilation_bump_skipped",
                            code=code,
                            assignment_id=assignment_id,
                            elapsed_s=round(elapsed, 2),
                            min_seconds=bump_min_seconds,
                        )
                        continue
                except Exception as e:
                    # If we can't parse the timestamp, bump anyway
                    log_event(
                        logger,
                        logging.WARNING,
                        "compilation_bump_parse_error",
                        code=code,
                        error=str(e),
                    )

            # Bump the assignment
            patch_resp = requests.patch(
                f"{supabase_url}/rest/v1/assignments",
                headers=_headers(supabase_key),
                params={"id": f"eq.{assignment_id}"},
                json={
                    "last_seen": now_iso,
                    "bump_count": current_bump_count + 1,
                },
                timeout=10,
            )

            if patch_resp.status_code >= 400:
                errors.append(f"Failed to bump {code}: HTTP {patch_resp.status_code}")
                continue

            bumped += 1
            log_event(
                logger,
                logging.INFO,
                "compilation_bump_success",
                code=code,
                assignment_id=assignment_id,
                bump_count=current_bump_count + 1,
            )

        except Exception as e:
            errors.append(f"Error bumping {code}: {str(e)}")
            log_event(
                logger,
                logging.ERROR,
                "compilation_bump_error",
                code=code,
                error=str(e),
            )

    result = {
        "ok": len(errors) == 0,
        "bumped": bumped,
        "skipped": skipped,
        "not_found": not_found,
        "errors": errors,
    }

    log_event(
        logger,
        logging.INFO,
        "compilation_bump_complete",
        total_codes=len(assignment_codes),
        **result,
    )

    return result
