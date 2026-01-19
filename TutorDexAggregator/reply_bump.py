"""
Bump assignments from reply messages.

When a reply message is detected, we fetch the parent message and bump
the corresponding assignment in the database to keep it fresh.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, Optional

import requests

try:
    from logging_setup import log_event, setup_logging  # type: ignore
    from supabase_env import resolve_supabase_url  # type: ignore
except Exception:
    from TutorDexAggregator.logging_setup import log_event, setup_logging  # type: ignore
    from TutorDexAggregator.supabase_env import resolve_supabase_url  # type: ignore

setup_logging()
logger = logging.getLogger("reply_bump")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _headers(key: str) -> Dict[str, str]:
    return {
        "apikey": key,
        "authorization": f"Bearer {key}",
        "content-type": "application/json",
        "prefer": "return=minimal",
    }


def bump_assignment_from_reply(
    channel_link: str,
    reply_to_msg_id: str,
    *,
    supabase_url: Optional[str] = None,
    supabase_key: Optional[str] = None,
    bump_min_seconds: int = 6 * 60 * 60,  # 6 hours default
) -> Dict[str, Any]:
    """
    Bump an assignment when a reply is posted to it.
    
    This is used when a message is detected as a reply. We fetch the parent
    message from telegram_messages_raw, find the corresponding assignment,
    and bump it to keep it fresh.
    
    Args:
        channel_link: Channel link where the reply was posted
        reply_to_msg_id: Message ID that is being replied to
        supabase_url: Supabase URL (defaults to env)
        supabase_key: Supabase service role key (defaults to env)
        bump_min_seconds: Minimum seconds between bumps (default: 6 hours)
        
    Returns:
        Dict with keys:
            - ok: bool
            - bumped: bool (whether assignment was bumped)
            - reason: str (explanation of what happened)
    """
    if not reply_to_msg_id:
        return {
            "ok": False,
            "bumped": False,
            "reason": "No reply_to_msg_id provided",
        }

    # Resolve Supabase config
    if not supabase_url:
        supabase_url = resolve_supabase_url()
    if not supabase_key:
        from shared.config import load_aggregator_config

        supabase_key = load_aggregator_config().supabase_auth_key or ""

    if not supabase_url or not supabase_key:
        return {
            "ok": False,
            "bumped": False,
            "reason": "Missing Supabase configuration",
        }

    try:
        # Step 1: Find the parent message in telegram_messages_raw
        parent_resp = requests.get(
            f"{supabase_url}/rest/v1/telegram_messages_raw",
            headers=_headers(supabase_key),
            params={
                "select": "id,message_id,channel_link",
                "channel_link": f"eq.{channel_link}",
                "message_id": f"eq.{reply_to_msg_id}",
                "limit": 1,
            },
            timeout=10,
        )

        if parent_resp.status_code >= 400:
            log_event(
                logger,
                logging.WARNING,
                "reply_bump_parent_fetch_failed",
                channel_link=channel_link,
                reply_to_msg_id=reply_to_msg_id,
                status=parent_resp.status_code,
            )
            return {
                "ok": False,
                "bumped": False,
                "reason": f"Failed to fetch parent message: HTTP {parent_resp.status_code}",
            }

        parent_rows = parent_resp.json()
        if not parent_rows:
            log_event(
                logger,
                logging.DEBUG,
                "reply_bump_parent_not_found",
                channel_link=channel_link,
                reply_to_msg_id=reply_to_msg_id,
            )
            return {
                "ok": True,
                "bumped": False,
                "reason": "Parent message not found in telegram_messages_raw",
            }

        parent_message_id = parent_rows[0].get("message_id")

        # Step 2: Find the assignment corresponding to this parent message
        assignment_resp = requests.get(
            f"{supabase_url}/rest/v1/assignments",
            headers=_headers(supabase_key),
            params={
                "select": "id,external_id,last_seen,source_last_seen,bump_count",
                "channel_link": f"eq.{channel_link}",
                "message_id": f"eq.{parent_message_id}",
                "limit": 1,
            },
            timeout=10,
        )

        if assignment_resp.status_code >= 400:
            log_event(
                logger,
                logging.WARNING,
                "reply_bump_assignment_fetch_failed",
                channel_link=channel_link,
                message_id=parent_message_id,
                status=assignment_resp.status_code,
            )
            return {
                "ok": False,
                "bumped": False,
                "reason": f"Failed to fetch assignment: HTTP {assignment_resp.status_code}",
            }

        assignment_rows = assignment_resp.json()
        if not assignment_rows:
            log_event(
                logger,
                logging.DEBUG,
                "reply_bump_assignment_not_found",
                channel_link=channel_link,
                message_id=parent_message_id,
            )
            return {
                "ok": True,
                "bumped": False,
                "reason": "Parent message is not an assignment (no matching assignment found)",
            }

        assignment = assignment_rows[0]
        assignment_id = assignment.get("id")
        external_id = assignment.get("external_id")
        last_seen = assignment.get("last_seen") or assignment.get("source_last_seen")
        current_bump_count = int(assignment.get("bump_count") or 0)

        # Step 3: Check if we should bump (time-based throttling)
        should_bump = True
        if last_seen:
            try:
                last_seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                elapsed = (datetime.now(timezone.utc) - last_seen_dt.astimezone(timezone.utc)).total_seconds()
                should_bump = elapsed >= bump_min_seconds

                if not should_bump:
                    log_event(
                        logger,
                        logging.DEBUG,
                        "reply_bump_skipped",
                        channel_link=channel_link,
                        reply_to_msg_id=reply_to_msg_id,
                        assignment_id=assignment_id,
                        external_id=external_id,
                        elapsed_s=round(elapsed, 2),
                        min_seconds=bump_min_seconds,
                    )
                    return {
                        "ok": True,
                        "bumped": False,
                        "reason": f"Assignment bumped recently (elapsed: {round(elapsed/3600, 1)}h < {bump_min_seconds/3600}h)",
                    }
            except Exception as e:
                # If we can't parse the timestamp, bump anyway
                log_event(
                    logger,
                    logging.WARNING,
                    "reply_bump_parse_error",
                    channel_link=channel_link,
                    assignment_id=assignment_id,
                    error=str(e),
                )

        # Step 4: Bump the assignment
        now_iso = _utc_now_iso()
        patch_resp = requests.patch(
            f"{supabase_url}/rest/v1/assignments",
            headers=_headers(supabase_key),
            params={"id": f"eq.{assignment_id}"},
            json={
                "last_seen": now_iso,
                "source_last_seen": now_iso,
                "bump_count": current_bump_count + 1,
            },
            timeout=10,
        )

        if patch_resp.status_code >= 400:
            log_event(
                logger,
                logging.WARNING,
                "reply_bump_patch_failed",
                channel_link=channel_link,
                assignment_id=assignment_id,
                external_id=external_id,
                status=patch_resp.status_code,
            )
            return {
                "ok": False,
                "bumped": False,
                "reason": f"Failed to bump assignment: HTTP {patch_resp.status_code}",
            }

        log_event(
            logger,
            logging.INFO,
            "reply_bump_success",
            channel_link=channel_link,
            reply_to_msg_id=reply_to_msg_id,
            assignment_id=assignment_id,
            external_id=external_id,
            bump_count=current_bump_count + 1,
        )

        return {
            "ok": True,
            "bumped": True,
            "reason": f"Assignment {external_id} bumped successfully (bump #{current_bump_count + 1})",
        }

    except Exception as e:
        log_event(
            logger,
            logging.ERROR,
            "reply_bump_error",
            channel_link=channel_link,
            reply_to_msg_id=reply_to_msg_id,
            error=str(e),
        )
        return {
            "ok": False,
            "bumped": False,
            "reason": f"Error: {str(e)}",
        }
