import os
import logging
from dataclasses import dataclass
from typing import Optional, Dict, Any

import firebase_admin
from firebase_admin import credentials, auth


logger = logging.getLogger("firebase_auth")


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class FirebaseAuthConfig:
    enabled: bool
    credentials_path: Optional[str]


def load_firebase_auth_config() -> FirebaseAuthConfig:
    enabled = _truthy(os.environ.get("FIREBASE_ADMIN_ENABLED"))
    credentials_path = (os.environ.get("FIREBASE_ADMIN_CREDENTIALS_PATH") or "").strip() or None
    return FirebaseAuthConfig(enabled=enabled, credentials_path=credentials_path)


_firebase_ready = False
_firebase_init_error: Optional[str] = None


def init_firebase_admin_if_needed() -> bool:
    global _firebase_ready
    global _firebase_init_error
    if _firebase_ready:
        return True
    cfg = load_firebase_auth_config()
    if not cfg.enabled:
        _firebase_init_error = "disabled"
        return False
    try:
        if firebase_admin._apps:
            _firebase_ready = True
            _firebase_init_error = None
            return True
        if not cfg.credentials_path:
            raise RuntimeError("FIREBASE_ADMIN_CREDENTIALS_PATH not set")
        cred = credentials.Certificate(cfg.credentials_path)
        firebase_admin.initialize_app(cred)
        _firebase_ready = True
        _firebase_init_error = None
        return True
    except Exception as e:
        _firebase_init_error = str(e)
        logger.warning("Firebase Admin init failed; auth disabled error=%s", e)
        return False


def verify_bearer_token(token: str) -> Optional[Dict[str, Any]]:
    if not token:
        return None
    if not init_firebase_admin_if_needed():
        return None
    try:
        return auth.verify_id_token(token)
    except Exception:
        return None


def firebase_admin_status() -> Dict[str, Any]:
    """
    Returns a small status blob to distinguish "invalid token" vs "auth misconfigured".
    """
    cfg = load_firebase_auth_config()
    ready = init_firebase_admin_if_needed() if cfg.enabled else False
    return {
        "enabled": bool(cfg.enabled),
        "ready": bool(ready),
        "credentials_path_set": bool(cfg.credentials_path),
        "init_error": _firebase_init_error,
    }

