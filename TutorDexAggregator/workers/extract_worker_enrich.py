from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from extractors.postal_code_estimated import estimate_postal_codes
from extractors.time_availability import extract_time_availability
from hard_validator import hard_validate
from signals_builder import build_signals
from workers.enrichment_pipeline import (
    apply_deterministic_time,
    apply_hard_validation,
    apply_postal_code_estimated,
    build_signals as build_signals_wrapper,
    fill_postal_code_from_text,
)
from workers.extract_worker_types import WorkerToggles


def enrich_payload(
    *,
    payload: Dict[str, Any],
    raw_text: str,
    normalized_text: str,
    norm_meta: Dict[str, Any],
    toggles: WorkerToggles,
) -> Tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    parsed_obj = payload.get("parsed") if isinstance(payload.get("parsed"), dict) else {}

    postal_meta: Optional[Dict[str, Any]] = None
    try:
        before = parsed_obj.get("postal_code")
        parsed_obj = fill_postal_code_from_text(parsed_obj, raw_text)
        after = parsed_obj.get("postal_code")
        postal_meta = {
            "ok": True,
            "changed": before != after,
            "postal_code_count": len(after) if isinstance(after, list) else (1 if isinstance(after, str) and after.strip() else 0),
        }
    except Exception as e:
        postal_meta = {"ok": False, "error": str(e)}

    parsed_obj, postal_estimated_meta = apply_postal_code_estimated(
        parsed_obj,
        raw_text,
        estimate_postal_codes,
        bool(toggles.enable_postal_code_estimated),
    )

    parsed_obj, time_meta = apply_deterministic_time(
        parsed_obj,
        raw_text,
        normalized_text,
        extract_time_availability,
        bool(toggles.use_deterministic_time),
    )

    parsed_obj, hard_meta = apply_hard_validation(
        parsed_obj,
        raw_text,
        normalized_text,
        hard_validate,
        str(toggles.hard_validate_mode or "report"),
    )

    _signals, signals_meta = build_signals_wrapper(
        parsed_obj,
        raw_text,
        normalized_text,
        build_signals,
        bool(toggles.enable_deterministic_signals),
    )

    payload["parsed"] = parsed_obj
    payload["meta"] = {
        "normalization": norm_meta,
        "postal_code_fill": postal_meta,
        "postal_code_estimated": postal_estimated_meta,
        "time_deterministic": time_meta,
        "hard_validation": hard_meta,
        "signals": signals_meta,
    }

    return postal_estimated_meta, time_meta, hard_meta, signals_meta

