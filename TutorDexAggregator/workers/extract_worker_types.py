from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VersionInfo:
    pipeline_version: str
    schema_version: str


@dataclass(frozen=True)
class WorkerToggles:
    enable_broadcast: bool
    enable_dms: bool
    max_attempts: int
    backoff_base_s: float
    backoff_max_s: float
    stale_processing_seconds: int
    use_normalized_text_for_llm: bool
    hard_validate_mode: str
    enable_deterministic_signals: bool
    use_deterministic_time: bool
    enable_postal_code_estimated: bool

