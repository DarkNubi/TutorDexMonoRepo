import logging
import re
from functools import lru_cache
from typing import Optional, Tuple

import requests

from shared.config import load_backend_config

logger = logging.getLogger("geocoding")
_POSTAL_RE = re.compile(r"\b(\d{6})\b")
_CFG = load_backend_config()


def _nominatim_disabled() -> bool:
    return bool(_CFG.disable_nominatim)


def normalize_sg_postal_code(value: Optional[str]) -> Optional[str]:
    """
    Returns:
      - "" when input is blank (clear)
      - "NNNNNN" when valid SG postal
      - None when invalid
    """
    if value is None:
        return None
    raw = str(value).strip()
    digits = re.sub(r"\D+", "", raw)
    if not digits:
        return ""
    if len(digits) != 6:
        return None
    m = _POSTAL_RE.search(digits)
    return m.group(1) if m else None


@lru_cache(maxsize=2048)
def geocode_sg_postal_code(postal_code: str, *, timeout: int = 10) -> Optional[Tuple[float, float]]:
    if _nominatim_disabled():
        return None
    pc = normalize_sg_postal_code(postal_code)
    if not pc:
        return None

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": f"Singapore {pc}", "format": "jsonv2", "limit": 1, "countrycodes": "sg"}
    headers = {"User-Agent": str(_CFG.nominatim_user_agent or "TutorDexBackend/1.0")}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    except Exception as e:
        logger.info("nominatim_failed postal_code=%s error=%s", pc, e)
        return None

    if resp.status_code >= 400:
        logger.info("nominatim_status postal_code=%s status=%s", pc, resp.status_code)
        return None

    try:
        data = resp.json()
    except Exception:
        return None
    if not isinstance(data, list) or not data:
        return None

    row = data[0] if isinstance(data[0], dict) else None
    if not row:
        return None

    try:
        lat = float(row.get("lat"))
        lon = float(row.get("lon"))
        return (lat, lon)
    except Exception:
        return None
