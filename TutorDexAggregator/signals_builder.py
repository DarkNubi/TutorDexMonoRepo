from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

try:
    from extractors.academic_requests import parse_academic_requests  # type: ignore
except Exception:
    from TutorDexAggregator.extractors.academic_requests import parse_academic_requests  # type: ignore


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
        signals = {
            "schema_version": 1,
            "source": source,
            "text_chars": len(text),
            **parsed_signals,
        }
        return signals, None
    except Exception as e:
        return None, str(e)

