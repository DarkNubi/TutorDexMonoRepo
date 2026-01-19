from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Dict, List, Optional

import requests

from shared.config import load_aggregator_config

try:
    # Running from `TutorDexAggregator/` with that folder on sys.path.
    from logging_setup import log_event, timed  # type: ignore
except Exception:
    # Imported as `TutorDexAggregator.*` from repo root (e.g., unit tests).
    from TutorDexAggregator.logging_setup import log_event, timed  # type: ignore


logger = logging.getLogger("postal_code_estimated")

_SG_POSTAL_RE = re.compile(r"\b(\d{6})\b")


@lru_cache(maxsize=1)
def _cfg():
    return load_aggregator_config()


def _nominatim_disabled() -> bool:
    return bool(_cfg().disable_nominatim)


def _nominatim_user_agent() -> str:
    return (str(_cfg().nominatim_user_agent or "").strip() or "TutorDexAggregator/1.0")


def _extract_sg_postal_codes(text: Any) -> List[str]:
    try:
        codes = _SG_POSTAL_RE.findall(str(text or ""))
    except Exception:
        codes = []
    seen = set()
    out: List[str] = []
    for c in codes:
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def _coerce_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        return [s] if s else []
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for x in value:
            out.extend(_coerce_text_list(x))
        # de-dup preserve order
        seen = set()
        uniq: List[str] = []
        for t in out:
            s = str(t).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            uniq.append(s)
        return uniq
    s2 = str(value).strip()
    return [s2] if s2 else []


def _extract_address_from_raw_text(raw_text: str) -> List[str]:
    out: List[str] = []
    for line in str(raw_text or "").splitlines():
        ln = line.strip()
        if not ln:
            continue
        if ln.startswith("📍"):
            candidate = ln.lstrip("📍").strip()
            if candidate:
                out.append(candidate)
            continue
        m = re.match(r"(?i)^(address|location)\s*[:：]\s*(.+)$", ln)
        if m:
            candidate = (m.group(2) or "").strip()
            if candidate:
                out.append(candidate)

    # de-dup preserve order
    seen = set()
    uniq: List[str] = []
    for x in out:
        s = str(x).strip()
        if not s or s in seen:
            continue
        seen.add(s)
        uniq.append(s)
    return uniq


def _clean_address_for_geocode(address: str) -> str:
    s = str(address or "").strip()
    if not s:
        return ""
    # Conservative cleanup only: strip brackets and "near" noise.
    s = re.sub(r"\bnear\b", "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"[\[\(].*?[\]\)]", "", s).strip()
    s = re.sub(r"\s+", " ", s).strip()
    return s


@lru_cache(maxsize=5000)
def _estimate_postal_from_cleaned_address(cleaned_address: str, *, timeout_s: float) -> Optional[str]:
    if _nominatim_disabled():
        return None
    q = _clean_address_for_geocode(cleaned_address)
    if not q:
        return None

    # Nominatim: query by free-form string; force SG.
    url = "https://nominatim.openstreetmap.org/search"
    params = {
        "q": f"{q}, Singapore",
        "format": "jsonv2",
        "countrycodes": "sg",
        "addressdetails": 1,
        "limit": 5,
    }
    headers = {"User-Agent": _nominatim_user_agent()}

    max_attempts = int(_cfg().nominatim_retries)
    backoff_s = float(_cfg().nominatim_backoff_seconds)

    last_err: Optional[str] = None
    for attempt in range(max(1, min(max_attempts, 6))):
        try:
            t0 = timed()
            resp = requests.get(url, params=params, headers=headers, timeout=float(timeout_s))
            log_event(
                logger,
                logging.INFO,
                "nominatim_postal_lookup",
                status_code=getattr(resp, "status_code", None),
                elapsed_ms=round((timed() - t0) * 1000.0, 2),
                q_chars=len(q),
                attempt=attempt + 1,
            )
        except Exception as e:
            last_err = str(e)
            resp = None

        if resp is None:
            if attempt < max_attempts - 1:
                time.sleep(min(10.0, backoff_s * (2**attempt)))
            continue

        if resp.status_code in {429, 503} and attempt < max_attempts - 1:
            retry_after = resp.headers.get("Retry-After")
            sleep_s = min(20.0, backoff_s * (2**attempt))
            if retry_after:
                try:
                    sleep_s = max(sleep_s, float(retry_after))
                except Exception:
                    pass
            time.sleep(min(20.0, sleep_s))
            continue

        if resp.status_code >= 400:
            return None

        try:
            data = resp.json()
        except Exception:
            return None
        if not isinstance(data, list):
            return None

        for r in data:
            if not isinstance(r, dict):
                continue
            addr = r.get("address") if isinstance(r.get("address"), dict) else {}
            postal = addr.get("postcode") if isinstance(addr, dict) else None
            for candidate in (postal, r.get("display_name")):
                codes = _extract_sg_postal_codes(candidate)
                if codes:
                    return codes[0]

        return None

    _ = last_err
    return None


@dataclass(frozen=True)
class PostalEstimateResult:
    estimated: Optional[List[str]]
    meta: Dict[str, Any]


def estimate_postal_codes(
    *,
    parsed: Dict[str, Any],
    raw_text: str,
    timeout_s: float = 10.0,
) -> PostalEstimateResult:
    """
    Best-effort postal code estimation (rough) when no explicit postal code exists.

    Returns:
      - estimated: list[str] | None   (6-digit SG postals; deduped; order preserved)
      - meta: dict (diagnostics; safe to persist)
    """
    if not isinstance(parsed, dict):
        return PostalEstimateResult(estimated=None, meta={"ok": False, "error": "parsed_not_dict"})

    # Never override explicit postal codes.
    if _coerce_text_list(parsed.get("postal_code")):
        return PostalEstimateResult(estimated=None, meta={"ok": True, "skipped": "postal_code_present"})

    if _nominatim_disabled():
        return PostalEstimateResult(estimated=None, meta={"ok": True, "skipped": "nominatim_disabled"})

    # Candidate addresses: prefer structured extraction, then raw-text hints.
    addr_candidates = _coerce_text_list(parsed.get("address"))
    if not addr_candidates:
        addr_candidates = _extract_address_from_raw_text(raw_text)

    if not addr_candidates:
        return PostalEstimateResult(estimated=None, meta={"ok": True, "skipped": "missing_address"})

    estimated_codes: List[str] = []
    used = 0
    for addr in addr_candidates[:5]:
        cleaned = _clean_address_for_geocode(addr)
        if not cleaned:
            continue
        used += 1
        code = _estimate_postal_from_cleaned_address(cleaned, timeout_s=float(timeout_s))
        if code and code not in estimated_codes:
            estimated_codes.append(code)

    return PostalEstimateResult(
        estimated=estimated_codes or None,
        meta={
            "ok": True,
            "used_address_candidates": used,
            "address_candidates_total": len(addr_candidates),
            "estimated_count": len(estimated_codes),
        },
    )

