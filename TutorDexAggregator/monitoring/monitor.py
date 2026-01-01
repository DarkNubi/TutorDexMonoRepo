import json
import os
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip()


def _env_int(name: str, default: int) -> int:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return int(str(v).strip())
    except Exception:
        return default


def _env_float(name: str, default: float) -> float:
    v = os.environ.get(name)
    if v is None:
        return default
    try:
        return float(str(v).strip())
    except Exception:
        return default


@dataclass(frozen=True)
class MonitorConfig:
    # Telegram alerts
    bot_token: str
    chat_id: str
    thread_id: Optional[int]
    alert_prefix: str

    # Files
    raw_heartbeat_path: Path
    queue_heartbeat_path: Path
    log_path: Path
    state_path: Path

    # Health checks
    backend_health_url: str

    # Thresholds / cadence
    check_interval_s: float
    cooldown_s: int
    heartbeat_stale_s: int
    log_stale_s: int
    error_burst_limit: int

    # Daily summary
    daily_summary_enabled: bool
    daily_summary_hour_local: int


def load_config() -> MonitorConfig:
    here = Path(__file__).resolve().parent
    agg_dir = here.parent

    # Optional dotenv support (same pattern as rest of repo).
    try:
        from dotenv import load_dotenv  # type: ignore
    except Exception:
        load_dotenv = None
    env_path = agg_dir / ".env"
    if load_dotenv and env_path.exists():
        load_dotenv(dotenv_path=env_path)

    bot_token = _env("ALERT_BOT_TOKEN", _env("GROUP_BOT_TOKEN", ""))
    chat_id = _env("ALERT_CHAT_ID", _env("SKIPPED_MESSAGES_CHAT_ID", ""))
    thread_raw = _env("ALERT_THREAD_ID", _env("SKIPPED_MESSAGES_THREAD_ID", ""))
    thread_id = None
    if thread_raw.strip():
        try:
            thread_id = int(thread_raw)
        except Exception:
            thread_id = None

    raw_hb_rel = _env("MONITOR_RAW_HEARTBEAT_FILE", _env("RAW_HEARTBEAT_FILE", "monitoring/heartbeat_raw_collector.json"))
    raw_heartbeat_path = (agg_dir / raw_hb_rel).resolve()

    queue_hb_rel = _env("MONITOR_QUEUE_HEARTBEAT_FILE", _env("EXTRACTION_QUEUE_HEARTBEAT_FILE", "monitoring/heartbeat_queue_worker.json"))
    queue_heartbeat_path = (agg_dir / queue_hb_rel).resolve()

    log_dir = _env("LOG_DIR", str(agg_dir / "logs"))
    log_file = _env("LOG_FILE", "tutordex_aggregator.log")
    log_path = Path(_env("MONITOR_LOG_PATH", str(Path(log_dir) / log_file))).resolve()

    state_path = Path(_env("MONITOR_STATE_PATH", str(agg_dir / "monitoring" / "monitor_state.json"))).resolve()

    backend_health_url = _env("MONITOR_BACKEND_HEALTH_URL", "http://127.0.0.1:8000/health/full")

    return MonitorConfig(
        bot_token=bot_token,
        chat_id=chat_id,
        thread_id=thread_id,
        alert_prefix=_env("ALERT_PREFIX", "[TutorDex Monitor]"),
        raw_heartbeat_path=raw_heartbeat_path,
        queue_heartbeat_path=queue_heartbeat_path,
        log_path=log_path,
        state_path=state_path,
        backend_health_url=backend_health_url,
        check_interval_s=_env_float("MONITOR_CHECK_INTERVAL_SECONDS", 15.0),
        cooldown_s=_env_int("ALERT_COOLDOWN_SECONDS", 600),
        heartbeat_stale_s=_env_int("ALERT_HEARTBEAT_STALE_SECONDS", 900),
        log_stale_s=_env_int("ALERT_LOG_STALE_SECONDS", 900),
        error_burst_limit=_env_int("ALERT_ERROR_BURST_LIMIT", 6),
        daily_summary_enabled=_truthy(_env("DAILY_SUMMARY_ENABLED", "true")),
        daily_summary_hour_local=max(0, min(23, _env_int("DAILY_SUMMARY_HOUR_LOCAL", 9))),
    )


def _load_json(path: Path) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _atomic_write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(str(tmp), str(path))


def _now_local() -> datetime:
    # Local timezone (Windows-friendly).
    return datetime.now().astimezone()


def _parse_ts(ts: str) -> Optional[datetime]:
    s = str(ts or "").strip()
    if not s:
        return None
    # JSON logs: 2025-12-16T19:59:25+0800
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
        try:
            dt = datetime.strptime(s, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=_now_local().tzinfo)
            return dt
        except Exception:
            continue
    return None


def _read_log_tail(path: Path, offset: int) -> Tuple[int, List[str]]:
    if not path.exists():
        return 0, []
    size = path.stat().st_size
    if offset > size:
        offset = 0  # rotated/truncated
    with open(path, "rb") as fh:
        fh.seek(offset, 0)
        data = fh.read()
        new_offset = fh.tell()
    text = data.decode("utf-8", errors="ignore")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    return new_offset, lines


def _classify_log_line(line: str) -> Tuple[Optional[str], Optional[str], Optional[Dict[str, Any]]]:
    """
    Returns (level, event, data) best-effort.
    Supports JSON logs (preferred) and legacy text logs.
    """
    s = line.strip()
    if s.startswith("{") and s.endswith("}"):
        try:
            j = json.loads(s)
            level = (j.get("level") or "").strip().upper() or None
            event = (j.get("event") or j.get("msg") or "").strip() or None
            return level, event, j
        except Exception:
            pass

    # Legacy text logs include patterns like:
    # 2025-12-14 14:04:29 INFO extract_key_info LLM extract start ...
    parts = s.split()
    if len(parts) >= 4:
        level = parts[2].strip().upper()
        return level if level in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"} else None, None, None
    return None, None, None


def _should_alert_event(level: Optional[str], event: Optional[str], raw: str) -> Optional[str]:
    # Explicit structured events
    if event:
        e = event.strip()
        if e in {"llm_extract_failed", "supabase_get_failed", "supabase_insert_failed", "supabase_patch_failed"}:
            return e
        if e in {"broadcast_send_failed", "dm_send_failed"}:
            return e
        if e in {"schema_validation_failed", "validation_failed"}:
            return "validation_failed"
        if e in {"supabase_bump_suppressed"}:
            return "bump_suppressed"
        if e in {"dm_rate_limited"}:
            return "telegram_rate_limited"
        if e in {"pipeline_summary"} and level in {"ERROR", "CRITICAL"}:
            return "pipeline_error"

    # Fallback keyword search (covers legacy text logs)
    hay = raw
    keywords = {
        "FloodWaitError": "telegram_rate_limited",
        "SlowModeWaitError": "telegram_rate_limited",
        "FloodError": "telegram_rate_limited",
        "llm_extract_failed": "llm_extract_failed",
        "match_api_error": "dm_match_failed",
        "Broadcast send error": "broadcast_send_failed",
        "Broadcast failed": "broadcast_send_failed",
        "DM failed": "dm_send_failed",
        "supabase_get_failed": "supabase_get_failed",
        "supabase_insert_failed": "supabase_insert_failed",
        "supabase_patch_failed": "supabase_patch_failed",
        "validation_failed": "validation_failed",
        "schema_validation_failed": "validation_failed",
        "supabase_bump_suppressed": "bump_suppressed",
    }
    for k, key in keywords.items():
        if k in hay:
            return key
    return None


def _read_queue_heartbeat() -> Optional[Dict[str, Any]]:
    hb_rel = _env("MONITOR_QUEUE_HEARTBEAT_FILE", _env("EXTRACTION_QUEUE_HEARTBEAT_FILE", "monitoring/heartbeat_queue_worker.json"))
    agg_dir = Path(__file__).resolve().parent.parent
    hb_path = (agg_dir / hb_rel).resolve()
    return _load_json(hb_path)


def _send_telegram(cfg: MonitorConfig, text: str) -> bool:
    if not (cfg.bot_token and cfg.chat_id):
        return False
    url = f"https://api.telegram.org/bot{cfg.bot_token}/sendMessage"
    body: Dict[str, Any] = {
        "chat_id": cfg.chat_id,
        "text": text,
        "disable_web_page_preview": True,
    }
    if cfg.thread_id is not None:
        body["message_thread_id"] = int(cfg.thread_id)
    try:
        resp = requests.post(url, json=body, timeout=15)
        return resp.status_code < 400
    except Exception:
        return False


def _format_alert(prefix: str, title: str, lines: Iterable[str]) -> str:
    parts = [f"{prefix} {title}".strip()]
    for ln in lines:
        if not ln:
            continue
        parts.append(f"- {ln}")
    return "\n".join(parts).strip()


def _cooldown_ok(state: Dict[str, Any], key: str, cooldown_s: int) -> bool:
    now = int(time.time())
    last = int((state.get("last_alert_ts") or {}).get(key) or 0)
    return (now - last) >= int(cooldown_s)


def _mark_alert(state: Dict[str, Any], key: str) -> None:
    now = int(time.time())
    if "last_alert_ts" not in state or not isinstance(state["last_alert_ts"], dict):
        state["last_alert_ts"] = {}
    state["last_alert_ts"][key] = now


def _backend_health(cfg: MonitorConfig) -> Tuple[bool, str]:
    url = (cfg.backend_health_url or "").strip()
    if not url:
        return True, "backend health check disabled"
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code >= 400:
            return False, f"backend health HTTP {resp.status_code}"
        data = resp.json()
        ok = bool(data.get("ok"))
        if ok:
            return True, "backend ok"
        return False, f"backend unhealthy: {json.dumps(data, ensure_ascii=False)[:300]}"
    except Exception as e:
        return False, f"backend health error: {e}"


def _should_send_daily_summary(cfg: MonitorConfig, state: Dict[str, Any]) -> bool:
    if not cfg.daily_summary_enabled:
        return False
    now = _now_local()
    if now.hour != cfg.daily_summary_hour_local:
        return False
    last_date = str(state.get("last_daily_summary_date") or "")
    today = now.date().isoformat()
    return last_date != today


def _summarize_last_24h(cfg: MonitorConfig) -> List[str]:
    cutoff = _now_local() - timedelta(hours=24)
    counts: Dict[str, int] = {}
    latency: List[float] = []
    qhb = _read_queue_heartbeat()

    if cfg.log_path.exists():
        try:
            for line in cfg.log_path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line:
                    continue
                level, event, j = _classify_log_line(line)
                ts = None
                if j and isinstance(j, dict):
                    ts = _parse_ts(j.get("ts") or "")
                    if ts and ts < cutoff:
                        continue
                    ev = j.get("event") or ""
                    if ev:
                        counts[str(ev)] = counts.get(str(ev), 0) + 1
                    if str(ev) == "pipeline_summary":
                        try:
                            ms = (j.get("data") or {}).get("ms") or {}
                            total_ms = ms.get("total_ms")
                            if isinstance(total_ms, (int, float)):
                                latency.append(float(total_ms))
                        except Exception:
                            pass
                else:
                    # Legacy: best-effort timestamp parsing (local time)
                    if len(line) >= 19 and line[4] == "-" and line[7] == "-":
                        dt = _parse_ts(line[:19])
                        if dt and dt < cutoff:
                            continue
                    if "FloodWaitError" in line or "SlowModeWaitError" in line or "FloodError" in line:
                        counts["telegram_rate_limited"] = counts.get("telegram_rate_limited", 0) + 1
                    if "llm_extract_failed" in line:
                        counts["llm_extract_failed"] = counts.get("llm_extract_failed", 0) + 1
                    if "supabase_" in line and "failed" in line.lower():
                        counts["supabase_failed"] = counts.get("supabase_failed", 0) + 1
        except Exception:
            pass

    raw_hb = _load_json(cfg.raw_heartbeat_path) if cfg.raw_heartbeat_path.exists() else None
    raw_status = raw_hb.get("status") if raw_hb else None
    raw_mode = raw_hb.get("mode") if raw_hb else None
    raw_ts = int(raw_hb.get("ts") or 0) if isinstance(raw_hb, dict) else 0
    raw_age = int(time.time()) - raw_ts if raw_ts else None
    raw_run_id = raw_hb.get("run_id") if raw_hb else None
    raw_scanned = raw_written = raw_errors = None
    if raw_hb and isinstance(raw_hb.get("channels"), dict):
        try:
            ch = raw_hb["channels"]
            raw_scanned = sum(int((v or {}).get("scanned") or 0) for v in ch.values())
            raw_written = sum(int((v or {}).get("written") or 0) for v in ch.values())
            raw_errors = sum(int((v or {}).get("errors") or 0) for v in ch.values())
        except Exception:
            raw_scanned = raw_written = raw_errors = None
    qhb_counts = qhb.get("counts") if isinstance(qhb, dict) else None
    qhb_oldest = qhb.get("oldest_pending_age_s") if isinstance(qhb, dict) else None
    qhb_ts = int(qhb.get("ts") or 0) if isinstance(qhb, dict) else 0
    qhb_age = int(time.time()) - qhb_ts if qhb_ts else None
    qhb_pv = qhb.get("pipeline_version") if isinstance(qhb, dict) else None

    lines = []
    lines.append(
        "Raw collector: "
        f"status={raw_status} mode={raw_mode} run_id={raw_run_id} heartbeat_age_s={raw_age} "
        f"scanned={raw_scanned} written={raw_written} errors={raw_errors}"
    )
    if qhb_counts is not None:
        lines.append(
            "Queue worker: "
            f"heartbeat_age_s={qhb_age} pipeline_version={qhb_pv} counts={qhb_counts} oldest_pending_age_s={qhb_oldest}"
        )
    lines.append(f"Log path: {cfg.log_path.name} exists={cfg.log_path.exists()}")
    lines.append(
        "Events (last 24h): "
        f"pipeline_summary={counts.get('pipeline_summary',0)} "
        f"message_skipped={counts.get('message_skipped',0)}"
    )
    lines.append(
        "Failures (last 24h): "
        f"llm_extract_failed={counts.get('llm_extract_failed',0)} "
        f"supabase_get_failed={counts.get('supabase_get_failed',0)} "
        f"supabase_insert_failed={counts.get('supabase_insert_failed',0)} "
        f"supabase_patch_failed={counts.get('supabase_patch_failed',0)} "
        f"broadcast_send_failed={counts.get('broadcast_send_failed',0)} "
        f"dm_send_failed={counts.get('dm_send_failed',0)} "
        f"validation_failed={counts.get('validation_failed',0)} "
        f"bump_suppressed={counts.get('bump_suppressed',0)} "
        f"telegram_rate_limited={counts.get('telegram_rate_limited',0)}"
    )
    if latency:
        latency.sort()
        p50 = latency[len(latency) // 2]
        lines.append(f"Latency total_ms: p50={round(p50,2)} samples={len(latency)}")
    return lines


def main() -> None:
    cfg = load_config()
    state = _load_json(cfg.state_path) or {}
    if not isinstance(state, dict):
        state = {}

    log_offset = int(state.get("log_offset") or 0)

    while True:
        now = int(time.time())

        # 1) Liveness checks: heartbeat + log staleness + queue heartbeat
        qhb = _read_queue_heartbeat()
        qhb_ts = int(qhb.get("ts") or 0) if isinstance(qhb, dict) else 0
        qhb_age = now - qhb_ts if qhb_ts else None
        queue_healthy = bool(qhb_ts and qhb_age is not None and qhb_age <= max(cfg.heartbeat_stale_s, int(cfg.check_interval_s * 2)))

        raw_hb = _load_json(cfg.raw_heartbeat_path) if cfg.raw_heartbeat_path.exists() else None
        raw_ts = int(raw_hb.get("ts") or 0) if isinstance(raw_hb, dict) else 0
        raw_age = now - raw_ts if raw_ts else None
        raw_healthy = bool(raw_ts and raw_age is not None and raw_age <= max(cfg.heartbeat_stale_s, int(cfg.check_interval_s * 2)))

        if raw_age is None or raw_age > cfg.heartbeat_stale_s:
            key = "raw_collector_heartbeat_stale"
            if _cooldown_ok(state, key, cfg.cooldown_s):
                msg = _format_alert(
                    cfg.alert_prefix,
                    "Raw collector heartbeat stale",
                    [
                        f"heartbeat_age_s={raw_age}",
                        f"file={cfg.raw_heartbeat_path}",
                        f"last_status={(raw_hb or {}).get('status') if isinstance(raw_hb, dict) else None}",
                        f"last_mode={(raw_hb or {}).get('mode') if isinstance(raw_hb, dict) else None}",
                    ],
                )
                _send_telegram(cfg, msg)
                _mark_alert(state, key)

        if cfg.log_path.exists():
            log_age = now - int(cfg.log_path.stat().st_mtime)
            # If both the raw collector + queue heartbeats are healthy, don't page on log staleness.
            # Logs may not update if the file isn't mounted into a container or if the pipeline is quiet.
            if not (raw_healthy and queue_healthy) and log_age > cfg.log_stale_s:
                key = "log_stale"
                if _cooldown_ok(state, key, cfg.cooldown_s):
                    msg = _format_alert(cfg.alert_prefix, "Aggregator log not updating", [f"log_age_s={log_age}", f"log_path={cfg.log_path}"])
                    _send_telegram(cfg, msg)
                    _mark_alert(state, key)

        # Only alert when we have a timestamp and it's stale; skip malformed/missing ts to avoid noise.
        if qhb_ts and qhb_age is not None and qhb_age > max(cfg.heartbeat_stale_s, int(cfg.check_interval_s * 2)):
            key = "queue_heartbeat_stale"
            if _cooldown_ok(state, key, cfg.cooldown_s):
                msg = _format_alert(
                    cfg.alert_prefix,
                    "Queue worker heartbeat stale",
                    [
                        f"heartbeat_age_s={qhb_age}",
                        f"file={cfg.queue_heartbeat_path}",
                        f"last_counts={(qhb or {}).get('counts') if isinstance(qhb, dict) else None}",
                    ],
                )
                _send_telegram(cfg, msg)
                _mark_alert(state, key)
        elif qhb_ts:
            try:
                oldest_age = qhb.get("oldest_pending_age_s") if isinstance(qhb, dict) else None
                if oldest_age and int(oldest_age) > max(cfg.heartbeat_stale_s, 900):
                    key = "queue_lag"
                    if _cooldown_ok(state, key, cfg.cooldown_s):
                        msg = _format_alert(cfg.alert_prefix, "Queue lag high", [f"oldest_pending_age_s={oldest_age}", f"counts={qhb.get('counts') if isinstance(qhb, dict) else None}"])
                        _send_telegram(cfg, msg)
                        _mark_alert(state, key)
            except Exception:
                pass

        # 2) Backend/Redis/Supabase health (via backend endpoint)
        ok, detail = _backend_health(cfg)
        if not ok:
            key = "backend_unhealthy"
            if _cooldown_ok(state, key, cfg.cooldown_s):
                msg = _format_alert(cfg.alert_prefix, "Backend/Redis/Supabase health check failed", [detail, f"url={cfg.backend_health_url}"])
                _send_telegram(cfg, msg)
                _mark_alert(state, key)

        # 3) Tail new logs for bursty errors
        new_offset, lines = _read_log_tail(cfg.log_path, log_offset)
        log_offset = new_offset
        state["log_offset"] = log_offset

        burst: Dict[str, List[str]] = {}
        for ln in lines:
            level, event, _j = _classify_log_line(ln)
            alert_key = _should_alert_event(level, event, ln)
            if not alert_key:
                continue
            bucket = burst.setdefault(alert_key, [])
            if len(bucket) < cfg.error_burst_limit:
                bucket.append(ln[:220])
            else:
                # keep counting implicitly without expanding message
                pass

        for alert_key, samples in burst.items():
            if not _cooldown_ok(state, f"err:{alert_key}", cfg.cooldown_s):
                continue
            msg = _format_alert(cfg.alert_prefix, f"Error spike: {alert_key}", samples[: cfg.error_burst_limit])
            _send_telegram(cfg, msg)
            _mark_alert(state, f"err:{alert_key}")

        # 4) Daily summary
        if _should_send_daily_summary(cfg, state):
            lines = _summarize_last_24h(cfg)
            msg = _format_alert(cfg.alert_prefix, "Daily pipeline health summary (last 24h)", lines)
            _send_telegram(cfg, msg)
            state["last_daily_summary_date"] = _now_local().date().isoformat()

        _atomic_write_json(cfg.state_path, state)
        time.sleep(max(2.0, float(cfg.check_interval_s)))


if __name__ == "__main__":
    main()
