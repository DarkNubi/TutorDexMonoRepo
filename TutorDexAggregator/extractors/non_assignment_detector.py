"""
Non-assignment message detector.

Identifies messages that should be filtered out early in the extraction pipeline
before expensive LLM processing. This includes:
- Status-only messages (CLOSED, TAKEN, FILLED)
- Redirect messages (reposted below, see above)
- Administrative/promotional messages (Calling All Tutors, job lists)

Design principles:
- Conservative: when in doubt, let the message through (false negatives OK, false positives bad)
- Fast: uses simple regex and heuristics, no LLM calls
- Observable: returns detailed reasons for debugging
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Any, Tuple


class MessageType(str, Enum):
    """Types of non-assignment messages we can detect."""

    STATUS_ONLY = "status_only"  # Just status like "CLOSED" or "TAKEN"
    REDIRECT = "redirect"  # Redirect to another message
    ADMINISTRATIVE = "administrative"  # Announcements, promotions, job lists


@dataclass
class DetectionResult:
    """Result of non-assignment detection."""

    is_non_assignment: bool
    message_type: MessageType | None
    details: str
    confidence: float  # 0.0 to 1.0


# Patterns for status-only messages
_STATUS_PATTERNS = [
    re.compile(r"^\s*assignment\s+(closed|taken|filled|expired)\s*$", re.IGNORECASE),
    re.compile(r"^\s*(closed|taken|filled|expired)\s*$", re.IGNORECASE),
    re.compile(r"^\s*status\s*:\s*(closed|taken|filled|expired)\s*$", re.IGNORECASE),
]

# Patterns for redirect messages
_REDIRECT_PATTERNS = [
    re.compile(r"has\s+been\s+reposted\s+(below|above)", re.IGNORECASE),
    re.compile(r"reposted\s+(below|above)", re.IGNORECASE),
    re.compile(r"see\s+(above|below|message\s+above|message\s+below)", re.IGNORECASE),
    re.compile(r"refer\s+to\s+(above|below|previous|next)\s+(message|post)", re.IGNORECASE),
    re.compile(r"assignment\s+\d+\s+has\s+been\s+reposted", re.IGNORECASE),
]

# Patterns for administrative/promotional messages
_ADMIN_PATTERNS = [
    re.compile(r"calling\s+all\s+tutors", re.IGNORECASE),
    re.compile(r"new\s+job\s+opportunities", re.IGNORECASE),
    re.compile(r"many\s+(tuition\s+)?job\s+opportunities", re.IGNORECASE),
    re.compile(r"important\s+announcement", re.IGNORECASE),
    re.compile(r"agency\s+(will\s+be\s+)?(closed|opening)", re.IGNORECASE),
]

# Markers that suggest this is a real assignment, not administrative
_ASSIGNMENT_MARKERS = [
    "job id:",
    "job code:",
    "assignment code:",
    "hourly rate:",
    "🔻",  # Common bullet point in assignments
    "lesson per week:",
    "student's gender:",
    "time:",
    "location/area:",
    "level and subject",
]


def _normalize_text(text: Any) -> str:
    """Normalize text for pattern matching."""
    try:
        return str(text or "").strip()
    except Exception:
        return ""


def _count_assignment_markers(text: str) -> int:
    """Count how many assignment markers are present in the text."""
    text_lower = text.lower()
    count = 0
    for marker in _ASSIGNMENT_MARKERS:
        if marker in text_lower:
            count += 1
    return count


def _is_very_short(text: str) -> bool:
    """Check if text is suspiciously short for an assignment."""
    lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
    char_count = len(text.strip())

    # Less than 3 non-empty lines OR less than 50 characters
    return len(lines) < 3 or char_count < 50


def _detect_status_only(text: str) -> Tuple[bool, str]:
    """
    Detect status-only messages like "ASSIGNMENT CLOSED".

    Returns (is_status_only, reason).
    """
    text_stripped = text.strip()

    # Must be very short to be status-only
    if not _is_very_short(text_stripped):
        return False, ""

    # Must not have assignment markers (this is a status update, not an assignment)
    marker_count = _count_assignment_markers(text_stripped)
    if marker_count >= 2:
        return False, ""

    # Check patterns
    for pattern in _STATUS_PATTERNS:
        if pattern.search(text_stripped):
            return True, f"Status-only message detected: {pattern.pattern}"

    return False, ""


def _detect_redirect(text: str) -> Tuple[bool, str]:
    """
    Detect redirect messages like "Assignment X has been reposted below".

    Returns (is_redirect, reason).
    """
    text_stripped = text.strip()

    # Must be relatively short
    if not _is_very_short(text_stripped):
        return False, ""

    # Must not have strong assignment markers
    marker_count = _count_assignment_markers(text_stripped)
    if marker_count >= 3:
        return False, ""

    # Check patterns
    for pattern in _REDIRECT_PATTERNS:
        if pattern.search(text_stripped):
            return True, f"Redirect message detected: {pattern.pattern}"

    return False, ""


def _detect_administrative(text: str) -> Tuple[bool, str]:
    """
    Detect administrative/promotional messages.

    Returns (is_administrative, reason).
    """
    text_lower = text.lower()

    # Check for promotional patterns
    for pattern in _ADMIN_PATTERNS:
        if pattern.search(text):
            # Additional check: if this looks like a list of multiple assignments, flag it
            # Count how many times "apply now" or similar appears (indicates compilation/list)
            apply_count = text_lower.count("apply now")
            checkmark_count = text_lower.count("✅")
            bullet_count = text_lower.count("✅") + text_lower.count("•")

            # If it's a promotional message with many items, flag as administrative
            if apply_count >= 3 or checkmark_count >= 3 or bullet_count >= 5:
                return True, f"Promotional list message: {pattern.pattern}, {bullet_count} bullets"

            # For other admin patterns like announcements, check that it's not an assignment
            marker_count = _count_assignment_markers(text)
            if marker_count < 3:  # Real assignments typically have 3+ markers
                return True, f"Administrative message: {pattern.pattern}"

    return False, ""


def is_non_assignment(text: Any) -> Tuple[bool, MessageType | None, str]:
    """
    Detect if a message is not an assignment and should be filtered early.

    Args:
        text: Raw message text

    Returns:
        Tuple of (is_non_assignment, message_type, details)
        - is_non_assignment: True if this should be filtered out
        - message_type: Type of non-assignment message (or None)
        - details: Human-readable explanation

    Examples:
        >>> is_non_assignment("ASSIGNMENT CLOSED")
        (True, MessageType.STATUS_ONLY, "Status-only message detected: ...")

        >>> is_non_assignment("Assignment 123 has been reposted below.")
        (True, MessageType.REDIRECT, "Redirect message detected: ...")

        >>> is_non_assignment("Valid assignment with Job ID: ABC123...")
        (False, None, "")
    """
    normalized = _normalize_text(text)

    # Empty or whitespace-only: let it be handled elsewhere
    if not normalized:
        return False, None, ""

    # Try status-only detection
    is_status, status_reason = _detect_status_only(normalized)
    if is_status:
        return True, MessageType.STATUS_ONLY, status_reason

    # Try redirect detection
    is_redirect, redirect_reason = _detect_redirect(normalized)
    if is_redirect:
        return True, MessageType.REDIRECT, redirect_reason

    # Try administrative detection
    is_admin, admin_reason = _detect_administrative(normalized)
    if is_admin:
        return True, MessageType.ADMINISTRATIVE, admin_reason

    # Not detected as non-assignment
    return False, None, ""


def detection_meta(is_non: bool, msg_type: MessageType | None, details: str) -> dict[str, Any]:
    """
    Format detection result as metadata dict for logging/storage.

    Args:
        is_non: Result from is_non_assignment
        msg_type: Message type from is_non_assignment
        details: Details from is_non_assignment

    Returns:
        Dict with keys: ok, is_non_assignment, message_type, details
    """
    return {
        "ok": True,
        "is_non_assignment": bool(is_non),
        "message_type": str(msg_type) if msg_type else None,
        "details": str(details or ""),
    }
