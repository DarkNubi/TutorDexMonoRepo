import base64
import hashlib
import hmac
import json
import os
from typing import Any, Dict, Optional


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _tracking_secret() -> str:
    return (os.environ.get("CLICK_TRACKING_SECRET") or os.environ.get("TRACKING_SIGNING_SECRET") or "").strip()


def tracking_enabled() -> bool:
    return bool(_tracking_secret()) and bool((os.environ.get("TRACKING_BASE_URL") or "").strip())


def build_tracked_url(*, external_id: str, original_url: str) -> Optional[str]:
    base = (os.environ.get("TRACKING_BASE_URL") or "").strip().rstrip("/")
    secret = _tracking_secret()
    ext = str(external_id).strip()
    url = str(original_url).strip()
    if not (base and secret and ext and url):
        return None

    payload: Dict[str, Any] = {"external_id": ext, "original_url": url}
    payload_b64 = _b64url(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    sig = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).digest()
    token = f"{payload_b64}.{_b64url(sig)}"
    return f"{base}/r/a/{token}"

