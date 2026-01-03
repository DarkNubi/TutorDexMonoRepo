import os
import re
from typing import Any, Optional, Tuple, List


LABEL_RE = re.compile(r"(slot\s*[a-z]\s*:|assignment\s*\d+|job\s*\d+|available\s*assignment):", re.I)
CODE_RE = re.compile(r"(code|assignment|job|id)\s*[:#]\s*\w+", re.I)
POSTAL_RE = re.compile(r"\b\d{6}\b")
URL_RE = re.compile(r"https?://|t\.me/|www\.", re.I)


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def load_compilation_thresholds() -> dict[str, int]:
    """
    Default thresholds used by the queue worker pipeline.
    Override via env vars if needed.
    """
    return {
        "code_hits": _env_int("COMPILATION_CODE_HITS", 2),
        "label_hits": _env_int("COMPILATION_LABEL_HITS", 2),
        "postal_hits": _env_int("COMPILATION_POSTAL_HITS", 2),
        "url_hits": _env_int("COMPILATION_URL_HITS", 2),
        "block_count": _env_int("COMPILATION_BLOCK_COUNT", 3),
    }


def is_compilation(text: str) -> Tuple[bool, List[str]]:
    """
    Heuristic detector for compilation/multi-assignment posts.
    Returns (is_compilation, triggered_checks).
    """
    if not text:
        return False, []

    thresh = load_compilation_thresholds()
    code_hits = len(CODE_RE.findall(text))
    label_hits = len(LABEL_RE.findall(text))
    postal_codes = {c.strip() for c in POSTAL_RE.findall(text) if str(c).strip()}
    postal_hits = len(postal_codes)
    url_hits = len(URL_RE.findall(text))
    blocks = [b for b in re.split(r"\n{2,}", text) if b.strip()]
    block_count = len(blocks)

    triggered: List[str] = []
    if code_hits >= thresh["code_hits"]:
        triggered.append(f"Multiple assignment codes detected ({code_hits} codes found, threshold: {thresh['code_hits']})")
    if label_hits >= thresh["label_hits"] and block_count >= 2:
        triggered.append(f"Multiple labeled sections ({label_hits} labels found, threshold: {thresh['label_hits']}, {block_count} blocks)")
    if postal_hits >= thresh["postal_hits"]:
        triggered.append(
            f"Multiple unique postal codes detected ({postal_hits} unique postal codes found, threshold: {thresh['postal_hits']})"
        )
    if url_hits >= thresh["url_hits"]:
        triggered.append(f"Multiple URLs detected ({url_hits} URLs found, threshold: {thresh['url_hits']})")
    if block_count >= thresh["block_count"] and label_hits >= 1:
        triggered.append(f"Multiple content blocks ({block_count} blocks found, threshold: {thresh['block_count']}, with {label_hits} labels)")

    return (len(triggered) > 0), triggered
