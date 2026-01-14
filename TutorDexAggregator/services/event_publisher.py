"""
Event Publisher Service

Handles side-effect operations like duplicate detection and metrics publishing.
These operations run asynchronously and do not block the main persistence flow.
"""
import logging
import threading
from typing import TYPE_CHECKING

from shared.config import load_aggregator_config

if TYPE_CHECKING:
    from utils.supabase_client import SupabaseConfig


logger = logging.getLogger("event_publisher")
_CFG = load_aggregator_config()


def should_run_duplicate_detection() -> bool:
    """Check if duplicate detection should run (environment variable)"""
    return bool(_CFG.duplicate_detection_enabled)


def run_duplicate_detection_async(assignment_id: int, cfg: "SupabaseConfig"):
    """
    Run duplicate detection asynchronously (non-blocking).
    
    This runs in a separate thread to avoid blocking the main persist operation.
    Failures in duplicate detection do not affect assignment persistence.
    
    Args:
        assignment_id: Database assignment ID
        cfg: Supabase configuration
    """
    def _detect():
        try:
            try:
                from duplicate_detector import detect_duplicates_for_assignment
            except Exception:
                from TutorDexAggregator.duplicate_detector import detect_duplicates_for_assignment
            
            group_id = detect_duplicates_for_assignment(
                assignment_id,
                supabase_url=cfg.url,
                supabase_key=cfg.key
            )
            
            if group_id:
                logger.info(
                    f"Duplicate detection completed for assignment {assignment_id}",
                    extra={"assignment_id": assignment_id, "duplicate_group_id": group_id}
                )
            else:
                logger.debug(
                    f"No duplicates found for assignment {assignment_id}",
                    extra={"assignment_id": assignment_id}
                )
        except Exception as e:
            logger.warning(
                f"Duplicate detection failed for assignment {assignment_id}: {e}",
                extra={"assignment_id": assignment_id, "error": str(e)}
            )
    
    # Run in background thread (non-blocking)
    thread = threading.Thread(target=_detect, daemon=True)
    thread.start()
