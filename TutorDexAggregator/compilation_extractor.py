"""
Extract assignment codes from compilation messages.

Compilation messages contain multiple assignments in one post. Instead of parsing
each assignment fully, we extract just the assignment codes/IDs and use them to
bump the corresponding assignments in the database.

This is a lightweight operation that allows compilation messages to still contribute
to assignment freshness without expensive LLM parsing.
"""

from __future__ import annotations

import re
from typing import List, Set, Tuple


# Patterns to extract assignment codes from text
# These patterns look for common formats like:
# - "Job ID: ABC123"
# - "Assignment Code: XYZ789"
# - "Code: DEF456"
# - "#ABC123" or "Job #123"
_CODE_PATTERNS = [
    # Job/Assignment ID/Code with colon or hash
    re.compile(r"(?:job\s+(?:id|code|#)|assignment\s+(?:id|code|#))\s*[:\-]?\s*([A-Z0-9]+)", re.IGNORECASE),
    # Standalone code format (more restrictive to avoid false positives)
    re.compile(r"\b(?:id|code)\s*[:\-]?\s*([A-Z]{2,}[0-9]+)\b", re.IGNORECASE),
    # Hash tag format
    re.compile(r"#([A-Z]{2,}[0-9]+)\b", re.IGNORECASE),
]


def extract_assignment_codes(text: str) -> Tuple[List[str], dict]:
    """
    Extract assignment codes from a compilation message.
    
    Args:
        text: The raw message text (compilation post)
        
    Returns:
        Tuple of (codes_list, metadata_dict)
        - codes_list: List of unique assignment codes found (de-duplicated, preserving order)
        - metadata_dict: Diagnostic info about extraction (pattern matches, etc.)
        
    Examples:
        >>> text = "Job ID: ABC123\\nJob ID: XYZ789\\nJob ID: ABC123"
        >>> codes, meta = extract_assignment_codes(text)
        >>> codes
        ['ABC123', 'XYZ789']
        >>> meta['total_matches']
        3
    """
    if not text:
        return [], {"ok": False, "reason": "empty_text"}

    codes_found: List[str] = []
    seen: Set[str] = set()
    match_count = 0
    pattern_hits = {}

    # Try each pattern
    for pattern in _CODE_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            pattern_name = pattern.pattern[:50]  # Truncate for metadata
            pattern_hits[pattern_name] = len(matches)
            match_count += len(matches)

            for match in matches:
                # Normalize: uppercase, strip whitespace
                code = str(match).strip().upper()

                # Filter out very short codes (likely false positives)
                if len(code) < 3:
                    continue

                # Filter out pure numeric codes (likely not assignment codes)
                if code.isdigit():
                    continue

                # Add to list if not seen before
                if code not in seen:
                    seen.add(code)
                    codes_found.append(code)

    metadata = {
        "ok": True,
        "codes_count": len(codes_found),
        "total_matches": match_count,
        "patterns_hit": pattern_hits,
    }

    return codes_found, metadata


def should_process_compilation(codes: List[str], min_codes: int = 1) -> bool:
    """
    Determine if a compilation has enough valid codes to be worth processing.
    
    Args:
        codes: List of extracted codes
        min_codes: Minimum number of codes required (default: 1)
        
    Returns:
        True if compilation should be processed, False otherwise
    """
    return len(codes) >= min_codes
