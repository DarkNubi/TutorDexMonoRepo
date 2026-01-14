"""
Validation pipeline for the extraction worker.

Handles schema validation and quality checks.
"""

import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger("validation_pipeline")


def validate_schema(
    parsed: Dict[str, Any],
    validate_func: Any
) -> Tuple[bool, Optional[Any]]:
    """
    Validate parsed assignment against schema.
    
    Args:
        parsed: Parsed assignment dict
        validate_func: Function to call for validation (e.g., validate_parsed_assignment)
        
    Returns:
        Tuple of (is_valid, errors)
    """
    try:
        ok, errors = validate_func(parsed or {})
        return ok, errors
    except Exception as e:
        logger.error(f"Schema validation error: {e}")
        return False, [str(e)]


def increment_quality_missing(
    field: str,
    channel: str,
    metrics: Optional[Dict[str, Any]] = None
) -> None:
    """
    Increment quality metric for missing field.
    
    Args:
        field: Field name
        channel: Channel name
        metrics: Metrics dict with counters
    """
    if not metrics or "assignment_quality_missing_field_total" not in metrics:
        return
    
    try:
        metrics["assignment_quality_missing_field_total"].labels(
            field=field,
            channel=channel,
            pipeline_version=metrics.get("pipeline_version", ""),
            schema_version=metrics.get("schema_version", ""),
        ).inc()
    except Exception:
        pass


def increment_quality_inconsistency(
    kind: str,
    channel: str,
    metrics: Optional[Dict[str, Any]] = None
) -> None:
    """
    Increment quality metric for inconsistency.
    
    Args:
        kind: Inconsistency kind
        channel: Channel name
        metrics: Metrics dict with counters
    """
    if not metrics or "assignment_quality_inconsistency_total" not in metrics:
        return
    
    try:
        metrics["assignment_quality_inconsistency_total"].labels(
            kind=kind,
            channel=channel,
            pipeline_version=metrics.get("pipeline_version", ""),
            schema_version=metrics.get("schema_version", ""),
        ).inc()
    except Exception:
        pass


def run_quality_checks(
    parsed: Dict[str, Any],
    signals: Optional[Dict[str, Any]],
    channel: str,
    metrics: Optional[Dict[str, Any]] = None
) -> None:
    """
    Run quality checks on parsed data and signals.
    
    Checks:
    - Missing subjects in signals
    - Missing levels in signals
    - Missing postal code
    - Missing academic display text
    - Inconsistency between headline and signals (IB, IGCSE)
    
    Args:
        parsed: Parsed assignment dict
        signals: Signals dict
        channel: Channel name
        metrics: Metrics dict with counters
    """
    p = parsed if isinstance(parsed, dict) else {}
    s = signals if isinstance(signals, dict) else {}
    
    # Check signals
    subjects = s.get("subjects") or []
    levels = s.get("levels") or []
    
    if not isinstance(subjects, list) or len(subjects) == 0:
        increment_quality_missing("signals_subjects", channel, metrics)
    
    if not isinstance(levels, list) or len(levels) == 0:
        increment_quality_missing("signals_levels", channel, metrics)
    
    # Check postal code
    postal = p.get("postal_code")
    if not (isinstance(postal, list) and any(str(x).strip() for x in postal)):
        increment_quality_missing("postal_code", channel, metrics)
    
    # Check academic display text
    academic = str(p.get("academic_display_text") or "")
    if not academic.strip():
        increment_quality_missing("academic_display_text", channel, metrics)
    
    # Check consistency between headline and signals
    headline = academic.lower()
    sig_levels = {str(x).strip() for x in levels} if isinstance(levels, list) else set()
    
    if "ib" in headline and "IB" not in sig_levels:
        increment_quality_inconsistency("headline_ib_no_signal", channel, metrics)
    
    if "igcse" in headline and "IGCSE" not in sig_levels:
        increment_quality_inconsistency("headline_igcse_no_signal", channel, metrics)
