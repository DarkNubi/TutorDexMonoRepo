"""
LLM processing for the extraction worker.

Handles LLM extraction with circuit breaker protection and error classification.
"""

import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

from circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

logger = logging.getLogger("llm_processor")


def get_llm_model_name() -> str:
    """Get LLM model name from environment."""
    return (os.environ.get("LLM_MODEL_NAME") or "").strip() or "unknown"


def classify_llm_error(err: Exception) -> str:
    """
    Classify LLM error for metrics and debugging.
    
    Categories:
    - llm_timeout: Timeout errors
    - llm_connection: Connection errors
    - llm_invalid_json: JSON parsing errors
    - llm_bad_response: Bad response format
    - llm_error: Other errors
    """
    s = str(err or "").lower()

    if "timeout" in s or "timed out" in s:
        return "llm_timeout"

    if "connection" in s or "connection refused" in s or "failed to establish a new connection" in s:
        return "llm_connection"

    if "failed to parse json" in s or "json parsing" in s or "json parse" in s:
        return "llm_invalid_json"

    if "failed to parse llm response" in s or "no valid text found" in s:
        return "llm_bad_response"

    return "llm_error"


def extract_with_llm(
    text: str,
    channel: str,
    cid: str,
    circuit_breaker: CircuitBreaker,
    extract_func: Any,
    metrics: Optional[Dict[str, Any]] = None
) -> Tuple[Optional[Dict[str, Any]], Optional[str], float]:
    """
    Extract assignment data using LLM with circuit breaker protection.
    
    Args:
        text: Text to extract from
        channel: Channel name for context
        cid: Correlation ID for logging
        circuit_breaker: Circuit breaker instance
        extract_func: Function to call for extraction (e.g., extract_assignment_with_model)
        metrics: Optional dict to track metrics
        
    Returns:
        Tuple of (parsed_data, error_type, latency_seconds)
    """
    model = get_llm_model_name()
    t0 = time.perf_counter()

    # Track request
    if metrics and "llm_requests_total" in metrics:
        try:
            metrics["llm_requests_total"].labels(
                model=model,
                pipeline_version=metrics.get("pipeline_version", ""),
                schema_version=metrics.get("schema_version", "")
            ).inc()
        except Exception:
            pass  # Metrics must never break runtime

    try:
        if circuit_breaker:
            parsed = circuit_breaker.call(extract_func, text, chat=channel, cid=cid)
        else:
            parsed = extract_func(text, chat=channel, cid=cid)

        if not isinstance(parsed, dict):
            parsed = {}

        latency = time.perf_counter() - t0

        # Track latency
        if metrics and "llm_call_latency_seconds" in metrics:
            try:
                metrics["llm_call_latency_seconds"].labels(
                    pipeline_version=metrics.get("pipeline_version", ""),
                    schema_version=metrics.get("schema_version", "")
                ).observe(latency)
            except Exception:
                pass  # Metrics must never break runtime

        return parsed, None, latency

    except CircuitBreakerOpenError as e:
        # Circuit breaker is open - fail fast
        logger.warning(f"Circuit breaker open for LLM extraction: {e}")
        latency = time.perf_counter() - t0

        if metrics and "llm_fail_total" in metrics:
            try:
                metrics["llm_fail_total"].labels(
                    pipeline_version=metrics.get("pipeline_version", ""),
                    schema_version=metrics.get("schema_version", "")
                ).inc()
            except Exception:
                pass  # Metrics must never break runtime

        return None, "llm_circuit_open", latency

    except Exception as e:
        # Extraction failed
        error_type = classify_llm_error(e)
        logger.warning(f"LLM extraction failed: {error_type} - {e}")
        latency = time.perf_counter() - t0

        if metrics and "llm_fail_total" in metrics:
            try:
                metrics["llm_fail_total"].labels(
                    pipeline_version=metrics.get("pipeline_version", ""),
                    schema_version=metrics.get("schema_version", "")
                ).inc()
            except Exception:
                pass  # Metrics must never break runtime

        return None, error_type, latency


def get_prompt_metadata(get_system_prompt_meta_func: Any) -> Optional[Dict[str, Any]]:
    """
    Get system prompt metadata.
    
    Args:
        get_system_prompt_meta_func: Function to get prompt metadata
        
    Returns:
        Prompt metadata dict or None
    """
    try:
        prompt_meta = get_system_prompt_meta_func()
        if not isinstance(prompt_meta, dict) or not prompt_meta:
            return None
        return prompt_meta
    except Exception:
        return None


def get_examples_metadata(get_examples_meta_func: Any, channel: str) -> Optional[Dict[str, Any]]:
    """
    Get examples metadata for channel.
    
    Args:
        get_examples_meta_func: Function to get examples metadata
        channel: Channel name
        
    Returns:
        Examples metadata dict or None
    """
    try:
        examples_meta = get_examples_meta_func(channel)
        if not isinstance(examples_meta, dict) or not examples_meta:
            return None
        return examples_meta
    except Exception:
        return None
