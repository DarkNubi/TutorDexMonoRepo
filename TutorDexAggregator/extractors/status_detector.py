import re
from dataclasses import dataclass
from typing import Any, Dict, Optional


def _norm_channel(value: Any) -> str:
    s = str(value or "").strip().lower()
    if not s:
        return ""
    s = s.replace("https://", "").replace("http://", "")
    if s.startswith("@"):
        s = s[1:]
    if s.startswith("t.me/"):
        s = s.split("t.me/", 1)[-1]
    return s.strip().strip("/")


def _norm_text(value: Any) -> str:
    try:
        return str(value or "")
    except Exception:
        return ""


@dataclass(frozen=True)
class StatusDetection:
    status: str  # "open" | "closed"
    rule: str
    evidence: str
    confidence: float


_ALLOWLIST = {
    "elitetutorsg",
    "tutoranywhr",
    "eduaidtuition",
}


_RE_ELITE = re.compile(r"(?im)^\s*status\s*:\s*.*\b(open|closed)\b", re.IGNORECASE)
_RE_TUTORANYWHR = re.compile(r"(?im)^[^a-z0-9]*application\s*status\s*:\s*(open|closed)\b", re.IGNORECASE)
_RE_EDUAID_CLOSED = re.compile(r"(?im)\bassignment\s+closed\b", re.IGNORECASE)
_RE_EDUAID_NEW = re.compile(r"(?im)\bnew\s+assignment\b", re.IGNORECASE)


def detect_status(*, raw_text: Any, channel_link: Any = None, channel_username: Any = None) -> Optional[StatusDetection]:
    """
    Deterministic, opt-in status detection for a small set of agencies that reliably publish status.
    Returns None when:
    - channel is not allowlisted
    - no explicit marker is found
    """
    channel = _norm_channel(channel_username) or _norm_channel(channel_link)
    if channel not in _ALLOWLIST:
        return None

    text = _norm_text(raw_text)
    if not text.strip():
        return None

    if channel == "elitetutorsg":
        m = _RE_ELITE.search(text)
        if not m:
            return None
        s = m.group(1).strip().lower()
        return StatusDetection(status="closed" if s == "closed" else "open", rule="elitetutorsg:status_line", evidence=m.group(0).strip()[:120], confidence=0.95)

    if channel == "tutoranywhr":
        m = _RE_TUTORANYWHR.search(text)
        if not m:
            return None
        s = m.group(1).strip().lower()
        return StatusDetection(status="closed" if s == "closed" else "open", rule="tutoranywhr:application_status", evidence=m.group(0).strip()[:120], confidence=0.95)

    if channel == "eduaidtuition":
        m = _RE_EDUAID_CLOSED.search(text)
        if m:
            return StatusDetection(status="closed", rule="eduaidtuition:assignment_closed", evidence=m.group(0).strip()[:120], confidence=0.9)
        m2 = _RE_EDUAID_NEW.search(text)
        if m2:
            return StatusDetection(status="open", rule="eduaidtuition:new_assignment", evidence=m2.group(0).strip()[:120], confidence=0.75)
        return None

    return None


def detection_meta(d: StatusDetection) -> Dict[str, Any]:
    return {
        "ok": True,
        "status": d.status,
        "rule": d.rule,
        "confidence": float(d.confidence),
        "evidence": d.evidence,
    }
