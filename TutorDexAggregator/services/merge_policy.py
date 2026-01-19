"""
Merge Policy Service

Conservative merge logic for assignment updates.
Handles quality-based overwrites, timestamp comparisons, and signal unions.
"""
from typing import Any, Dict

from shared.config import load_aggregator_config

try:
    from utils.timestamp_utils import parse_iso_dt
    from utils.field_coercion import coerce_text_list
    from services.row_builder import compute_parse_quality
except Exception:
    from TutorDexAggregator.utils.timestamp_utils import parse_iso_dt
    from TutorDexAggregator.utils.field_coercion import coerce_text_list
    from TutorDexAggregator.services.row_builder import compute_parse_quality


def _freshness_enabled() -> bool:
    """Check if freshness tier feature is enabled."""
    try:
        return bool(load_aggregator_config().freshness_tier_enabled)
    except Exception:
        return False


def merge_patch_body(*, existing: Dict[str, Any], incoming_row: Dict[str, Any], force_upgrade: bool = False) -> Dict[str, Any]:
    """
    Conservative merge:
    - Always update latest message pointers (message_id/message_link).
    - Allow filling missing fields.
    - Overwrite more broadly only when parse_quality_score improves.
    
    Args:
        existing: Current database row
        incoming_row: New row to merge
        force_upgrade: Force full upgrade even if quality score didn't improve
    
    Returns:
        Dict of fields to update (patch body)
    """
    old_score = existing.get("parse_quality_score")
    old_score_i = int(old_score) if isinstance(old_score, (int, float)) else compute_parse_quality(existing)
    new_score_i = int(incoming_row.get("parse_quality_score") or 0)
    upgrade = force_upgrade or (new_score_i > old_score_i)

    patch: Dict[str, Any] = {}

    # Status should always be updated when explicitly detected (even if overall parse quality didn't improve).
    incoming_status = incoming_row.get("status")
    if incoming_status is not None:
        s = str(incoming_status).strip().lower()
        if s in {"open", "closed"} and str(existing.get("status") or "").strip().lower() != s:
            patch["status"] = s

    # Update "latest seen" identifiers for UI linking/debugging only when
    # the incoming record is at least as new as the existing seen timestamp,
    # or when the existing pointer is missing. This prevents an older original
    # post (processed after a bump/repost) from clobbering the pointer to the
    # more recent repost/bump message.
    try:
        existing_source = None
        if isinstance(existing.get("source_last_seen"), str) and existing.get("source_last_seen"):
            existing_source = parse_iso_dt(existing.get("source_last_seen"))
        elif isinstance(existing.get("published_at"), str) and existing.get("published_at"):
            existing_source = parse_iso_dt(existing.get("published_at"))
        elif isinstance(existing.get("last_seen"), str) and existing.get("last_seen"):
            existing_source = parse_iso_dt(existing.get("last_seen"))

        incoming_source = None
        if isinstance(incoming_row.get("source_last_seen"), str) and incoming_row.get("source_last_seen"):
            incoming_source = parse_iso_dt(incoming_row.get("source_last_seen"))
        elif isinstance(incoming_row.get("published_at"), str) and incoming_row.get("published_at"):
            incoming_source = parse_iso_dt(incoming_row.get("published_at"))

        for k in ("message_id", "message_link"):
            # If existing pointer is missing, allow update.
            existing_ptr = existing.get(k)
            incoming_ptr = incoming_row.get(k)
            if incoming_ptr is None:
                continue
            allow = False
            if not existing_ptr:
                allow = True
            elif incoming_source is None and existing_source is None:
                # Unknown timestamps, be conservative and do not overwrite.
                allow = False
            elif incoming_source is not None and existing_source is not None:
                try:
                    allow = incoming_source >= existing_source
                except Exception:
                    allow = False
            elif incoming_source is not None and existing_source is None:
                allow = True

            if allow:
                patch[k] = incoming_ptr
    except Exception:
        # Fallback to the previous conservative behavior on any unexpected error.
        for k in ("message_id", "message_link"):
            if k in incoming_row and incoming_row.get(k) is not None:
                patch[k] = incoming_row[k]

    # Only update heavy/raw blobs when we're upgrading quality.
    if upgrade:
        for k in ("raw_text", "canonical_json", "meta"):
            if k in incoming_row and incoming_row.get(k) is not None:
                patch[k] = incoming_row[k]

    for k, v in incoming_row.items():
        if k in {"external_id", "agency_telegram_channel_name", "agency_id", "parse_quality_score"}:
            continue
        if v is None:
            continue

        if upgrade:
            patch[k] = v
            continue

        cur = existing.get(k)
        if cur is None:
            patch[k] = v
            continue
        if isinstance(cur, str) and not cur.strip():
            patch[k] = v
            continue
        if isinstance(cur, list) and len(cur) == 0:
            patch[k] = v
            continue

    # Union signal rollups when not upgrading (preserve + add).
    if not upgrade:
        for key in ("signals_subjects", "signals_levels", "signals_specific_student_levels", "signals_streams"):
            existing_vals = coerce_text_list(existing.get(key) or [])
            incoming_vals = coerce_text_list(incoming_row.get(key) or [])
            if incoming_vals:
                combined = coerce_text_list(existing_vals + incoming_vals)
                if combined != existing_vals:
                    patch[key] = combined

    # Update score to reflect the merged record.
    merged_preview = dict(existing)
    merged_preview.update(patch)
    patch["parse_quality_score"] = compute_parse_quality(merged_preview)

    # Freshness tier is optional; enable only after applying the DB migration.
    if _freshness_enabled():
        patch["freshness_tier"] = "green"

    return patch
