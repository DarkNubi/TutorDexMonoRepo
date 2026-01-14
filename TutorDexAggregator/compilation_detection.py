import re
from typing import Any, Optional, Tuple, List

from shared.config import load_aggregator_config

try:
    # When running inside TutorDexAggregator (worker adds this dir to sys.path)
    from compilation_extractor import extract_assignment_codes
except Exception:  # pragma: no cover
    # When importing via namespace package in tests/tools
    from TutorDexAggregator.compilation_extractor import extract_assignment_codes

MULTI_ITEM_LABEL_RE = re.compile(r"(?im)^(?:\s*)(slot\s*[a-z]\s*:|assignment\s*\d+\s*:|job\s*\d+\s*:)\s*")
POSTAL_RE = re.compile(r"\b\d{6}\b")
URL_RE = re.compile(r"https?://|t\.me/|www\.", re.I)
APPLY_NOW_RE = re.compile(r"(?i)\bapply\s+now\b")


def load_compilation_thresholds() -> dict[str, int]:
    """
    Default thresholds used by the queue worker pipeline.
    Override via env vars if needed.
    """
    cfg = load_aggregator_config()
    distinct_codes = int(cfg.compilation_distinct_codes or 2)

    return {
        # Distinct assignment codes extracted via compilation_extractor (more reliable than counting "ID:" fields).
        "distinct_codes": distinct_codes,
        # Enumerated "slot A:", "assignment 1:", etc. Avoid generic section headers like "Available assignment:".
        "label_hits": int(cfg.compilation_label_hits or 2),
        "postal_hits": int(cfg.compilation_postal_hits or 2),
        "url_hits": int(cfg.compilation_url_hits or 2),
        # A conservative default: many single-assignment posts are 3 blocks (title/details/footer).
        "block_count": int(cfg.compilation_block_count or 5),
        # "Apply now" repeats frequently in compilation/list posts.
        "apply_now_hits": int(cfg.compilation_apply_now_hits or 2),
    }


def is_compilation(text: str) -> Tuple[bool, List[str]]:
    """
    Heuristic detector for compilation/multi-assignment posts.
    Returns (is_compilation, triggered_checks).
    """
    if not text:
        return False, []

    thresh = load_compilation_thresholds()
    codes, _meta = extract_assignment_codes(text)
    distinct_codes = len({str(c).strip().upper() for c in (codes or []) if str(c).strip()})
    label_hits = len(MULTI_ITEM_LABEL_RE.findall(text))
    postal_codes = {c.strip() for c in POSTAL_RE.findall(text) if str(c).strip()}
    postal_hits = len(postal_codes)
    url_hits = len(URL_RE.findall(text))
    blocks = [b for b in re.split(r"\n{2,}", text) if b.strip()]
    block_count = len(blocks)
    apply_now_hits = len(APPLY_NOW_RE.findall(text))

    triggered: List[str] = []
    if distinct_codes >= thresh["distinct_codes"]:
        triggered.append(f"Multiple distinct assignment codes ({distinct_codes} >= {thresh['distinct_codes']})")
    if label_hits >= thresh["label_hits"] and block_count >= 2:
        triggered.append(f"Multiple enumerated items ({label_hits} >= {thresh['label_hits']}, blocks={block_count})")
    if postal_hits >= thresh["postal_hits"]:
        # Keep this signal, but require some evidence of multiple items to avoid false positives.
        if distinct_codes >= 2 or label_hits >= 2 or apply_now_hits >= 2:
            triggered.append(f"Multiple unique postal codes ({postal_hits} >= {thresh['postal_hits']})")
    if url_hits >= thresh["url_hits"]:
        # Single assignments can contain multiple links; require extra evidence.
        if distinct_codes >= 2 or label_hits >= 2 or apply_now_hits >= 2:
            triggered.append(f"Multiple URLs ({url_hits} >= {thresh['url_hits']})")
    if apply_now_hits >= thresh["apply_now_hits"] and block_count >= 2:
        triggered.append(f"Repeated 'apply now' ({apply_now_hits} >= {thresh['apply_now_hits']}, blocks={block_count})")
    if block_count >= thresh["block_count"] and (distinct_codes >= 2 or label_hits >= 2):
        triggered.append(f"Many content blocks ({block_count} >= {thresh['block_count']}) with multi-item signals")

    return (len(triggered) > 0), triggered
