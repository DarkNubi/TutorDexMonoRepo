"""
Unified Supabase Client for TutorDex.

Consolidates Supabase interactions across all services.
Handles auth, error handling, retries, and RPC 300 detection.
"""
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)


@dataclass
class SupabaseConfig:
    """Configuration for Supabase client."""
    url: str
    key: str
    timeout: int = 30
    max_retries: int = 3
    enabled: bool = True


class SupabaseError(Exception):
    """Base exception for Supabase errors."""
    pass


class SupabaseRPC300Error(SupabaseError):
    """Raised when RPC returns HTTP 300 (silent failure)."""
    pass


class SupabaseClient:
    """
    Unified Supabase PostgREST client.
    
    Provides a consistent interface for all Supabase operations across services.
    Handles:
    - Authentication headers
    - Error handling and retries
    - RPC 300 detection (audit Priority 2)
    - Connection pooling
    - Timeout configuration
    """
    
    def __init__(self, config: SupabaseConfig):
        """
        Initialize Supabase client.
        
        Args:
            config: SupabaseConfig with URL, key, and options
        """
        self.config = config
        self.base_url = f"{config.url}/rest/v1"
        
        # Create session with retry logic
        self.session = requests.Session()
        
        # Configure retries for transient errors
        retry_strategy = Retry(
            total=config.max_retries,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["GET", "POST", "PUT", "DELETE"]
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
        
        # Disable trust_env for local/Docker URLs
        try:
            host = (urlparse(config.url).hostname or "").lower()
            if host in {"127.0.0.1", "localhost", "::1"}:
                self.session.trust_env = False
        except Exception:
            pass
    
    def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        """
        Generate request headers with authentication.
        
        Args:
            extra: Additional headers to include
            
        Returns:
            Dict of headers
        """
        headers = {
            "apikey": self.config.key,
            "Authorization": f"Bearer {self.config.key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation",
        }
        if extra:
            headers.update(extra)
        return headers
    
    def select(
        self,
        table: str,
        filters: Optional[Dict[str, Any]] = None,
        columns: str = "*",
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        order_by: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        SELECT query with filters.
        
        Args:
            table: Table name
            filters: Dict of column=value filters (uses eq operator)
            columns: Columns to select (default: all)
            limit: Max rows to return
            offset: Rows to skip (for pagination)
            order_by: Order by clause (e.g., "created_at.desc")
            
        Returns:
            List of rows
            
        Raises:
            SupabaseError: On API error
        """
        url = f"{self.base_url}/{table}"
        params: Dict[str, Any] = {"select": columns}
        
        # Add filters
        if filters:
            for key, value in filters.items():
                params[key] = f"eq.{value}"
        
        # Add pagination
        if limit:
            params["limit"] = limit
        if offset:
            params["offset"] = offset
        
        # Add ordering
        if order_by:
            params["order"] = order_by
        
        try:
            response = self.session.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Supabase SELECT failed: {e}")
            raise SupabaseError(f"SELECT failed: {e}") from e
    
    def insert(self, table: str, data: Union[Dict, List[Dict]]) -> Union[Dict, List[Dict]]:
        """
        INSERT single row or multiple rows.
        
        Args:
            table: Table name
            data: Single row dict or list of row dicts
            
        Returns:
            Inserted row(s)
            
        Raises:
            SupabaseError: On API error
        """
        url = f"{self.base_url}/{table}"
        is_single = isinstance(data, dict)
        
        try:
            response = self.session.post(
                url,
                headers=self._headers(),
                json=data,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            result = response.json()
            return result[0] if is_single and result else result
        except requests.exceptions.RequestException as e:
            logger.error(f"Supabase INSERT failed: {e}")
            raise SupabaseError(f"INSERT failed: {e}") from e
    
    def upsert(
        self,
        table: str,
        data: Union[Dict, List[Dict]],
        on_conflict: str = "id"
    ) -> Union[Dict, List[Dict]]:
        """
        UPSERT single row or multiple rows.
        
        Args:
            table: Table name
            data: Single row dict or list of row dicts
            on_conflict: Column(s) for conflict resolution
            
        Returns:
            Upserted row(s)
            
        Raises:
            SupabaseError: On API error
        """
        url = f"{self.base_url}/{table}?on_conflict={on_conflict}"
        headers = self._headers({"Prefer": "resolution=merge-duplicates,return=representation"})
        is_single = isinstance(data, dict)
        
        try:
            response = self.session.post(
                url,
                headers=headers,
                json=data,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            result = response.json()
            return result[0] if is_single and result else result
        except requests.exceptions.RequestException as e:
            logger.error(f"Supabase UPSERT failed: {e}")
            raise SupabaseError(f"UPSERT failed: {e}") from e
    
    def update(
        self,
        table: str,
        data: Dict[str, Any],
        filters: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        UPDATE rows matching filters.
        
        Args:
            table: Table name
            data: Columns to update
            filters: WHERE conditions
            
        Returns:
            Updated rows
            
        Raises:
            SupabaseError: On API error
        """
        url = f"{self.base_url}/{table}"
        params = {}
        for key, value in filters.items():
            params[key] = f"eq.{value}"
        
        try:
            response = self.session.patch(
                url,
                headers=self._headers(),
                json=data,
                params=params,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Supabase UPDATE failed: {e}")
            raise SupabaseError(f"UPDATE failed: {e}") from e
    
    def delete(self, table: str, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        DELETE rows matching filters.
        
        Args:
            table: Table name
            filters: WHERE conditions
            
        Returns:
            Deleted rows
            
        Raises:
            SupabaseError: On API error
        """
        url = f"{self.base_url}/{table}"
        params = {}
        for key, value in filters.items():
            params[key] = f"eq.{value}"
        
        try:
            response = self.session.delete(
                url,
                headers=self._headers(),
                params=params,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"Supabase DELETE failed: {e}")
            raise SupabaseError(f"DELETE failed: {e}") from e
    
    def rpc(self, function: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """
        Call RPC function.
        
        Includes detection for HTTP 300 (audit Priority 2).
        
        Args:
            function: Function name
            params: Function parameters
            
        Returns:
            Function result
            
        Raises:
            SupabaseRPC300Error: If RPC returns HTTP 300
            SupabaseError: On other API errors
        """
        url = f"{self.base_url}/rpc/{function}"
        
        try:
            response = self.session.post(
                url,
                headers=self._headers(),
                json=params or {},
                timeout=self.config.timeout
            )
            
            # Check for HTTP 300 (silent failure - audit Priority 2)
            if response.status_code == 300:
                error_msg = f"RPC returned HTTP 300 for function '{function}' - indicates silent failure"
                logger.error(error_msg)
                raise SupabaseRPC300Error(error_msg)
            
            response.raise_for_status()
            return response.json()
        except SupabaseRPC300Error:
            raise  # Re-raise RPC 300 errors
        except requests.exceptions.RequestException as e:
            logger.error(f"Supabase RPC failed: {e}")
            raise SupabaseError(f"RPC '{function}' failed: {e}") from e
    
    def count(self, table: str, filters: Optional[Dict[str, Any]] = None) -> int:
        """
        Count rows matching filters.
        
        Args:
            table: Table name
            filters: WHERE conditions
            
        Returns:
            Row count
        """
        url = f"{self.base_url}/{table}"
        params = {"select": "*"}
        
        if filters:
            for key, value in filters.items():
                params[key] = f"eq.{value}"
        
        headers = self._headers({"Prefer": "count=exact"})
        
        try:
            response = self.session.head(
                url,
                headers=headers,
                params=params,
                timeout=self.config.timeout
            )
            response.raise_for_status()
            
            # Extract count from Content-Range header
            content_range = response.headers.get("Content-Range", "")
            if content_range:
                # Format: "0-9/42" where 42 is the total count
                total = content_range.split("/")[-1]
                return int(total) if total != "*" else 0
            return 0
        except Exception as e:
            logger.warning(f"Count failed, returning 0: {e}")
            return 0
    
    def enabled(self) -> bool:
        """Check if client is enabled."""
        return self.config.enabled


def create_client_from_env() -> SupabaseClient:
    """
    Create Supabase client from environment variables.
    
    Environment variables:
    - SUPABASE_URL: Supabase project URL
    - SUPABASE_KEY or SUPABASE_SERVICE_ROLE_KEY: API key
    - SUPABASE_TIMEOUT: Request timeout in seconds (default: 30)
    - SUPABASE_MAX_RETRIES: Max retry attempts (default: 3)
    - SUPABASE_ENABLED: Enable/disable client (default: 1)
    
    Returns:
        Configured SupabaseClient
    """

    class _SupabaseEnvSettings(BaseSettings):
        model_config = SettingsConfigDict(case_sensitive=False, extra="ignore", env_file=None)

        supabase_url: str = Field(default="", validation_alias=AliasChoices("SUPABASE_URL"))
        supabase_service_role_key: Optional[str] = Field(default=None, validation_alias=AliasChoices("SUPABASE_SERVICE_ROLE_KEY"))
        supabase_key: Optional[str] = Field(default=None, validation_alias=AliasChoices("SUPABASE_KEY"))
        supabase_timeout: int = Field(default=30, validation_alias=AliasChoices("SUPABASE_TIMEOUT"))
        supabase_max_retries: int = Field(default=3, validation_alias=AliasChoices("SUPABASE_MAX_RETRIES"))
        supabase_enabled: bool = Field(default=True, validation_alias=AliasChoices("SUPABASE_ENABLED"))

    s = _SupabaseEnvSettings()
    url = str(s.supabase_url or "").strip()
    key = str(s.supabase_service_role_key or s.supabase_key or "").strip()
    enabled = bool(s.supabase_enabled) and bool(url and key)
    
    config = SupabaseConfig(
        url=url,
        key=key,
        timeout=int(s.supabase_timeout),
        max_retries=int(s.supabase_max_retries),
        enabled=enabled
    )
    
    return SupabaseClient(config)
