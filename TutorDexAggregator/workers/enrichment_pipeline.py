"""
Enrichment pipeline for the extraction worker.

Handles deterministic enrichment: signals, time availability, postal codes, hard validation.
"""

import logging
from typing import Any, Dict, Optional, Tuple

from workers.utils import coerce_list_of_str, extract_sg_postal_codes

logger = logging.getLogger("enrichment_pipeline")


def _build_signals_summary(signals: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build summary of signals for metadata.
    
    Args:
        signals: Signals dict
        
    Returns:
        Summary dict with counts and flags
    """
    if not isinstance(signals, dict):
        return {
            "subjects": 0,
            "levels": 0,
            "academic_requests": 0,
            "ambiguous": False,
        }
    
    academic_requests = signals.get("academic_requests")
    confidence_flags = signals.get("confidence_flags") or {}
    
    return {
        "subjects": len(signals.get("subjects") or []),
        "levels": len(signals.get("levels") or []),
        "academic_requests": len(academic_requests) if isinstance(academic_requests, list) else 0,
        "ambiguous": bool(confidence_flags.get("ambiguous_academic_mapping")),
    }


def fill_postal_code_from_text(parsed: Dict[str, Any], raw_text: str) -> Dict[str, Any]:
    """
    Best-effort, deterministic enrichment for postal codes.
    
    - Ensures `parsed["postal_code"]` is a list[str] when explicit 6-digit SG codes exist.
    - Never guesses a postal code from an address (no external geocoding).
    
    Args:
        parsed: Parsed assignment dict
        raw_text: Raw message text
        
    Returns:
        Updated parsed dict with postal codes
    """
    if not isinstance(parsed, dict):
        return {}
    
    existing = coerce_list_of_str(parsed.get("postal_code"))
    if existing:
        parsed["postal_code"] = existing
        return parsed
    
    codes = extract_sg_postal_codes(raw_text)
    if codes:
        parsed["postal_code"] = codes
    else:
        parsed["postal_code"] = None
    
    return parsed


def apply_postal_code_estimated(
    parsed: Dict[str, Any],
    raw_text: str,
    estimate_func: Any,
    enabled: bool
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """
    Apply postal code estimation if enabled.
    
    Args:
        parsed: Parsed assignment dict
        raw_text: Raw message text
        estimate_func: Function to call for estimation
        enabled: Whether estimation is enabled
        
    Returns:
        Tuple of (updated_parsed, estimation_metadata)
    """
    if not enabled:
        return parsed, None
    
    postal_estimated_meta: Optional[Dict[str, Any]] = None
    
    try:
        res = estimate_func(parsed, raw_text)
        if res and hasattr(res, "estimated") and hasattr(res, "meta"):
            if isinstance(parsed, dict):
                parsed["postal_code_estimated"] = res.estimated
            postal_estimated_meta = dict(res.meta or {})
            postal_estimated_meta["estimated"] = res.estimated
    except Exception as e:
        postal_estimated_meta = {"ok": False, "error": str(e)}
    
    return parsed, postal_estimated_meta


def apply_deterministic_time(
    parsed: Dict[str, Any],
    raw_text: str,
    normalized_text: str,
    extract_func: Any,
    enabled: bool
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """
    Apply deterministic time availability extraction if enabled.
    
    Overwrites LLM output when enabled.
    
    Args:
        parsed: Parsed assignment dict
        raw_text: Raw message text
        normalized_text: Normalized message text
        extract_func: Function to call for extraction
        enabled: Whether extraction is enabled
        
    Returns:
        Tuple of (updated_parsed, extraction_metadata)
    """
    if not enabled:
        return parsed, None
    
    time_meta: Optional[Dict[str, Any]] = None
    
    try:
        det_ta, det_meta = extract_func(raw_text=raw_text, normalized_text=normalized_text)
        if isinstance(parsed, dict):
            parsed["time_availability"] = det_ta
        time_meta = {"ok": True}
        if isinstance(det_meta, dict):
            time_meta.update(det_meta)
    except Exception as e:
        time_meta = {"ok": False, "error": str(e)}
    
    return parsed, time_meta


def apply_hard_validation(
    parsed: Dict[str, Any],
    raw_text: str,
    normalized_text: str,
    validate_func: Any,
    mode: str
) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    """
    Apply hard validation if enabled.
    
    Modes:
    - "off": Skip validation
    - "report": Report violations but don't modify
    - "enforce": Apply fixes from validator
    
    Args:
        parsed: Parsed assignment dict
        raw_text: Raw message text
        normalized_text: Normalized message text
        validate_func: Function to call for validation
        mode: Validation mode
        
    Returns:
        Tuple of (updated_parsed, validation_metadata)
    """
    if mode == "off":
        return parsed, None
    
    hard_meta: Optional[Dict[str, Any]] = None
    
    try:
        cleaned, violations = validate_func(parsed or {}, raw_text=raw_text, normalized_text=normalized_text)
        hard_meta = {
            "mode": mode,
            "violations_count": int(len(violations)),
            "violations": violations[:50],  # Limit to 50 for metadata
        }
        if mode == "enforce":
            parsed = cleaned
    except Exception as e:
        hard_meta = {"mode": mode, "error": str(e)}
    
    return parsed, hard_meta


def build_signals(
    parsed: Dict[str, Any],
    raw_text: str,
    normalized_text: str,
    signals_func: Any,
    enabled: bool
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Build deterministic signals if enabled.
    
    Signals include: subjects, levels, academic requests, tutor types, rates.
    Stored in metadata only, never breaks the job.
    
    Args:
        parsed: Parsed assignment dict
        raw_text: Raw message text
        normalized_text: Normalized message text
        signals_func: Function to call for signal building
        enabled: Whether signal building is enabled
        
    Returns:
        Tuple of (signals_dict, signals_metadata)
    """
    if not enabled:
        return None, None
    
    signals_meta: Optional[Dict[str, Any]] = None
    signals: Optional[Dict[str, Any]] = None
    
    try:
        signals, err = signals_func(parsed=parsed or {}, raw_text=raw_text, normalized_text=normalized_text)
        
        if err:
            signals_meta = {"ok": False, "error": err}
        else:
            signals_meta = {
                "ok": True,
                "signals": signals,
                "summary": _build_signals_summary(signals),
            }
    except Exception as e:
        signals_meta = {"ok": False, "error": str(e)}
    
    return signals, signals_meta


def run_enrichment_pipeline(
    parsed: Dict[str, Any],
    raw_text: str,
    normalized_text: str,
    config: Dict[str, Any],
    functions: Dict[str, Any]
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Run the complete enrichment pipeline.
    
    Steps:
    1. Fill postal code from text (always)
    2. Estimate postal codes (if enabled)
    3. Extract deterministic time availability (if enabled)
    4. Apply hard validation (if mode != "off")
    5. Build deterministic signals (if enabled)
    
    Args:
        parsed: Parsed assignment dict
        raw_text: Raw message text
        normalized_text: Normalized message text
        config: Configuration dict with enable flags
        functions: Dict of functions to call for each step
        
    Returns:
        Tuple of (enriched_parsed, metadata_dict)
    """
    # Step 1: Fill postal code from text (always)
    parsed = fill_postal_code_from_text(parsed, raw_text)
    
    # Step 2: Postal code estimation
    parsed, postal_estimated_meta = apply_postal_code_estimated(
        parsed,
        raw_text,
        functions.get("estimate_postal_codes"),
        config.get("enable_postal_code_estimated", False)
    )
    
    # Step 3: Deterministic time availability
    parsed, time_meta = apply_deterministic_time(
        parsed,
        raw_text,
        normalized_text,
        functions.get("extract_time_availability"),
        config.get("use_deterministic_time", False)
    )
    
    # Step 4: Hard validation
    parsed, hard_meta = apply_hard_validation(
        parsed,
        raw_text,
        normalized_text,
        functions.get("hard_validate"),
        config.get("hard_validate_mode", "off")
    )
    
    # Step 5: Build signals
    signals, signals_meta = build_signals(
        parsed,
        raw_text,
        normalized_text,
        functions.get("build_signals"),
        config.get("enable_deterministic_signals", False)
    )
    
    # Combine metadata
    metadata = {
        "postal_code_estimated": postal_estimated_meta,
        "time_deterministic": time_meta,
        "hard_validation": hard_meta,
        "signals": signals_meta,
    }
    
    return parsed, metadata
