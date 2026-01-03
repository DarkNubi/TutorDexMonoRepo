import re
from typing import Optional


_WS_RE = re.compile(r"\s+")

_REMARKS_MARKER_RE = re.compile(
    r"(?im)^\s*(remarks|remark|notes|note|additional\s+requirement|additional\s+requirements|comment|comments)\s*:",
)


def normalize_ws_for_match(text: str) -> str:
    return _WS_RE.sub(" ", str(text or "")).strip().lower()


def has_remarks_marker(raw_text: str) -> bool:
    return bool(_REMARKS_MARKER_RE.search(str(raw_text or "")))


def substring_supported(raw_text: str, value: Optional[str]) -> bool:
    if value is None:
        return True
    needle = normalize_ws_for_match(value)
    if not needle:
        return True
    hay = normalize_ws_for_match(raw_text)
    return needle in hay


def rate_is_quote_like(rate_raw_text: Optional[str]) -> bool:
    s = normalize_ws_for_match(rate_raw_text or "")
    if not s:
        return False

    # Strong indicators (safe).
    strong = [
        "tutor to quote",
        "please quote",
        "pls quote",
        "market rate",
        "mkt rate",
        "quote",
        "tbc",
    ]
    if any(x in s for x in strong):
        return True

    # Weaker indicators: only treat as quote-like when obviously about rate.
    if "negotiable" in s and ("rate" in s or "$" in s or "per hour" in s or "/hr" in s or "p/h" in s):
        return True

    return False

