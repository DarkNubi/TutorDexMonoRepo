from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from shared.config import load_aggregator_config

try:
    from logging_setup import bind_log_context, log_event  # type: ignore
except Exception:
    from TutorDexAggregator.logging_setup import bind_log_context, log_event  # type: ignore

try:
    from supabase_raw_persist import SupabaseRawStore  # type: ignore
except Exception:
    from TutorDexAggregator.supabase_raw_persist import SupabaseRawStore  # type: ignore

logger = logging.getLogger("recovery.catchup")


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


@dataclass(frozen=True)
class CatchupConfig:
    enabled: bool
    state_path: Path
    target_lag_minutes: int
    overlap_minutes: int
    chunk_hours: int
    low_watermark: int
    check_interval_s: float
    pipeline_version: str
    recovery_session_name: str


def load_catchup_config(*, agg_dir: Path) -> CatchupConfig:
    cfg = load_aggregator_config()
    enabled = bool(cfg.recovery_catchup_enabled)
    state_rel = str(cfg.recovery_catchup_state_file or "state/recovery_catchup_state.json").strip()
    state_candidate = Path(state_rel).expanduser()
    state_path = state_candidate if state_candidate.is_absolute() else (agg_dir / state_candidate).resolve()

    target_lag_minutes = int(cfg.recovery_catchup_target_lag_minutes)
    overlap_minutes = int(cfg.recovery_catchup_overlap_minutes)
    chunk_hours = int(cfg.recovery_catchup_chunk_hours)
    low_watermark = int(cfg.recovery_catchup_queue_low_watermark)
    check_interval_s = float(cfg.recovery_catchup_check_interval_seconds)
    pipeline_version = str(cfg.extraction_pipeline_version or "2026-01-02_det_time_v1").strip() or "2026-01-02_det_time_v1"

    recovery_session_name = str(cfg.telegram_session_recovery or "tutordex_recovery.session").strip() or "tutordex_recovery.session"

    return CatchupConfig(
        enabled=enabled,
        state_path=state_path,
        target_lag_minutes=max(0, min(60, target_lag_minutes)),
        overlap_minutes=max(0, min(120, overlap_minutes)),
        chunk_hours=max(1, min(72, chunk_hours)),
        low_watermark=max(0, low_watermark),
        check_interval_s=max(5.0, min(600.0, check_interval_s)),
        pipeline_version=pipeline_version,
        recovery_session_name=recovery_session_name,
    )


def build_initial_state(
    *,
    channels: List[str],
    store: SupabaseRawStore,
    config: CatchupConfig,
    default_lookback_hours: int = 168,
) -> Dict[str, Any]:
    """
    Creates a resumable state snapshot for catchup after a restart.

    Strategy:
    - Use latest raw message in DB (best-effort).
    - Fallback to `now - default_lookback_hours` to avoid a null start.
    """
    now = _utc_now()
    cursors: Dict[str, str] = {}
    for ch in channels:
        latest = store.get_latest_message_cursor(channel_link=ch)
        dt = _parse_iso_dt(latest[0]) if latest and latest[0] else None
        if dt is None:
            dt = now - timedelta(hours=max(1, int(default_lookback_hours)))
        cursors[ch] = _iso(dt)

    target = now - timedelta(minutes=config.target_lag_minutes)
    return {
        "version": 1,
        "created_at": _iso(now),
        "pipeline_version": config.pipeline_version,
        "target_iso": _iso(target),
        "cursors": cursors,  # channel_link -> cursor_iso
        "status": "running",
        "last_update_at": _iso(now),
        "errors": [],
    }


def _parse_count_from_range(rng: Optional[str]) -> Optional[int]:
    if not rng or "/" not in rng:
        return None
    try:
        return int(rng.split("/")[-1])
    except Exception:
        return None


def _queue_backlog(store: SupabaseRawStore, *, pipeline_version: str) -> int:
    """
    Returns pending+processing count for the pipeline version (best-effort).
    """
    if not store.cfg.enabled:
        return 0
    h = {
        "apikey": store.cfg.key,
        "authorization": f"Bearer {store.cfg.key}",
        "content-type": "application/json",
        "prefer": "count=exact",
    }
    # Use two requests (simpler + clearer logs).
    total = 0
    for st in ("pending", "processing"):
        resp = requests.get(
            f"{store.cfg.url}/rest/v1/telegram_extractions?select=id&pipeline_version=eq.{requests.utils.quote(pipeline_version, safe='')}&status=eq.{st}&limit=0",
            headers=h,
            timeout=15,
        )
        total += int(_parse_count_from_range(resp.headers.get("content-range")) or 0)
    return total


def _load_or_init_state(*, state_path: Path, initial_state: Dict[str, Any]) -> Dict[str, Any]:
    existing = _read_json(state_path)
    if isinstance(existing, dict) and existing.get("status") == "running" and isinstance(existing.get("cursors"), dict):
        return existing
    _atomic_write_json(state_path, initial_state)
    return initial_state


def _update_state(state_path: Path, state: Dict[str, Any], patch: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(state)
    merged.update(patch)
    merged["last_update_at"] = _iso(_utc_now())
    _atomic_write_json(state_path, merged)
    return merged


async def run_catchup_until_target(
    *,
    agg_dir: Path,
    channels: List[str],
    store: SupabaseRawStore,
    config: CatchupConfig,
) -> None:
    """
    Cursor-based catchup from the last known "tail watermark" up to `target_iso`, throttled by queue backlog.

    This is intended to run alongside `collector.py tail` after a restart. It will stop once caught up.
    """
    if not config.enabled:
        return
    if not store.enabled():
        log_event(logger, logging.WARNING, "recovery_catchup_disabled_no_supabase", enabled=False)
        return
    if not channels:
        return

    initial_state = build_initial_state(channels=channels, store=store, config=config)
    state = _load_or_init_state(state_path=config.state_path, initial_state=initial_state)

    target_dt = _parse_iso_dt(str(state.get("target_iso") or "")) or (_utc_now() - timedelta(minutes=config.target_lag_minutes))
    cursors_raw = state.get("cursors") if isinstance(state.get("cursors"), dict) else {}

    # Lazy imports so tests can import this module without Telethon installed.
    from telethon import TelegramClient  # type: ignore

    try:
        from telethon.sessions import StringSession  # type: ignore
    except Exception:
        StringSession = None

    cfg = load_aggregator_config()
    api_id_raw = str(cfg.telegram_api_id or "").strip()
    try:
        api_id = int(api_id_raw) if api_id_raw else 0
    except Exception:
        api_id = 0
    api_hash = str(cfg.telegram_api_hash or "").strip()
    if not api_id or not api_hash:
        log_event(logger, logging.WARNING, "recovery_missing_telegram_creds", api_id=bool(api_id), api_hash=bool(api_hash))
        return

    # If you already run tail with `SESSION_STRING`, reuse it for catchup unless explicitly overridden.
    # This avoids needing a second authenticated session in many deployments.
    session_string = str(cfg.session_string_recovery or cfg.session_string or "").strip()
    if session_string and StringSession is not None:
        recovery_client = TelegramClient(StringSession(session_string), api_id, api_hash)
    else:
        recovery_client = TelegramClient(config.recovery_session_name, api_id, api_hash)

    await recovery_client.connect()
    try:
        # Import backfill helper from collector (single source of truth for backfill semantics).
        import collector as collector_mod  # type: ignore

        run_id = store.create_run(
            run_type="recovery_catchup",
            channels=channels,
            meta={
                "pipeline_version": config.pipeline_version,
                "target_iso": _iso(target_dt),
                "chunk_hours": config.chunk_hours,
                "overlap_minutes": config.overlap_minutes,
                "low_watermark": config.low_watermark,
            },
        )

        while True:
            backlog = _queue_backlog(store, pipeline_version=config.pipeline_version)
            if backlog > config.low_watermark:
                log_event(logger, logging.INFO, "recovery_wait_queue", backlog=backlog, low_watermark=config.low_watermark)
                await asyncio_sleep(config.check_interval_s)
                continue

            any_progress = False
            for ch in channels:
                cursor_dt = _parse_iso_dt(str(cursors_raw.get(ch) or "")) or (target_dt - timedelta(days=7))
                if cursor_dt >= target_dt:
                    continue

                next_until = min(target_dt, cursor_dt + timedelta(hours=config.chunk_hours))
                since = cursor_dt - timedelta(minutes=config.overlap_minutes) if config.overlap_minutes else cursor_dt
                until = next_until

                with bind_log_context(step="raw.recovery.catchup", channel=ch):
                    log_event(logger, logging.INFO, "recovery_catchup_window_start", channel=ch, since=_iso(since), until=_iso(until), run_id=run_id)
                    # Retry/backoff wrapper for backfill to tolerate transient Telethon/network errors.
                    max_attempts = max(1, int(cfg.recovery_backfill_max_attempts))
                    base_backoff = float(cfg.recovery_backfill_base_backoff_seconds)
                    last_exc = None
                    res = None
                    for attempt in range(1, max_attempts + 1):
                        try:
                            res = await collector_mod.backfill_channel(  # type: ignore[attr-defined]
                                client=recovery_client,
                                store=store,
                                run_id=run_id,
                                channel_ref=ch,
                                since=since,
                                until=until,
                                batch_size=200,
                                max_messages=None,
                                force_enqueue=False,
                            )
                            last_exc = None
                            break
                        except Exception as e:
                            last_exc = e
                            log_event(
                                logger,
                                logging.WARNING,
                                "recovery_backfill_attempt_failed",
                                channel=ch,
                                attempt=attempt,
                                max_attempts=max_attempts,
                                error=str(e)[:500],
                            )
                            if attempt >= max_attempts:
                                # re-raise after exhausting attempts so outer handler records the error
                                raise
                            # exponential backoff (jittered by small amount)
                            wait_s = min(300.0, base_backoff * (2 ** (attempt - 1)))
                            await asyncio_sleep(wait_s + (0.1 * attempt))
                    log_event(
                        logger,
                        logging.INFO,
                        "recovery_catchup_window_done",
                        channel=ch,
                        scanned=res.scanned,
                        written=res.written,
                        errors=res.errors,
                        until=_iso(until),
                        run_id=run_id,
                    )

                cursors_raw[ch] = _iso(next_until)
                any_progress = True
                state = _update_state(config.state_path, state, {"cursors": dict(cursors_raw)})

            if not any_progress:
                break

            await asyncio_sleep(config.check_interval_s)

        state = _update_state(config.state_path, state, {"status": "ok"})
        store.finish_run(run_id=run_id, status="ok", meta_patch={"finished_at": _iso(_utc_now())})
        log_event(logger, logging.INFO, "recovery_catchup_done", target_iso=_iso(target_dt))
    except Exception as e:
        log_event(logger, logging.WARNING, "recovery_catchup_failed", error=str(e))
        try:
            errors = state.get("errors")
            if not isinstance(errors, list):
                errors = []
            errors.append({"ts": int(time.time()), "error": str(e)[:500]})
            _update_state(config.state_path, state, {"errors": errors})
        except Exception:
            pass
    finally:
        await recovery_client.disconnect()


async def asyncio_sleep(seconds: float) -> None:
    # Local helper to keep imports minimal (collector already uses asyncio).
    import asyncio

    await asyncio.sleep(max(0.0, float(seconds)))
