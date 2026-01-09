from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

try:
    from extractors.academic_requests import parse_academic_requests  # type: ignore
except Exception:
    from TutorDexAggregator.extractors.academic_requests import parse_academic_requests  # type: ignore
try:
    from extractors.tutor_types import extract_tutor_types  # type: ignore
except Exception:
    from TutorDexAggregator.extractors.tutor_types import extract_tutor_types  # type: ignore
try:
    from observability_metrics import worker_tutor_types_extracted_total, worker_tutor_types_low_confidence_total, worker_tutor_types_unmapped_total  # type: ignore
except Exception:
    worker_tutor_types_extracted_total = None  # type: ignore
    worker_tutor_types_low_confidence_total = None  # type: ignore
    worker_tutor_types_unmapped_total = None  # type: ignore


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        return s or None
    s = str(value).strip()
    return s or None


def build_signals(
    *,
    parsed: Dict[str, Any],
    raw_text: str,
    normalized_text: Optional[str],
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Returns (signals, error). Never raises.

    Signals are deterministic matching metadata stored in `telegram_extractions.meta.signals`.
    """
    try:
        display = _safe_str((parsed or {}).get("academic_display_text"))
        source = "academic_display_text" if display else ("normalized_text" if _safe_str(normalized_text) else "raw_text")
        text = display or _safe_str(normalized_text) or _safe_str(raw_text) or ""

        parsed_signals = parse_academic_requests(text=text)
        try:
            tt = extract_tutor_types(text=text, parsed=parsed_signals)
            if isinstance(tt, dict):
                # Metrics (best-effort): count extracted types and low-confidence/unmapped
                try:
                    types = tt.get("tutor_types") if isinstance(tt.get("tutor_types"), list) else []
                    lb = tt.get("rate_breakdown") if isinstance(tt.get("rate_breakdown"), dict) else {}
                    if worker_tutor_types_extracted_total is not None:
                        worker_tutor_types_extracted_total.labels(channel="unknown", pipeline_version="-", schema_version="-").inc(len(types))
                    # low-confidence/unmapped heuristics
                    low = 0
                    unmapped = 0
                    for t in types:
                        conf = None
                        try:
                            conf = float(t.get("confidence")) if t.get("confidence") is not None else None
                        except Exception:
                            conf = None
                        if conf is None or conf < 0.6:
                            low += 1
                        if (t.get("canonical") or "").lower() == "unknown":
                            unmapped += 1
                    if worker_tutor_types_low_confidence_total is not None and low:
                        worker_tutor_types_low_confidence_total.labels(channel="unknown", pipeline_version="-", schema_version="-").inc(low)
                    if worker_tutor_types_unmapped_total is not None and unmapped:
                        worker_tutor_types_unmapped_total.labels(channel="unknown", pipeline_version="-", schema_version="-").inc(unmapped)
                except Exception:
                    pass
                parsed_signals.update(tt)
        except Exception:
            # non-fatal: keep parsed_signals as-is
            pass
        signals = {
            "schema_version": 1,
            "source": source,
            "text_chars": len(text),
            **parsed_signals,
        }
        return signals, None
    except Exception as e:
        return None, str(e)
