"""
Centralized Configuration Management for TutorDex MonoRepo.

Goal:
- One typed source of truth for config across services.
- Keep legacy env var names working during migration (aliases), but prefer the new canonical keys.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Optional

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_REPO_ROOT = Path(__file__).resolve().parents[1]


def _running_in_docker() -> bool:
    """Detect if running inside a Docker container (best-effort)."""
    if Path("/.dockerenv").exists():
        return True
    try:
        p = Path("/proc/1/cgroup")
        if p.exists():
            s = p.read_text(encoding="utf-8", errors="ignore")
            if "docker" in s or "containerd" in s or "kubepods" in s:
                return True
    except Exception as e:
        from shared.observability import swallow_exception
        swallow_exception(e, context="docker_detection", extra={"module": __name__})
    return False


def _clean_url(value: Optional[str]) -> Optional[str]:
    s = (value or "").strip().rstrip("/")
    return s or None


def _env_file_candidates(service_dir: str) -> list[Path]:
    # Order matters: service-local .env first, then repo-root .env (if any).
    return [
        _REPO_ROOT / service_dir / ".env",
        _REPO_ROOT / ".env",
    ]


class AggregatorConfig(BaseSettings):
    """Configuration for TutorDexAggregator services (collector, workers, broadcasters, utilities)."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # -------------------------
    # Supabase (routing + auth)
    # -------------------------
    supabase_url_docker: Optional[str] = Field(default=None, validation_alias=AliasChoices("SUPABASE_URL_DOCKER"))
    supabase_url_host: Optional[str] = Field(default=None, validation_alias=AliasChoices("SUPABASE_URL_HOST"))
    supabase_url: Optional[str] = Field(default=None, validation_alias=AliasChoices("SUPABASE_URL"))

    supabase_service_role_key: Optional[str] = Field(default=None, validation_alias=AliasChoices("SUPABASE_SERVICE_ROLE_KEY"))
    supabase_key: Optional[str] = Field(default=None, validation_alias=AliasChoices("SUPABASE_KEY"))

    # Default to disabled if not explicitly set (matches legacy behavior of truthy(env)).
    supabase_enabled: bool = Field(default=False, validation_alias=AliasChoices("SUPABASE_ENABLED"))
    supabase_raw_enabled: bool = Field(default=False, validation_alias=AliasChoices("SUPABASE_RAW_ENABLED"))
    supabase_assignments_table: str = Field(default="assignments", validation_alias=AliasChoices("SUPABASE_ASSIGNMENTS_TABLE"))
    supabase_raw_messages_table: str = Field(default="telegram_messages_raw", validation_alias=AliasChoices("SUPABASE_RAW_MESSAGES_TABLE"))
    supabase_raw_channels_table: str = Field(default="telegram_channels", validation_alias=AliasChoices("SUPABASE_RAW_CHANNELS_TABLE"))
    # Canonical ingestion tracking tables (see `TutorDexAggregator/supabase sqls/supabase_schema_full.sql`).
    # Note: older names (`telegram_collector_*`) are not part of the canonical schema snapshot.
    supabase_raw_progress_table: str = Field(default="ingestion_run_progress", validation_alias=AliasChoices("SUPABASE_RAW_PROGRESS_TABLE"))
    supabase_raw_runs_table: str = Field(default="ingestion_runs", validation_alias=AliasChoices("SUPABASE_RAW_RUNS_TABLE"))
    supabase_bump_min_seconds: int = Field(default=6 * 60 * 60, validation_alias=AliasChoices("SUPABASE_BUMP_MIN_SECONDS"))

    # -------------------------
    # Pipeline / worker knobs
    # -------------------------
    extraction_pipeline_version: str = Field(default="2026-01-02_det_time_v1", validation_alias=AliasChoices("EXTRACTION_PIPELINE_VERSION"))
    schema_version: str = Field(default="2026-01-01", validation_alias=AliasChoices("SCHEMA_VERSION"))

    extraction_queue_enabled: bool = Field(default=True, validation_alias=AliasChoices("EXTRACTION_QUEUE_ENABLED"))
    extraction_max_attempts: int = Field(default=3, validation_alias=AliasChoices("EXTRACTION_MAX_ATTEMPTS"))
    extraction_worker_batch_size: int = Field(default=10, validation_alias=AliasChoices("EXTRACTION_WORKER_BATCH_SIZE", "EXTRACTION_WORKER_BATCH"))
    extraction_worker_idle_s: float = Field(default=2.0, validation_alias=AliasChoices("EXTRACTION_WORKER_IDLE_S"))
    extraction_worker_max_jobs: int = Field(default=0, validation_alias=AliasChoices("EXTRACTION_WORKER_MAX_JOBS"))
    extraction_worker_oneshot: bool = Field(default=False, validation_alias=AliasChoices("EXTRACTION_WORKER_ONESHOT"))
    extraction_backoff_base_s: float = Field(default=1.5, validation_alias=AliasChoices("EXTRACTION_BACKOFF_BASE_S"))
    extraction_backoff_max_s: float = Field(default=60.0, validation_alias=AliasChoices("EXTRACTION_BACKOFF_MAX_S"))
    extraction_stale_processing_seconds: int = Field(default=900, validation_alias=AliasChoices("EXTRACTION_STALE_PROCESSING_SECONDS"))

    # Compilation detection thresholds (heuristics)
    compilation_distinct_codes: int = Field(default=2, validation_alias=AliasChoices("COMPILATION_DISTINCT_CODES", "COMPILATION_CODE_HITS"))
    compilation_label_hits: int = Field(default=2, validation_alias=AliasChoices("COMPILATION_LABEL_HITS"))
    compilation_postal_hits: int = Field(default=2, validation_alias=AliasChoices("COMPILATION_POSTAL_HITS"))
    compilation_url_hits: int = Field(default=2, validation_alias=AliasChoices("COMPILATION_URL_HITS"))
    compilation_block_count: int = Field(default=5, validation_alias=AliasChoices("COMPILATION_BLOCK_COUNT"))
    compilation_apply_now_hits: int = Field(default=2, validation_alias=AliasChoices("COMPILATION_APPLY_NOW_HITS"))

    enable_broadcast: bool = Field(default=False, validation_alias=AliasChoices("ENABLE_BROADCAST", "EXTRACTION_WORKER_BROADCAST"))
    enable_dms: bool = Field(default=False, validation_alias=AliasChoices("ENABLE_DMS", "EXTRACTION_WORKER_DMS"))

    # Enrichment and hardening
    enable_deterministic_signals: bool = Field(default=True, validation_alias=AliasChoices("ENABLE_DETERMINISTIC_SIGNALS"))
    use_deterministic_time: bool = Field(default=True, validation_alias=AliasChoices("USE_DETERMINISTIC_TIME"))
    use_normalized_text_for_llm: bool = Field(default=False, validation_alias=AliasChoices("USE_NORMALIZED_TEXT_FOR_LLM"))
    hard_validate_mode: str = Field(default="report", validation_alias=AliasChoices("HARD_VALIDATE_MODE"))
    enable_postal_code_estimated: bool = Field(default=True, validation_alias=AliasChoices("ENABLE_POSTAL_CODE_ESTIMATED"))
    freshness_tier_enabled: bool = Field(default=False, validation_alias=AliasChoices("FRESHNESS_TIER_ENABLED"))
    freshness_green_hours: int = Field(default=24, validation_alias=AliasChoices("FRESHNESS_GREEN_HOURS"))
    freshness_yellow_hours: int = Field(default=36, validation_alias=AliasChoices("FRESHNESS_YELLOW_HOURS"))
    freshness_orange_hours: int = Field(default=48, validation_alias=AliasChoices("FRESHNESS_ORANGE_HOURS"))
    freshness_red_hours: int = Field(default=72, validation_alias=AliasChoices("FRESHNESS_RED_HOURS"))
    geo_enrichment_enabled: bool = Field(default=True, validation_alias=AliasChoices("GEO_ENRICHMENT_ENABLED"))

    # -------------------------
    # LLM configuration
    # -------------------------
    llm_api_url: str = Field(default="http://localhost:1234", validation_alias=AliasChoices("LLM_API_URL"))
    llm_model_name: str = Field(default="lfm2-8b-a1b", validation_alias=AliasChoices("LLM_MODEL_NAME"))
    llm_timeout_seconds: int = Field(default=200, validation_alias=AliasChoices("LLM_TIMEOUT_SECONDS"))
    llm_system_prompt_file: Optional[str] = Field(default=None, validation_alias=AliasChoices("LLM_SYSTEM_PROMPT_FILE"))
    llm_system_prompt_text: Optional[str] = Field(default=None, validation_alias=AliasChoices("LLM_SYSTEM_PROMPT_TEXT"))
    llm_include_examples: bool = Field(default=False, validation_alias=AliasChoices("LLM_INCLUDE_EXAMPLES"))
    llm_examples_dir: Optional[str] = Field(default=None, validation_alias=AliasChoices("LLM_EXAMPLES_DIR"))
    llm_examples_variant: Optional[str] = Field(default=None, validation_alias=AliasChoices("LLM_EXAMPLES_VARIANT"))
    llm_mock_output_file: Optional[str] = Field(default=None, validation_alias=AliasChoices("LLM_MOCK_OUTPUT_FILE"))
    llm_assignment_code_extractor_mock_file: Optional[str] = Field(default=None, validation_alias=AliasChoices("LLM_ASSIGNMENT_CODE_EXTRACTOR_MOCK_FILE"))
    llm_circuit_breaker_threshold: int = Field(default=5, validation_alias=AliasChoices("LLM_CIRCUIT_BREAKER_THRESHOLD"))
    llm_circuit_breaker_timeout_seconds: int = Field(default=60, validation_alias=AliasChoices("LLM_CIRCUIT_BREAKER_TIMEOUT_SECONDS"))

    # -------------------------
    # Telegram collector/bots
    # -------------------------
    telegram_api_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("TELEGRAM_API_ID", "TG_API_ID", "API_ID"))
    telegram_api_hash: Optional[str] = Field(default=None, validation_alias=AliasChoices("TELEGRAM_API_HASH", "TG_API_HASH", "API_HASH"))
    session_string: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("SESSION_STRING", "TELEGRAM_SESSION_STRING", "TG_SESSION_STRING", "SESSION"),
    )
    session_string_recovery: Optional[str] = Field(default=None, validation_alias=AliasChoices("SESSION_STRING_RECOVERY", "TG_SESSION_STRING_RECOVERY", "SESSION_STRING_RECOVERY"))
    telegram_session_name: str = Field(default="tutordex.session", validation_alias=AliasChoices("TG_SESSION", "TELEGRAM_SESSION_NAME"))
    telegram_session_recovery: str = Field(default="tutordex_recovery.session", validation_alias=AliasChoices("TG_SESSION_RECOVERY"))

    channel_list: str = Field(default="", validation_alias=AliasChoices("CHANNEL_LIST", "CHANNELS"))

    group_bot_token: Optional[str] = Field(default=None, validation_alias=AliasChoices("GROUP_BOT_TOKEN", "TG_GROUP_BOT_TOKEN"))
    dm_bot_token: Optional[str] = Field(default=None, validation_alias=AliasChoices("DM_BOT_TOKEN"))
    dm_bot_api_url: Optional[str] = Field(default=None, validation_alias=AliasChoices("DM_BOT_API_URL"))
    tutor_match_url: str = Field(default="http://127.0.0.1:8000/match/payload", validation_alias=AliasChoices("TUTOR_MATCH_URL"))
    backend_api_key: Optional[str] = Field(default=None, validation_alias=AliasChoices("BACKEND_API_KEY"))

    dm_enabled: bool = Field(default=False, validation_alias=AliasChoices("DM_ENABLED"))
    dm_max_recipients: int = Field(default=50, validation_alias=AliasChoices("DM_MAX_RECIPIENTS"))
    dm_fallback_file: Optional[str] = Field(default=None, validation_alias=AliasChoices("DM_FALLBACK_FILE"))
    dm_filter_duplicates: bool = Field(default=True, validation_alias=AliasChoices("DM_FILTER_DUPLICATES"))
    dm_use_adaptive_threshold: bool = Field(default=True, validation_alias=AliasChoices("DM_USE_ADAPTIVE_THRESHOLD"))
    dm_rating_lookback_days: int = Field(default=7, validation_alias=AliasChoices("DM_RATING_LOOKBACK_DAYS"))
    dm_rating_avg_rate_lookback_days: int = Field(default=30, validation_alias=AliasChoices("DM_RATING_AVG_RATE_LOOKBACK_DAYS"))

    # Broadcast
    aggregator_channel_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("AGGREGATOR_CHANNEL_ID"))
    aggregator_channel_ids: Optional[str] = Field(default=None, validation_alias=AliasChoices("AGGREGATOR_CHANNEL_IDS"))
    bot_api_url: Optional[str] = Field(default=None, validation_alias=AliasChoices("BOT_API_URL", "TG_BOT_API_URL"))
    broadcast_fallback_file: Optional[str] = Field(default=None, validation_alias=AliasChoices("BROADCAST_FALLBACK_FILE"))
    broadcast_max_attempts: int = Field(default=3, validation_alias=AliasChoices("BROADCAST_MAX_ATTEMPTS"))
    broadcast_retry_base_seconds: float = Field(default=1.0, validation_alias=AliasChoices("BROADCAST_RETRY_BASE_SECONDS"))
    broadcast_retry_max_sleep_seconds: float = Field(default=30.0, validation_alias=AliasChoices("BROADCAST_RETRY_MAX_SLEEP_SECONDS"))
    broadcast_max_message_len: int = Field(default=3800, validation_alias=AliasChoices("BROADCAST_MAX_MESSAGE_LEN"))
    broadcast_max_remarks_len: int = Field(default=800, validation_alias=AliasChoices("BROADCAST_MAX_REMARKS_LEN"))
    broadcast_duplicate_mode: str = Field(default="skip", validation_alias=AliasChoices("BROADCAST_DUPLICATE_MODE"))
    enable_broadcast_tracking: bool = Field(default=False, validation_alias=AliasChoices("ENABLE_BROADCAST_TRACKING"))
    broadcast_sync_on_startup: bool = Field(default=False, validation_alias=AliasChoices("BROADCAST_SYNC_ON_STARTUP"))

    # Skipped/triage reporting channel
    skipped_messages_chat_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("SKIPPED_MESSAGES_CHAT_ID"))
    skipped_messages_thread_id: Optional[int] = Field(default=None, validation_alias=AliasChoices("SKIPPED_MESSAGES_THREAD_ID"))
    skipped_messages_thread_id_extraction_errors: Optional[int] = Field(default=None, validation_alias=AliasChoices("SKIPPED_MESSAGES_THREAD_ID_EXTRACTION_ERRORS"))
    skipped_messages_thread_id_non_assignment: Optional[int] = Field(default=None, validation_alias=AliasChoices("SKIPPED_MESSAGES_THREAD_ID_NON_ASSIGNMENT"))
    skipped_messages_thread_id_compilations: Optional[int] = Field(default=None, validation_alias=AliasChoices("SKIPPED_MESSAGES_THREAD_ID_COMPILATIONS"))

    # Alerts (Telegram alertmanager receiver)
    alert_bot_token: Optional[str] = Field(default=None, validation_alias=AliasChoices("ALERT_BOT_TOKEN"))
    alert_chat_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("ALERT_CHAT_ID"))
    alert_thread_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("ALERT_THREAD_ID"))
    alert_prefix: Optional[str] = Field(default=None, validation_alias=AliasChoices("ALERT_PREFIX"))

    # -------------------------
    # Observability
    # -------------------------
    log_level: str = Field(default="INFO", validation_alias=AliasChoices("LOG_LEVEL"))
    log_dir: Optional[str] = Field(default=None, validation_alias=AliasChoices("LOG_DIR"))
    log_file: Optional[str] = Field(default=None, validation_alias=AliasChoices("LOG_FILE"))
    log_json: bool = Field(default=False, validation_alias=AliasChoices("LOG_JSON"))
    log_to_console: bool = Field(default=True, validation_alias=AliasChoices("LOG_TO_CONSOLE"))
    log_to_file: bool = Field(default=True, validation_alias=AliasChoices("LOG_TO_FILE"))
    log_max_bytes: int = Field(default=5_000_000, validation_alias=AliasChoices("LOG_MAX_BYTES"))
    log_backup_count: int = Field(default=5, validation_alias=AliasChoices("LOG_BACKUP_COUNT"))

    otel_enabled: bool = Field(default=False, validation_alias=AliasChoices("OTEL_ENABLED"))
    otel_exporter_otlp_endpoint: str = Field(default="http://otel-collector:4318", validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_ENDPOINT"))
    otel_service_name: Optional[str] = Field(default=None, validation_alias=AliasChoices("OTEL_SERVICE_NAME"))

    sentry_dsn: Optional[str] = Field(default=None, validation_alias=AliasChoices("SENTRY_DSN"))
    sentry_environment: str = Field(default="production", validation_alias=AliasChoices("SENTRY_ENVIRONMENT"))
    sentry_release: Optional[str] = Field(default=None, validation_alias=AliasChoices("SENTRY_RELEASE"))
    sentry_service_name: Optional[str] = Field(default=None, validation_alias=AliasChoices("SENTRY_SERVICE_NAME"))
    sentry_traces_sample_rate: Optional[float] = Field(default=None, validation_alias=AliasChoices("SENTRY_TRACES_SAMPLE_RATE"))
    sentry_profiles_sample_rate: Optional[float] = Field(default=None, validation_alias=AliasChoices("SENTRY_PROFILES_SAMPLE_RATE"))

    # -------------------------
    # Recovery/catchup tuning
    # -------------------------
    recovery_catchup_enabled: bool = Field(default=True, validation_alias=AliasChoices("RECOVERY_CATCHUP_ENABLED"))
    recovery_catchup_state_file: str = Field(default="state/recovery_catchup_state.json", validation_alias=AliasChoices("RECOVERY_CATCHUP_STATE_FILE"))
    recovery_catchup_check_interval_seconds: int = Field(default=30, validation_alias=AliasChoices("RECOVERY_CATCHUP_CHECK_INTERVAL_SECONDS"))
    recovery_catchup_chunk_hours: int = Field(default=6, validation_alias=AliasChoices("RECOVERY_CATCHUP_CHUNK_HOURS"))
    recovery_catchup_overlap_minutes: int = Field(default=10, validation_alias=AliasChoices("RECOVERY_CATCHUP_OVERLAP_MINUTES"))
    recovery_catchup_target_lag_minutes: int = Field(default=2, validation_alias=AliasChoices("RECOVERY_CATCHUP_TARGET_LAG_MINUTES"))
    recovery_catchup_queue_low_watermark: int = Field(default=0, validation_alias=AliasChoices("RECOVERY_CATCHUP_QUEUE_LOW_WATERMARK"))
    recovery_backfill_max_attempts: int = Field(default=5, validation_alias=AliasChoices("RECOVERY_BACKFILL_MAX_ATTEMPTS"))
    recovery_backfill_base_backoff_seconds: float = Field(default=2.0, validation_alias=AliasChoices("RECOVERY_BACKFILL_BASE_BACKOFF_SECONDS"))

    # -------------------------
    # Geocoding/Nominatim
    # -------------------------
    disable_nominatim: bool = Field(default=False, validation_alias=AliasChoices("DISABLE_NOMINATIM"))
    nominatim_user_agent: Optional[str] = Field(default=None, validation_alias=AliasChoices("NOMINATIM_USER_AGENT"))
    nominatim_retries: int = Field(default=3, validation_alias=AliasChoices("NOMINATIM_RETRIES"))
    nominatim_backoff_seconds: float = Field(default=1.0, validation_alias=AliasChoices("NOMINATIM_BACKOFF_SECONDS"))

    # -------------------------
    # Taxonomy/assets (paths)
    # -------------------------
    subject_taxonomy_enabled: bool = Field(default=False, validation_alias=AliasChoices("SUBJECT_TAXONOMY_ENABLED"))
    subject_taxonomy_path: Optional[str] = Field(default=None, validation_alias=AliasChoices("SUBJECT_TAXONOMY_PATH"))
    subject_taxonomy_debug: bool = Field(default=False, validation_alias=AliasChoices("SUBJECT_TAXONOMY_DEBUG"))
    region_geojson_path: Optional[str] = Field(default=None, validation_alias=AliasChoices("REGION_GEOJSON_PATH"))
    mrt_data_json_path: Optional[str] = Field(default=None, validation_alias=AliasChoices("MRT_DATA_JSON_PATH"))

    # -------------------------
    # Misc toggles used by tools
    # -------------------------
    duplicate_detection_enabled: bool = Field(default=True, validation_alias=AliasChoices("DUPLICATE_DETECTION_ENABLED"))
    raw_fallback_file: Optional[str] = Field(default=None, validation_alias=AliasChoices("RAW_FALLBACK_FILE"))

    # A/B tools
    ab_pipeline_a: Optional[str] = Field(default=None, validation_alias=AliasChoices("AB_PIPELINE_A"))
    ab_pipeline_b: Optional[str] = Field(default=None, validation_alias=AliasChoices("AB_PIPELINE_B"))
    ab_since_iso: Optional[str] = Field(default=None, validation_alias=AliasChoices("AB_SINCE_ISO"))
    ab_until_iso: Optional[str] = Field(default=None, validation_alias=AliasChoices("AB_UNTIL_ISO"))
    ab_out_dir: Optional[str] = Field(default=None, validation_alias=AliasChoices("AB_OUT_DIR"))
    ab_extra_metrics: Optional[str] = Field(default=None, validation_alias=AliasChoices("AB_EXTRA_METRICS"))

    # Edit monitor tool
    edit_monitor_db_path: Optional[str] = Field(default=None, validation_alias=AliasChoices("EDIT_MONITOR_DB_PATH"))
    edit_monitor_events_jsonl: Optional[str] = Field(default=None, validation_alias=AliasChoices("EDIT_MONITOR_EVENTS_JSONL"))
    edit_monitor_historic_fetch: int = Field(default=50, validation_alias=AliasChoices("EDIT_MONITOR_HISTORIC_FETCH"))
    edit_monitor_include_text: bool = Field(default=True, validation_alias=AliasChoices("EDIT_MONITOR_INCLUDE_TEXT"))
    edit_monitor_max_text_chars: int = Field(default=20000, validation_alias=AliasChoices("EDIT_MONITOR_MAX_TEXT_CHARS"))
    edit_monitor_summary_interval_seconds: int = Field(default=600, validation_alias=AliasChoices("EDIT_MONITOR_SUMMARY_INTERVAL_SECONDS"))

    # TutorCity API
    tutorcity_api_url: Optional[str] = Field(default=None, validation_alias=AliasChoices("TUTORCITY_API_URL"))
    tutorcity_user_agent: Optional[str] = Field(default=None, validation_alias=AliasChoices("TUTORCITY_USER_AGENT"))
    tutorcity_limit: int = Field(default=50, validation_alias=AliasChoices("TUTORCITY_LIMIT"))
    tutorcity_timeout_seconds: int = Field(default=30, validation_alias=AliasChoices("TUTORCITY_TIMEOUT_SECONDS"))

    # Telegram retry tuning
    telegram_max_retries: int = Field(default=5, validation_alias=AliasChoices("TELEGRAM_MAX_RETRIES"))
    telegram_initial_retry_delay: float = Field(default=1.0, validation_alias=AliasChoices("TELEGRAM_INITIAL_RETRY_DELAY"))
    telegram_max_retry_delay: float = Field(default=300.0, validation_alias=AliasChoices("TELEGRAM_MAX_RETRY_DELAY"))
    telegram_backoff_multiplier: float = Field(default=2.0, validation_alias=AliasChoices("TELEGRAM_BACKOFF_MULTIPLIER"))

    @model_validator(mode="after")
    def _validate_supabase_required(self) -> "AggregatorConfig":
        url = self.supabase_rest_url
        key = self.supabase_auth_key
        if self.supabase_enabled and not url:
            raise ValueError("Missing Supabase URL (set SUPABASE_URL_HOST/SUPABASE_URL_DOCKER or SUPABASE_URL)")
        if self.supabase_enabled and not key:
            raise ValueError("Missing Supabase key (set SUPABASE_SERVICE_ROLE_KEY or SUPABASE_KEY)")
        return self

    @property
    def supabase_rest_url(self) -> str:
        url = _clean_url(self.supabase_url)
        url_docker = _clean_url(self.supabase_url_docker)
        url_host = _clean_url(self.supabase_url_host)
        if _running_in_docker():
            return (url_docker or url or url_host or "").strip().rstrip("/")
        return (url_host or url or url_docker or "").strip().rstrip("/")

    @property
    def supabase_auth_key(self) -> str:
        return (self.supabase_service_role_key or self.supabase_key or "").strip()


class BackendConfig(BaseSettings):
    """Configuration for TutorDexBackend API service."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # Environment
    app_env: str = Field(default="dev", validation_alias=AliasChoices("APP_ENV", "ENV"))
    app_host: str = Field(default="0.0.0.0", validation_alias=AliasChoices("APP_HOST"))
    app_port: int = Field(default=8000, validation_alias=AliasChoices("APP_PORT"))

    # Auth
    auth_required: bool = Field(default=True, validation_alias=AliasChoices("AUTH_REQUIRED"))
    firebase_admin_enabled: bool = Field(default=True, validation_alias=AliasChoices("FIREBASE_ADMIN_ENABLED"))
    firebase_admin_credentials_path: Optional[str] = Field(default=None, validation_alias=AliasChoices("FIREBASE_ADMIN_CREDENTIALS_PATH"))
    admin_api_key: Optional[str] = Field(default=None, validation_alias=AliasChoices("ADMIN_API_KEY"))

    # Database (Supabase routing + auth)
    supabase_url_docker: Optional[str] = Field(default=None, validation_alias=AliasChoices("SUPABASE_URL_DOCKER"))
    supabase_url_host: Optional[str] = Field(default=None, validation_alias=AliasChoices("SUPABASE_URL_HOST"))
    supabase_url: Optional[str] = Field(default=None, validation_alias=AliasChoices("SUPABASE_URL"))
    supabase_service_role_key: Optional[str] = Field(default=None, validation_alias=AliasChoices("SUPABASE_SERVICE_ROLE_KEY"))
    supabase_enabled: bool = Field(default=False, validation_alias=AliasChoices("SUPABASE_ENABLED"))

    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias=AliasChoices("REDIS_URL"))
    redis_prefix: str = Field(default="tutordex:", validation_alias=AliasChoices("REDIS_PREFIX"))

    # Pipeline metadata passthrough (used for list RPC/versioning)
    extraction_pipeline_version: str = Field(default="2026-01-02_det_time_v1", validation_alias=AliasChoices("EXTRACTION_PIPELINE_VERSION"))
    schema_version: str = Field(default="2026-01-01", validation_alias=AliasChoices("SCHEMA_VERSION"))

    # Rate limiting / CORS
    rate_limit_enabled: bool = Field(default=True, validation_alias=AliasChoices("RATE_LIMIT_ENABLED"))
    cors_allow_origins: str = Field(default="*", validation_alias=AliasChoices("CORS_ALLOW_ORIGINS"))

    # Public endpoint tuning (used by middleware and caching)
    public_assignments_limit_cap: int = Field(default=50, validation_alias=AliasChoices("PUBLIC_ASSIGNMENTS_LIMIT_CAP"))
    public_rpm_assignments: int = Field(default=60, validation_alias=AliasChoices("PUBLIC_RPM_ASSIGNMENTS"))
    public_rpm_facets: int = Field(default=120, validation_alias=AliasChoices("PUBLIC_RPM_FACETS"))
    public_cache_ttl_assignments_seconds: int = Field(default=15, validation_alias=AliasChoices("PUBLIC_CACHE_TTL_ASSIGNMENTS_SECONDS"))
    public_cache_ttl_facets_seconds: int = Field(default=30, validation_alias=AliasChoices("PUBLIC_CACHE_TTL_FACETS_SECONDS"))

    # Click tracking cooldown (used by AnalyticsService)
    click_tracking_ip_cooldown_seconds: int = Field(default=10, validation_alias=AliasChoices("CLICK_TRACKING_IP_COOLDOWN_SECONDS"))

    # Matching
    match_min_score: int = Field(default=3, validation_alias=AliasChoices("MATCH_MIN_SCORE"))

    # Telegram bot tokens (webhooks/edit tracking)
    group_bot_token: Optional[str] = Field(default=None, validation_alias=AliasChoices("GROUP_BOT_TOKEN"))
    tracking_edit_bot_token: Optional[str] = Field(default=None, validation_alias=AliasChoices("TRACKING_EDIT_BOT_TOKEN"))
    webhook_secret_token: Optional[str] = Field(default=None, validation_alias=AliasChoices("WEBHOOK_SECRET_TOKEN"))
    webhook_secret_token_dm: Optional[str] = Field(default=None, validation_alias=AliasChoices("WEBHOOK_SECRET_TOKEN_DM"))
    webhook_secret_token_group: Optional[str] = Field(default=None, validation_alias=AliasChoices("WEBHOOK_SECRET_TOKEN_GROUP"))
    dm_bot_token: Optional[str] = Field(default=None, validation_alias=AliasChoices("DM_BOT_TOKEN"))
    backend_url: Optional[str] = Field(default=None, validation_alias=AliasChoices("BACKEND_URL"))
    link_bot_offset_file: Optional[str] = Field(default=None, validation_alias=AliasChoices("LINK_BOT_OFFSET_FILE"))

    # Observability
    log_level: str = Field(default="INFO", validation_alias=AliasChoices("LOG_LEVEL"))
    log_dir: Optional[str] = Field(default=None, validation_alias=AliasChoices("LOG_DIR"))
    log_file: Optional[str] = Field(default=None, validation_alias=AliasChoices("LOG_FILE"))
    log_json: bool = Field(default=False, validation_alias=AliasChoices("LOG_JSON"))
    log_to_console: bool = Field(default=True, validation_alias=AliasChoices("LOG_TO_CONSOLE"))
    log_to_file: bool = Field(default=True, validation_alias=AliasChoices("LOG_TO_FILE"))
    log_max_bytes: int = Field(default=5_000_000, validation_alias=AliasChoices("LOG_MAX_BYTES"))
    log_backup_count: int = Field(default=5, validation_alias=AliasChoices("LOG_BACKUP_COUNT"))
    otel_enabled: bool = Field(default=False, validation_alias=AliasChoices("OTEL_ENABLED"))
    otel_exporter_otlp_endpoint: str = Field(default="http://otel-collector:4318", validation_alias=AliasChoices("OTEL_EXPORTER_OTLP_ENDPOINT"))
    otel_service_name: Optional[str] = Field(default=None, validation_alias=AliasChoices("OTEL_SERVICE_NAME"))

    sentry_dsn: Optional[str] = Field(default=None, validation_alias=AliasChoices("SENTRY_DSN"))
    sentry_environment: str = Field(default="production", validation_alias=AliasChoices("SENTRY_ENVIRONMENT"))
    sentry_release: Optional[str] = Field(default=None, validation_alias=AliasChoices("SENTRY_RELEASE"))
    sentry_traces_sample_rate: Optional[float] = Field(default=None, validation_alias=AliasChoices("SENTRY_TRACES_SAMPLE_RATE"))
    sentry_profiles_sample_rate: Optional[float] = Field(default=None, validation_alias=AliasChoices("SENTRY_PROFILES_SAMPLE_RATE"))

    # Nominatim (shared user agent override)
    disable_nominatim: bool = Field(default=False, validation_alias=AliasChoices("DISABLE_NOMINATIM"))
    nominatim_user_agent: Optional[str] = Field(default=None, validation_alias=AliasChoices("NOMINATIM_USER_AGENT"))

    @model_validator(mode="after")
    def _validate_supabase_required(self) -> "BackendConfig":
        url = self.supabase_rest_url
        key = self.supabase_auth_key
        if self.supabase_enabled and not url:
            raise ValueError("Missing Supabase URL (set SUPABASE_URL_HOST/SUPABASE_URL_DOCKER or SUPABASE_URL)")
        if self.supabase_enabled and not key:
            raise ValueError("Missing Supabase key (set SUPABASE_SERVICE_ROLE_KEY)")
        return self

    @property
    def supabase_rest_url(self) -> str:
        url = _clean_url(self.supabase_url)
        url_docker = _clean_url(self.supabase_url_docker)
        url_host = _clean_url(self.supabase_url_host)
        if _running_in_docker():
            return (url_docker or url or url_host or "").strip().rstrip("/")
        return (url_host or url or url_docker or "").strip().rstrip("/")

    @property
    def supabase_auth_key(self) -> str:
        return (self.supabase_service_role_key or "").strip()


class WebsiteConfig(BaseSettings):
    """Configuration for TutorDexWebsite (Vite env vars)."""

    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore", env_prefix="VITE_")

    firebase_api_key: str = Field(..., validation_alias=AliasChoices("VITE_FIREBASE_API_KEY"))
    firebase_auth_domain: str = Field(..., validation_alias=AliasChoices("VITE_FIREBASE_AUTH_DOMAIN"))
    firebase_project_id: str = Field(..., validation_alias=AliasChoices("VITE_FIREBASE_PROJECT_ID"))
    firebase_storage_bucket: Optional[str] = Field(default=None, validation_alias=AliasChoices("VITE_FIREBASE_STORAGE_BUCKET"))
    firebase_messaging_sender_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("VITE_FIREBASE_MESSAGING_SENDER_ID"))
    firebase_app_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("VITE_FIREBASE_APP_ID"))

    backend_api_url: str = Field(default="http://localhost:8000", validation_alias=AliasChoices("VITE_BACKEND_API_URL", "VITE_BACKEND_URL"))

    sentry_dsn: Optional[str] = Field(default=None, validation_alias=AliasChoices("VITE_SENTRY_DSN"))
    sentry_environment: str = Field(default="production", validation_alias=AliasChoices("VITE_SENTRY_ENVIRONMENT"))
    sentry_sample_rate: float = Field(default=0.1, validation_alias=AliasChoices("VITE_SENTRY_SAMPLE_RATE"))


@lru_cache(maxsize=4)
def _cached_aggregator_config(env_file_str: Optional[str]) -> AggregatorConfig:
    env_file = Path(env_file_str) if env_file_str else None
    candidates = [env_file] if env_file else _env_file_candidates("TutorDexAggregator")
    existing = [p for p in candidates if p and p.exists()]
    return AggregatorConfig(_env_file=existing or None, _env_file_encoding="utf-8")  # type: ignore[arg-type]


def load_aggregator_config(*, env_file: Optional[Path] = None) -> AggregatorConfig:
    return _cached_aggregator_config(str(env_file) if env_file else None)


@lru_cache(maxsize=4)
def _cached_backend_config(env_file_str: Optional[str]) -> BackendConfig:
    env_file = Path(env_file_str) if env_file_str else None
    candidates = [env_file] if env_file else _env_file_candidates("TutorDexBackend")
    existing = [p for p in candidates if p and p.exists()]
    return BackendConfig(_env_file=existing or None, _env_file_encoding="utf-8")  # type: ignore[arg-type]


def load_backend_config(*, env_file: Optional[Path] = None) -> BackendConfig:
    return _cached_backend_config(str(env_file) if env_file else None)


def load_website_config(*, env_file: Optional[Path] = None) -> WebsiteConfig:
    candidates = [env_file] if env_file else _env_file_candidates("TutorDexWebsite")
    existing = [p for p in candidates if p and p.exists()]
    return WebsiteConfig(_env_file=existing or None, _env_file_encoding="utf-8")  # type: ignore[arg-type]


def validate_environment_integrity(cfg: BaseSettings) -> None:
    """
    Validate that environment configuration is internally consistent.
    
    Raises RuntimeError if dangerous misconfigurations detected.
    """
    app_env = str(getattr(cfg, "app_env", "dev")).strip().lower()
    
    if app_env in {"prod", "production"}:
        # Production environment checks
        supabase_url = str(getattr(cfg, "supabase_url", "") or "").strip().lower()
        
        # Example validation: prod should not use :54322 (staging supabase port)
        if ":54322" in supabase_url:
            raise RuntimeError(
                "FATAL CONFIGURATION ERROR:\n"
                "APP_ENV=prod but SUPABASE_URL contains staging port :54322\n"
                "This configuration would write production data to staging database.\n"
                "Fix: Update .env.prod to use production Supabase URL (port :54321)"
            )
        
        # Check 2: Prod requires authentication
        if hasattr(cfg, "auth_required") and not getattr(cfg, "auth_required", True):
            raise RuntimeError(
                "FATAL CONFIGURATION ERROR:\n"
                "APP_ENV=prod but AUTH_REQUIRED=false\n"
                "Production must have authentication enabled.\n"
                "Fix: Set AUTH_REQUIRED=true in .env.prod"
            )
        
        # Check 3: Prod requires Firebase admin
        if hasattr(cfg, "firebase_admin_enabled") and not getattr(cfg, "firebase_admin_enabled", False):
            raise RuntimeError(
                "FATAL CONFIGURATION ERROR:\n"
                "APP_ENV=prod but FIREBASE_ADMIN_ENABLED=false\n"
                "Production must have Firebase authentication enabled.\n"
                "Fix: Set FIREBASE_ADMIN_ENABLED=true in .env.prod"
            )
        
        # Check 4: Prod requires admin API key
        if hasattr(cfg, "admin_api_key"):
            admin_key = str(getattr(cfg, "admin_api_key", "") or "").strip()
            if not admin_key or admin_key == "changeme" or len(admin_key) < 32:
                raise RuntimeError(
                    "FATAL CONFIGURATION ERROR:\n"
                    "APP_ENV=prod but ADMIN_API_KEY is missing or weak\n"
                    "Production must have a strong admin API key.\n"
                    "Fix: Set ADMIN_API_KEY to a secure random string in .env.prod"
                )
    
    elif app_env == "staging":
        # Staging environment checks
        supabase_url = str(getattr(cfg, "supabase_url", "") or "").strip().lower()
        
        # Check 1: Staging should not use production Supabase port
        if ":54321" in supabase_url and ":54322" not in supabase_url:
            raise RuntimeError(
                "FATAL CONFIGURATION ERROR:\n"
                "APP_ENV=staging but SUPABASE_URL contains production port :54321\n"
                "This configuration would write staging test data to production database.\n"
                "Fix: Update .env.staging to use staging Supabase URL (port :54322)"
            )
        
        # Check 2: Warn if broadcast enabled in staging (allow but warn)
        if hasattr(cfg, "enable_broadcast") and getattr(cfg, "enable_broadcast", False):
            import logging
            logging.warning(
                "STAGING BROADCAST ENABLED: "
                "ENABLE_BROADCAST=true in staging environment. "
                "Ensure AGGREGATOR_CHANNEL_ID points to a test channel, not production channel."
            )
        
        # Check 3: Warn if DMs enabled in staging
        if hasattr(cfg, "enable_dms") and getattr(cfg, "enable_dms", False):
            import logging
            logging.warning(
                "STAGING DMs ENABLED: "
                "ENABLE_DMS=true in staging environment. "
                "Ensure only test tutor accounts will receive DMs."
            )
