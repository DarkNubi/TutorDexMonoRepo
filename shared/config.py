"""
Centralized Configuration Management for TutorDex MonoRepo.

Uses pydantic-settings for type-safe configuration with validation.
Provides single source of truth for all environment variables across services.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class AggregatorConfig(BaseSettings):
    """Configuration for TutorDexAggregator services (collector, workers)."""
    
    # Supabase
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_key: str = Field(..., description="Supabase service role key")
    
    # Pipeline versioning
    extraction_pipeline_version: str = Field(
        default="2026-01-02_det_time_v1",
        description="Pipeline version for extraction queue isolation"
    )
    schema_version: str = Field(
        default="2026-01-01",
        description="Canonical JSON schema version"
    )
    
    # Extraction worker
    extraction_max_attempts: int = Field(
        default=3,
        description="Maximum retry attempts for failed extractions"
    )
    extraction_worker_batch_size: int = Field(
        default=10,
        description="Number of jobs to process per batch"
    )
    extraction_worker_poll_seconds: int = Field(
        default=5,
        description="Polling interval for extraction queue"
    )
    extraction_worker_oneshot: bool = Field(
        default=False,
        description="Process one batch and exit (for testing)"
    )
    
    # LLM API
    llm_api_url: str = Field(
        default="http://host.docker.internal:1234",
        description="OpenAI-compatible LLM API URL"
    )
    llm_model_name: str = Field(
        default="default",
        description="Model name to use for extraction"
    )
    llm_circuit_breaker_threshold: int = Field(
        default=5,
        description="Consecutive failures before circuit opens"
    )
    llm_circuit_breaker_timeout_seconds: int = Field(
        default=60,
        description="Seconds to wait before retrying after circuit open"
    )
    
    # Side-effects (opt-in for worker)
    enable_broadcast: bool = Field(
        default=False,
        description="Send assignments to broadcast Telegram channel"
    )
    enable_dms: bool = Field(
        default=False,
        description="Send DMs to matched tutors"
    )
    enable_persistence: bool = Field(
        default=True,
        description="Persist assignments to Supabase"
    )
    
    # Telegram
    telegram_api_id: Optional[str] = Field(
        default=None,
        description="Telegram API ID from my.telegram.org"
    )
    telegram_api_hash: Optional[str] = Field(
        default=None,
        description="Telegram API hash from my.telegram.org"
    )
    telegram_session_name: str = Field(
        default="tutordex_collector",
        description="Session file name for Telegram client"
    )
    telegram_bot_token: Optional[str] = Field(
        default=None,
        description="Bot token for Telegram bot"
    )
    
    # Observability
    otel_enabled: bool = Field(
        default=False,
        description="Enable OpenTelemetry tracing"
    )
    otel_exporter_otlp_endpoint: str = Field(
        default="http://otel-collector:4318",
        description="OTLP HTTP endpoint for traces"
    )
    otel_service_name: str = Field(
        default="tutordex-aggregator",
        description="Service name for tracing"
    )
    prometheus_port: int = Field(
        default=8001,
        description="Port to expose Prometheus metrics"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR)"
    )
    
    # Sentry
    sentry_dsn: Optional[str] = Field(
        default=None,
        description="Sentry DSN for error reporting"
    )
    sentry_environment: str = Field(
        default="production",
        description="Sentry environment name"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"  # Ignore unknown env vars


class BackendConfig(BaseSettings):
    """Configuration for TutorDexBackend API service."""
    
    # Environment
    app_env: str = Field(
        default="dev",
        description="Application environment (dev, test, production)"
    )
    app_host: str = Field(
        default="0.0.0.0",
        description="Host to bind API server"
    )
    app_port: int = Field(
        default=8000,
        description="Port to bind API server"
    )
    
    # Auth
    auth_required: bool = Field(
        default=True,
        description="Require Firebase authentication"
    )
    firebase_admin_enabled: bool = Field(
        default=True,
        description="Enable Firebase Admin SDK"
    )
    firebase_admin_credentials_path: Optional[str] = Field(
        default=None,
        description="Path to Firebase service account JSON"
    )
    admin_api_key: Optional[str] = Field(
        default=None,
        description="Admin API key for /admin/* endpoints"
    )
    
    # Database
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_key: str = Field(..., description="Supabase service role key")
    redis_url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL"
    )
    redis_prefix: str = Field(
        default="tutordex:",
        description="Prefix for Redis keys"
    )
    
    # Rate limiting
    rate_limit_enabled: bool = Field(
        default=True,
        description="Enable rate limiting"
    )
    rate_limit_default: str = Field(
        default="100/minute",
        description="Default rate limit"
    )
    
    # CORS
    cors_allow_origins: str = Field(
        default="*",
        description="Allowed CORS origins (comma-separated or *)"
    )
    
    # Observability
    otel_enabled: bool = Field(
        default=False,
        description="Enable OpenTelemetry tracing"
    )
    otel_exporter_otlp_endpoint: str = Field(
        default="http://otel-collector:4318",
        description="OTLP HTTP endpoint for traces"
    )
    otel_service_name: str = Field(
        default="tutordex-backend",
        description="Service name for tracing"
    )
    log_level: str = Field(
        default="INFO",
        description="Logging level"
    )
    
    # Sentry
    sentry_dsn: Optional[str] = Field(
        default=None,
        description="Sentry DSN for error reporting"
    )
    sentry_environment: str = Field(
        default="production",
        description="Sentry environment name"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


class WebsiteConfig(BaseSettings):
    """Configuration for TutorDexWebsite (frontend)."""
    
    # Firebase
    firebase_api_key: str = Field(..., description="Firebase Web API key")
    firebase_auth_domain: str = Field(..., description="Firebase auth domain")
    firebase_project_id: str = Field(..., description="Firebase project ID")
    firebase_storage_bucket: Optional[str] = Field(
        default=None,
        description="Firebase storage bucket"
    )
    firebase_messaging_sender_id: Optional[str] = Field(
        default=None,
        description="Firebase messaging sender ID"
    )
    firebase_app_id: Optional[str] = Field(
        default=None,
        description="Firebase app ID"
    )
    
    # Backend API
    backend_api_url: str = Field(
        default="http://localhost:8000",
        description="Backend API base URL"
    )
    
    # Sentry
    sentry_dsn: Optional[str] = Field(
        default=None,
        description="Sentry DSN for error reporting"
    )
    sentry_environment: str = Field(
        default="production",
        description="Sentry environment name"
    )
    sentry_sample_rate: float = Field(
        default=0.1,
        description="Sentry trace sample rate (0.0-1.0)"
    )
    
    class Config:
        env_prefix = "VITE_"  # Vite requires VITE_ prefix
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


# Convenience functions for loading configs
def load_aggregator_config() -> AggregatorConfig:
    """Load aggregator configuration from environment."""
    return AggregatorConfig()


def load_backend_config() -> BackendConfig:
    """Load backend configuration from environment."""
    return BackendConfig()


def load_website_config() -> WebsiteConfig:
    """Load website configuration from environment."""
    return WebsiteConfig()
