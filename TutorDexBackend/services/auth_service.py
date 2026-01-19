"""
Authentication and authorization service.

Handles Firebase token verification and admin API key validation.
"""
import logging
from typing import Optional
from fastapi import HTTPException, Request
from TutorDexBackend.firebase_auth import firebase_admin_status, verify_bearer_token
from TutorDexBackend.utils.config_utils import is_production
from shared.config import load_backend_config
from shared.observability.exception_handler import swallow_exception

logger = logging.getLogger("tutordex_backend")
_CFG = load_backend_config()


class AuthService:
    """Centralized authentication and authorization logic."""
    
    def __init__(self):
        pass
    
    def is_auth_required(self) -> bool:
        """Check if authentication is enabled."""
        return bool(_CFG.auth_required)
    
    def get_admin_key(self) -> str:
        """Get admin API key from environment."""
        return str(_CFG.admin_api_key or "").strip()
    
    def require_admin(self, request: Request) -> None:
        """
        Verify admin API key from request headers.
        
        Args:
            request: FastAPI request object
            
        Raises:
            HTTPException: 401 if unauthorized, 500 if key missing in prod
        """
        key = self.get_admin_key()
        if not key:
            # In dev, allow missing key for easier local iteration
            if not is_production():
                return
            raise HTTPException(status_code=500, detail="admin_api_key_missing")
        
        provided = (
            request.headers.get("x-api-key") or 
            request.headers.get("X-Api-Key") or 
            request.headers.get("x-admin-key") or
            request.headers.get("X-Admin-Key") or
            ""
        ).strip()
        
        if provided != key:
            raise HTTPException(status_code=401, detail="admin_unauthorized")
    
    def get_uid_from_request(self, request: Request) -> Optional[str]:
        """
        Extract Firebase UID from request if present.
        
        Returns None if no bearer token or invalid token.
        Does not raise exceptions.
        
        Args:
            request: FastAPI request object
            
        Returns:
            Firebase UID or None
        """
        header = (
            request.headers.get("authorization") or 
            request.headers.get("Authorization") or 
            ""
        )
        if not header:
            return None
        
        parts = header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        
        decoded = verify_bearer_token(parts[1])
        if not decoded:
            return None
        
        return decoded.get("uid")
    
    def require_uid(self, request: Request) -> str:
        """
        Require authenticated Firebase user.
        
        Args:
            request: FastAPI request object
            
        Returns:
            Firebase UID string
            
        Raises:
            HTTPException: 401 if not authenticated, 500/503 if Firebase misconfigured
        """
        header = (
            request.headers.get("authorization") or 
            request.headers.get("Authorization") or 
            ""
        )
        if not header:
            if self.is_auth_required():
                raise HTTPException(status_code=401, detail="missing_bearer_token")
            raise HTTPException(status_code=401, detail="unauthorized_or_auth_disabled")
        
        parts = header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            if self.is_auth_required():
                raise HTTPException(status_code=401, detail="invalid_authorization_header")
            raise HTTPException(status_code=401, detail="unauthorized_or_auth_disabled")
        
        decoded = verify_bearer_token(parts[1])
        uid = decoded.get("uid") if decoded else None
        
        if uid:
            try:
                request.state.uid = uid
            except Exception as e:
                swallow_exception(e, context="auth_request_state_setting", extra={"module": __name__})
            return uid
        
        if self.is_auth_required():
            st = firebase_admin_status()
            if not st.get("enabled"):
                raise HTTPException(
                    status_code=500, 
                    detail="auth_required_but_firebase_admin_disabled"
                )
            if not st.get("ready"):
                raise HTTPException(
                    status_code=503, 
                    detail="firebase_admin_init_failed"
                )
            raise HTTPException(status_code=401, detail="invalid_bearer_token")
        
        raise HTTPException(status_code=401, detail="unauthorized_or_auth_disabled")
    
    def validate_production_config(self) -> None:
        """
        Validate production configuration at startup.
        
        Raises:
            RuntimeError: If critical configuration is missing/invalid
        """
        if not is_production():
            return
        
        # Check admin API key
        if not self.get_admin_key():
            raise RuntimeError("ADMIN_API_KEY is required when APP_ENV=prod")
        
        # Check auth is required
        if not self.is_auth_required():
            raise RuntimeError("AUTH_REQUIRED must be true when APP_ENV=prod")
        
        # Check Firebase Admin is ready
        st = firebase_admin_status()
        if not bool(st.get("enabled")):
            raise RuntimeError(
                "FIREBASE_ADMIN_ENABLED must be true when APP_ENV=prod and AUTH_REQUIRED=true"
            )
        if not bool(st.get("ready")):
            raise RuntimeError(
                f"Firebase Admin not ready in prod "
                f"(check FIREBASE_ADMIN_CREDENTIALS_PATH). status={st}"
            )
