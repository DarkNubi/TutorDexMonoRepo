from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

import requests

from workers.extract_worker_types import VersionInfo
from workers.job_manager import merge_meta
from workers.message_processor import load_channel_info
from workers.supabase_operations import patch_table
from workers.utils import utc_now_iso


def supabase_cfg(cfg: Any) -> Tuple[str, str]:
    url = getattr(cfg, "supabase_rest_url", None)
    key = getattr(cfg, "supabase_auth_key", None)
    enabled = bool(getattr(cfg, "supabase_enabled", False))
    if not (enabled and url and key):
        raise SystemExit("Supabase not enabled/misconfigured. Check SUPABASE_* settings in .env.")
    return str(url), str(key)


def channel_info_cached(
    *,
    channel_cache: Dict[str, Dict[str, Any]],
    url: str,
    key: str,
    channel_link: str,
    version: VersionInfo,
) -> Dict[str, Any]:
    if channel_link in channel_cache:
        return channel_cache[channel_link]
    info = load_channel_info(url, key, channel_link, pipeline_version=version.pipeline_version, schema_version=version.schema_version) or {}
    if isinstance(info, dict):
        channel_cache[channel_link] = info
        return info
    channel_cache[channel_link] = {}
    return {}


def mark_extraction(
    url: str,
    key: str,
    extraction_id: Any,
    *,
    status: str,
    version: VersionInfo,
    canonical_json: Any = None,
    error: Any = None,
    meta_patch: Optional[Dict[str, Any]] = None,
    existing_meta: Any = None,
    llm_model: Optional[str] = None,
) -> None:
    body: Dict[str, Any] = {"status": status, "updated_at": utc_now_iso()}
    if canonical_json is not None:
        body["canonical_json"] = canonical_json
    if error is not None:
        body["error_json"] = error
    merged = merge_meta(existing_meta, meta_patch)
    if merged is not None:
        body["meta"] = merged
    if llm_model:
        body["llm_model"] = llm_model

    where = f"id=eq.{requests.utils.quote(str(extraction_id), safe='')}"
    ok = patch_table(
        url,
        key,
        "telegram_extractions",
        where,
        body,
        timeout=30,
        pipeline_version=version.pipeline_version,
        schema_version=version.schema_version,
    )

    if not ok and ("error_json" in body or "llm_model" in body):
        body2 = dict(body)
        body2.pop("updated_at", None)
        if "error_json" in body2:
            body2["stage_b_errors"] = body2.pop("error_json")
        if "llm_model" in body2:
            body2["model_a"] = body2.pop("llm_model")
        patch_table(
            url,
            key,
            "telegram_extractions",
            where,
            body2,
            timeout=30,
            pipeline_version=version.pipeline_version,
            schema_version=version.schema_version,
        )

