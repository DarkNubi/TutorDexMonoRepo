"""
Job management for the extraction worker.

Handles:
- Claiming jobs from the extraction queue
- Updating job status (processing, ok, failed)
- Requeuing stale jobs
- Managing job metadata and attempts
"""

import logging
from typing import Any, Dict, List, Optional

from workers.supabase_operations import call_rpc, patch_table
from observability_metrics import worker_requeued_stale_jobs_total

logger = logging.getLogger("job_manager")


def claim_jobs(
    url: str,
    key: str,
    pipeline_version: str,
    limit: int,
    schema_version: str = ""
) -> List[Dict[str, Any]]:
    """
    Claim pending extraction jobs from the queue.
    
    Args:
        url: Supabase base URL
        key: Supabase API key
        pipeline_version: Pipeline version to claim jobs for
        limit: Maximum number of jobs to claim
        schema_version: For metrics labeling
        
    Returns:
        List of claimed job records
    """
    jobs = call_rpc(
        url,
        key,
        "claim_telegram_extractions",
        {"p_pipeline_version": pipeline_version, "p_limit": int(max(1, limit))},
        timeout=30,
        pipeline_version=pipeline_version,
        schema_version=schema_version
    )
    
    if not isinstance(jobs, list):
        return []
    
    return jobs


def mark_job_status(
    url: str,
    key: str,
    extraction_id: Any,
    status: str,
    error: Optional[Dict[str, Any]] = None,
    meta_patch: Optional[Dict[str, Any]] = None,
    existing_meta: Any = None,
    llm_model: Optional[str] = None,
    pipeline_version: str = "",
    schema_version: str = ""
) -> bool:
    """
    Update extraction job status.
    
    Args:
        url: Supabase base URL
        key: Supabase API key
        extraction_id: Job ID
        status: New status (e.g., "ok", "failed", "processing")
        error: Error details if status is "failed"
        meta_patch: Metadata to merge with existing meta
        existing_meta: Existing metadata from job
        llm_model: LLM model name for metadata
        pipeline_version: For metrics labeling
        schema_version: For metrics labeling
        
    Returns:
        True if successful, False otherwise
    """
    if extraction_id is None:
        return False
    
    merged_meta = merge_meta(existing_meta, meta_patch)
    if llm_model and isinstance(merged_meta, dict):
        merged_meta["llm_model"] = llm_model
    
    body: Dict[str, Any] = {"status": status}
    if merged_meta is not None:
        body["meta"] = merged_meta
    if error is not None:
        body["error"] = error
    
    return patch_table(
        url,
        key,
        "telegram_extractions",
        f"id=eq.{extraction_id}",
        body,
        timeout=30,
        pipeline_version=pipeline_version,
        schema_version=schema_version
    )


def merge_meta(existing: Any, patch: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Merge metadata patch with existing metadata.
    
    Args:
        existing: Existing metadata (can be dict or None)
        patch: Metadata patch to apply
        
    Returns:
        Merged metadata dict or None
    """
    if patch is None:
        if isinstance(existing, dict):
            return existing
        return None
    
    base: Dict[str, Any] = existing if isinstance(existing, dict) else {}
    merged = dict(base)
    merged.update(patch)
    return merged


def get_job_attempt(job: Dict[str, Any]) -> int:
    """
    Extract attempt count from job metadata.
    
    Args:
        job: Job record
        
    Returns:
        Attempt count (0 if not found or invalid)
    """
    meta = job.get("meta")
    if isinstance(meta, dict):
        try:
            return int(meta.get("attempt") or 0)
        except Exception:
            return 0
    return 0


def requeue_stale_jobs(
    url: str,
    key: str,
    older_than_seconds: int,
    pipeline_version: str = "",
    schema_version: str = ""
) -> Optional[int]:
    """
    Requeue jobs that have been stuck in 'processing' status.
    
    This prevents jobs from being lost if a worker crashes while processing.
    
    Args:
        url: Supabase base URL
        key: Supabase API key
        older_than_seconds: Requeue jobs processing for longer than this
        pipeline_version: For metrics labeling
        schema_version: For metrics labeling
        
    Returns:
        Number of jobs requeued, or None if RPC failed
    """
    try:
        result = call_rpc(
            url,
            key,
            "requeue_stale_extractions",
            {"p_older_than_seconds": int(older_than_seconds)},
            timeout=30,
            pipeline_version=pipeline_version,
            schema_version=schema_version
        )
        
        if isinstance(result, dict) and "count" in result:
            count = int(result["count"])
            if count > 0:
                logger.info(f"Requeued {count} stale jobs (older than {older_than_seconds}s)")
            return count
        
        return 0
    except Exception as e:
        logger.warning(f"Failed to requeue stale jobs: {e}")
        return None
