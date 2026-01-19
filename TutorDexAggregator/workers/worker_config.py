"""
Worker configuration management.

Handles environment variable loading and provides typed configuration
for all worker settings.
"""

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("worker_config")


@dataclass
class WorkerConfig:
    """Configuration for the extraction worker."""

    # Pipeline configuration
    pipeline_version: str
    schema_version: str

    # Job claiming and processing
    claim_batch_size: int
    idle_sleep_seconds: float
    max_attempts: int
    backoff_base_seconds: float
    backoff_max_seconds: float
    stale_processing_seconds: int

    # Processing options
    use_normalized_text_for_llm: bool
    hard_validate_mode: str  # "off", "report", or "enforce"
    enable_deterministic_signals: bool
    use_deterministic_time: bool
    enable_postal_code_estimated: bool

    # Side-effects
    enable_broadcast: bool
    enable_dms: bool

    # Oneshot mode
    oneshot: bool
    max_jobs: int

    # Supabase
    supabase_url: str
    supabase_key: str


def load_env_file(env_path: Optional[Path] = None) -> None:
    """
    Load environment variables from .env file.

    Args:
        env_path: Path to .env file (if None, uses AGG_DIR/.env)
    """
    try:
        from dotenv import load_dotenv
        if env_path:
            load_dotenv(env_path)
        else:
            load_dotenv()
    except ImportError:
        # dotenv not installed, try manual parse
        if env_path is None:
            env_path = Path(__file__).resolve().parents[1] / ".env"

        if not env_path.exists():
            return

        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, _, v = line.partition("=")
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    if k and k not in os.environ:
                        os.environ[k] = v
        except Exception:
            logger.debug("env_parse_failed", exc_info=True)


def get_supabase_config() -> Tuple[str, str]:
    """
    Get Supabase URL and key from environment.

    Returns:
        Tuple of (url, key)

    Raises:
        SystemExit: If Supabase is not properly configured
    """
    from supabase_env import resolve_supabase_url

    url = resolve_supabase_url()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()

    enabled = truthy(os.environ.get("SUPABASE_ENABLED")) and bool(url and key)
    if not enabled:
        raise SystemExit(
            "Supabase not enabled. Set SUPABASE_ENABLED=1, SUPABASE_SERVICE_ROLE_KEY, "
            "and one of SUPABASE_URL_HOST / SUPABASE_URL_DOCKER / SUPABASE_URL."
        )

    return url, key


def truthy(value: Optional[str]) -> bool:
    """Check if environment variable value is truthy."""
    if not value:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def load_worker_config() -> WorkerConfig:
    """
    Load worker configuration from environment variables.

    Returns:
        WorkerConfig instance with all settings
    """
    # Load .env file first
    load_env_file()

    # Get Supabase config
    supabase_url, supabase_key = get_supabase_config()

    # Get versions
    pipeline_version = (os.environ.get("EXTRACTION_PIPELINE_VERSION") or "2026-01-02_det_time_v1").strip()
    schema_version = (os.environ.get("SCHEMA_VERSION") or "v1").strip()

    # Job processing settings
    claim_batch_size = int(os.environ.get("EXTRACTION_CLAIM_BATCH_SIZE") or "10")
    idle_sleep_seconds = float(os.environ.get("EXTRACTION_IDLE_SLEEP_SECONDS") or "2.0")
    max_attempts = int(os.environ.get("EXTRACTION_MAX_ATTEMPTS") or "3")
    backoff_base_seconds = float(os.environ.get("EXTRACTION_BACKOFF_BASE_SECONDS") or "1.5")
    backoff_max_seconds = float(os.environ.get("EXTRACTION_BACKOFF_MAX_SECONDS") or "60.0")
    stale_processing_seconds = int(os.environ.get("EXTRACTION_STALE_PROCESSING_SECONDS") or "900")

    # Processing options
    use_normalized_text = truthy(os.environ.get("USE_NORMALIZED_TEXT_FOR_LLM"))
    hard_validate_mode = (os.environ.get("HARD_VALIDATE_MODE") or "report").strip()
    enable_signals = truthy(os.environ.get("ENABLE_DETERMINISTIC_SIGNALS", "1"))
    use_det_time = truthy(os.environ.get("USE_DETERMINISTIC_TIME", "1"))
    enable_postal = truthy(os.environ.get("ENABLE_POSTAL_CODE_ESTIMATED", "1"))

    # Side-effects
    enable_broadcast = truthy(os.environ.get("ENABLE_BROADCAST", "1"))
    enable_dms = truthy(os.environ.get("ENABLE_DMS", "1"))

    # Oneshot mode
    oneshot = truthy(os.environ.get("EXTRACTION_WORKER_ONESHOT"))
    max_jobs = int(os.environ.get("EXTRACTION_WORKER_MAX_JOBS") or "0")
    if max_jobs < 0:
        max_jobs = 0

    return WorkerConfig(
        pipeline_version=pipeline_version,
        schema_version=schema_version,
        claim_batch_size=claim_batch_size,
        idle_sleep_seconds=idle_sleep_seconds,
        max_attempts=max_attempts,
        backoff_base_seconds=backoff_base_seconds,
        backoff_max_seconds=backoff_max_seconds,
        stale_processing_seconds=stale_processing_seconds,
        use_normalized_text_for_llm=use_normalized_text,
        hard_validate_mode=hard_validate_mode,
        enable_deterministic_signals=enable_signals,
        use_deterministic_time=use_det_time,
        enable_postal_code_estimated=enable_postal,
        enable_broadcast=enable_broadcast,
        enable_dms=enable_dms,
        oneshot=oneshot,
        max_jobs=max_jobs,
        supabase_url=supabase_url,
        supabase_key=supabase_key,
    )
