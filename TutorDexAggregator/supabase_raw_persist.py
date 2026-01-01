import os
import json
import time
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests
from urllib.parse import urlparse

from logging_setup import bind_log_context, log_event, setup_logging, timed
from supabase_env import resolve_supabase_url, running_in_docker


setup_logging()
logger = logging.getLogger("supabase_raw_persist")


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _safe_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        n = int(value)
        return n
    except Exception:
        return None


def _jsonable(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    # Telethon TLObjects often implement .to_dict()
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        try:
            return _jsonable(to_dict())
        except Exception:
            return str(value)
    return str(value)


@dataclass(frozen=True)
class SupabaseRawConfig:
    url: str
    key: str
    enabled: bool = False
    channels_table: str = "telegram_channels"
    messages_table: str = "telegram_messages_raw"
    runs_table: str = "ingestion_runs"
    progress_table: str = "ingestion_run_progress"


def load_raw_config_from_env() -> SupabaseRawConfig:
    url_env = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    url_docker_env = (os.environ.get("SUPABASE_URL_DOCKER") or "").strip().rstrip("/")
    url_host_env = (os.environ.get("SUPABASE_URL_HOST") or "").strip().rstrip("/")

    in_docker = running_in_docker()
    if in_docker:
        chosen = url_docker_env or url_env or url_host_env
        source = "SUPABASE_URL_DOCKER" if url_docker_env else ("SUPABASE_URL" if url_env else ("SUPABASE_URL_HOST" if url_host_env else "missing"))
    else:
        chosen = url_host_env or url_env or url_docker_env
        source = "SUPABASE_URL_HOST" if url_host_env else ("SUPABASE_URL" if url_env else ("SUPABASE_URL_DOCKER" if url_docker_env else "missing"))

    url = resolve_supabase_url()
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()

    # Default to SUPABASE_ENABLED, but allow overriding independently.
    raw_enabled_env = os.environ.get("SUPABASE_RAW_ENABLED")
    enabled = _truthy(raw_enabled_env) if raw_enabled_env is not None else _truthy(os.environ.get("SUPABASE_ENABLED"))
    enabled = bool(enabled and url and key)

    # This is intentionally INFO-level to make host-vs-docker connectivity issues obvious.
    log_event(
        logger,
        logging.INFO,
        "supabase_raw_url_selected",
        in_docker=in_docker,
        source=source,
        url=chosen or None,
        url_host_set=bool(url_host_env),
        url_docker_set=bool(url_docker_env),
        url_set=bool(url_env),
        enabled=enabled,
    )

    return SupabaseRawConfig(
        url=url,
        key=key,
        enabled=enabled,
        channels_table=(os.environ.get("SUPABASE_RAW_CHANNELS_TABLE") or "telegram_channels").strip(),
        messages_table=(os.environ.get("SUPABASE_RAW_MESSAGES_TABLE") or "telegram_messages_raw").strip(),
        runs_table=(os.environ.get("SUPABASE_RAW_RUNS_TABLE") or "ingestion_runs").strip(),
        progress_table=(os.environ.get("SUPABASE_RAW_PROGRESS_TABLE") or "ingestion_run_progress").strip(),
    )


class SupabaseRestClient:
    def __init__(self, cfg: SupabaseRawConfig):
        self.cfg = cfg
        self.base = f"{cfg.url}/rest/v1"
        self.session = requests.Session()
        # On some Windows setups, global proxy env vars can cause requests to proxy even localhost
        # traffic, leading to confusing "RemoteDisconnected" errors. For local Supabase (Kong on
        # 127.0.0.1/localhost), disable trusting env proxy vars.
        try:
            host = (urlparse(cfg.url).hostname or "").lower()
            if host in {"127.0.0.1", "localhost", "::1"}:
                self.session.trust_env = False
        except Exception:
            pass
        self.session.headers.update(
            {
                "apikey": cfg.key,
                "authorization": f"Bearer {cfg.key}",
                "content-type": "application/json",
            }
        )

    def _url(self, path: str) -> str:
        return f"{self.base}/{path.lstrip('/')}"

    def get(self, path: str, *, timeout: int = 15) -> requests.Response:
        return self.session.get(self._url(path), timeout=timeout)

    def post(
        self,
        path: str,
        json_body: Any,
        *,
        timeout: int = 15,
        prefer: Optional[str] = None,
        extra_headers: Optional[Dict[str, str]] = None,
    ) -> requests.Response:
        headers: Dict[str, str] = {}
        if prefer:
            headers["prefer"] = prefer
        if extra_headers:
            headers.update(extra_headers)
        return self.session.post(self._url(path), json=json_body, headers=headers, timeout=timeout)

    def patch(self, path: str, json_body: Any, *, timeout: int = 15, prefer: Optional[str] = None) -> requests.Response:
        headers: Dict[str, str] = {}
        if prefer:
            headers["prefer"] = prefer
        return self.session.patch(self._url(path), json=json_body, headers=headers, timeout=timeout)


class RawFallbackWriter:
    def __init__(self, *, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append_jsonl(self, row: Dict[str, Any]) -> None:
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


class SupabaseRawStore:
    def __init__(self, cfg: Optional[SupabaseRawConfig] = None):
        self.cfg = cfg or load_raw_config_from_env()
        self.client = SupabaseRestClient(self.cfg) if self.cfg.enabled else None
        fb = (os.environ.get("RAW_FALLBACK_FILE") or "").strip()
        self.fallback = RawFallbackWriter(path=Path(fb)) if fb else None

    def enabled(self) -> bool:
        return bool(self.client)

    def _best_effort_fallback(self, *, kind: str, row: Dict[str, Any]) -> None:
        if not self.fallback:
            return
        try:
            self.fallback.append_jsonl({"ts": int(time.time()), "kind": kind, "row": row})
        except Exception:
            logger.debug("raw_fallback_write_failed", exc_info=True)

    def upsert_channel(self, *, channel_link: str, channel_id: Optional[str], title: Optional[str]) -> bool:
        if not self.client:
            self._best_effort_fallback(kind="channel", row={"channel_link": channel_link, "channel_id": channel_id, "title": title})
            return False
        row: Dict[str, Any] = {"channel_link": channel_link}
        if channel_id:
            row["channel_id"] = channel_id
        if title:
            row["title"] = title
        try:
            resp = self.client.post(
                f"{self.cfg.channels_table}?on_conflict=channel_link",
                [row],
                timeout=20,
                prefer="resolution=merge-duplicates,return=representation",
            )
            ok = resp.status_code < 400
            if not ok:
                log_event(logger, logging.WARNING, "raw_channels_upsert_status", status_code=resp.status_code, body=resp.text[:400])
            return ok
        except Exception as e:
            log_event(logger, logging.WARNING, "raw_channels_upsert_failed", error=str(e))
            self._best_effort_fallback(kind="channel", row=row)
            return False

    def get_latest_run_id(self, *, run_type: Optional[str] = None) -> Optional[int]:
        if not self.client:
            return None
        q = f"{self.cfg.runs_table}?select=id,run_type,started_at&order=started_at.desc&limit=1"
        if run_type:
            q = f"{self.cfg.runs_table}?select=id,run_type,started_at&run_type=eq.{requests.utils.quote(str(run_type), safe='')}&order=started_at.desc&limit=1"
        try:
            resp = self.client.get(q, timeout=15)
        except Exception:
            return None
        if resp.status_code >= 400:
            return None
        try:
            data = resp.json()
        except Exception:
            return None
        if isinstance(data, list) and data:
            rid = data[0].get("id")
            try:
                return int(rid)
            except Exception:
                return None
        return None

    def get_run(self, *, run_id: int) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        try:
            resp = self.client.get(f"{self.cfg.runs_table}?select=*&id=eq.{int(run_id)}&limit=1", timeout=15)
        except Exception:
            return None
        if resp.status_code >= 400:
            return None
        try:
            data = resp.json()
        except Exception:
            return None
        if isinstance(data, list) and data:
            return data[0]
        return None

    def list_progress(self, *, run_id: int) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        try:
            resp = self.client.get(
                f"{self.cfg.progress_table}?select=channel_link,last_message_id,last_message_date,scanned_count,inserted_count,updated_count,error_count,updated_at&run_id=eq.{int(run_id)}&order=channel_link.asc",
                timeout=20,
            )
        except Exception:
            return []
        if resp.status_code >= 400:
            return []
        try:
            data = resp.json()
        except Exception:
            return []
        return data if isinstance(data, list) else []

    def create_run(self, *, run_type: str, channels: List[str], meta: Optional[Dict[str, Any]] = None) -> Optional[int]:
        if not self.client:
            self._best_effort_fallback(kind="run_start", row={"run_type": run_type, "channels": channels, "meta": meta or {}})
            return None
        row: Dict[str, Any] = {"run_type": str(run_type), "status": "running", "channels": channels, "meta": meta or {}}
        try:
            resp = self.client.post(self.cfg.runs_table, [row], timeout=20, prefer="return=representation")
            if resp.status_code >= 400:
                log_event(logger, logging.WARNING, "raw_run_create_status", status_code=resp.status_code, body=resp.text[:400])
                return None
            data = resp.json()
            if isinstance(data, list) and data:
                return data[0].get("id")
            return None
        except Exception as e:
            log_event(logger, logging.WARNING, "raw_run_create_failed", error=str(e))
            return None

    def finish_run(self, *, run_id: Optional[int], status: str, meta_patch: Optional[Dict[str, Any]] = None) -> bool:
        if not self.client or not run_id:
            self._best_effort_fallback(kind="run_finish", row={"run_id": run_id, "status": status, "meta_patch": meta_patch or {}})
            return False
        body: Dict[str, Any] = {"status": str(status), "finished_at": _utc_now_iso()}
        if meta_patch:
            body["meta"] = meta_patch
        try:
            resp = self.client.patch(f"{self.cfg.runs_table}?id=eq.{int(run_id)}", body, timeout=20, prefer="return=representation")
            ok = resp.status_code < 400
            if not ok:
                log_event(logger, logging.WARNING, "raw_run_finish_status", run_id=run_id, status_code=resp.status_code, body=resp.text[:400])
            return ok
        except Exception as e:
            log_event(logger, logging.WARNING, "raw_run_finish_failed", run_id=run_id, error=str(e))
            return False

    def upsert_progress(
        self,
        *,
        run_id: Optional[int],
        channel_link: str,
        last_message_id: Optional[str],
        last_message_date_iso: Optional[str],
        scanned: int,
        inserted: int,
        updated: int,
        errors: int,
    ) -> bool:
        if not self.client or not run_id:
            self._best_effort_fallback(
                kind="progress",
                row={
                    "run_id": run_id,
                    "channel_link": channel_link,
                    "last_message_id": last_message_id,
                    "last_message_date": last_message_date_iso,
                    "scanned": scanned,
                    "inserted": inserted,
                    "updated": updated,
                    "errors": errors,
                },
            )
            return False
        row: Dict[str, Any] = {
            "run_id": int(run_id),
            "channel_link": channel_link,
            "updated_at": _utc_now_iso(),
            "scanned_count": int(scanned),
            "inserted_count": int(inserted),
            "updated_count": int(updated),
            "error_count": int(errors),
        }
        if last_message_id:
            row["last_message_id"] = last_message_id
        if last_message_date_iso:
            row["last_message_date"] = last_message_date_iso
        try:
            resp = self.client.post(
                f"{self.cfg.progress_table}?on_conflict=run_id,channel_link",
                [row],
                timeout=20,
                prefer="resolution=merge-duplicates,return=representation",
            )
            ok = resp.status_code < 400
            if not ok:
                log_event(logger, logging.WARNING, "raw_progress_upsert_status", status_code=resp.status_code, body=resp.text[:400])
            return ok
        except Exception as e:
            log_event(logger, logging.WARNING, "raw_progress_upsert_failed", error=str(e))
            return False

    def upsert_messages_batch(
        self,
        *,
        rows: List[Dict[str, Any]],
        on_conflict: str = "channel_link,message_id",
        timeout: int = 30,
    ) -> Tuple[int, int]:
        """
        Returns (attempted, ok_rows). PostgREST doesn't reliably tell insert vs update counts; treat ok_rows as written.
        """
        if not rows:
            return 0, 0

        # PostgREST requires all objects in a bulk insert to have identical keys.
        # Normalize by filling missing keys with explicit nulls.
        all_keys: set[str] = set()
        for r in rows:
            all_keys.update(r.keys())

        normalized: List[Dict[str, Any]] = []
        dropped = 0
        for r in rows:
            if r.get("channel_link") is None or r.get("message_id") is None or r.get("message_date") is None or r.get("message_json") is None:
                dropped += 1
                continue
            nr = {k: r.get(k, None) for k in all_keys}
            normalized.append(nr)

        if dropped:
            log_event(logger, logging.WARNING, "raw_messages_batch_dropped", dropped=dropped, attempted=len(rows))

        if not normalized:
            return len(rows), 0
        if not self.client:
            for r in normalized:
                self._best_effort_fallback(kind="message", row=r)
            return len(rows), 0

        t0 = timed()
        prefer = "resolution=merge-duplicates,return=minimal"
        try:
            resp = self.client.post(
                f"{self.cfg.messages_table}?on_conflict={on_conflict}",
                normalized,
                timeout=timeout,
                prefer=prefer,
            )
        except Exception as e:
            log_event(logger, logging.WARNING, "raw_messages_upsert_failed", error=str(e), attempted=len(rows))
            return len(rows), 0

        ok = resp.status_code < 400
        if not ok:
            log_event(logger, logging.WARNING, "raw_messages_upsert_status", status_code=resp.status_code, body=resp.text[:400], attempted=len(rows))
            return len(rows), 0

        log_event(logger, logging.DEBUG, "raw_messages_upsert_ok", attempted=len(rows), ms=round((timed() - t0) * 1000.0, 2))
        return len(rows), len(rows)

    def mark_deleted(self, *, channel_link: str, message_ids: Iterable[str], deleted_at_iso: Optional[str] = None) -> int:
        ids = [str(x).strip() for x in message_ids if str(x).strip()]
        if not ids:
            return 0
        deleted_at_iso = deleted_at_iso or _utc_now_iso()

        if not self.client:
            for mid in ids:
                self._best_effort_fallback(kind="delete", row={"channel_link": channel_link, "message_id": mid, "deleted_at": deleted_at_iso})
            return 0

        # Patch per-message to keep it simple and safe. If this becomes a bottleneck, switch to RPC.
        patched = 0
        for mid in ids:
            try:
                resp = self.client.patch(
                    f"{self.cfg.messages_table}?channel_link=eq.{requests.utils.quote(channel_link, safe='')}&message_id=eq.{requests.utils.quote(mid, safe='')}",
                    {"deleted_at": deleted_at_iso, "last_seen_at": _utc_now_iso()},
                    timeout=20,
                    prefer="return=minimal",
                )
                if resp.status_code < 400:
                    patched += 1
                else:
                    log_event(logger, logging.DEBUG, "raw_delete_patch_status", status_code=resp.status_code, body=resp.text[:200])
            except Exception as e:
                log_event(logger, logging.DEBUG, "raw_delete_patch_failed", error=str(e))
        return patched


def build_raw_row(
    *,
    channel_link: str,
    channel_id: Optional[str],
    msg: Any,
) -> Optional[Dict[str, Any]]:
    """
    Convert a Telethon message into a JSON-serializable row for telegram_messages_raw.
    """
    if msg is None:
        return None

    message_id = getattr(msg, "id", None)
    dt = getattr(msg, "date", None)
    if message_id is None or dt is None:
        return None

    raw_text = getattr(msg, "raw_text", None) or getattr(msg, "message", None) or ""
    edit_dt = getattr(msg, "edit_date", None)

    replies = getattr(msg, "replies", None)
    reply_count = None
    if replies is not None:
        reply_count = _safe_int(getattr(replies, "replies", None))

    media = getattr(msg, "media", None)
    entities = getattr(msg, "entities", None)

    row: Dict[str, Any] = {
        "channel_link": channel_link,
        "channel_id": _safe_str(channel_id),
        "message_id": str(message_id),
        "message_date": _jsonable(dt),
        "sender_id": _safe_str(getattr(msg, "sender_id", None)),
        "is_forward": bool(getattr(msg, "fwd_from", None) is not None),
        "is_reply": bool(getattr(msg, "reply_to_msg_id", None) is not None),
        "raw_text": _safe_str(raw_text),
        "entities_json": _jsonable(entities) if entities is not None else None,
        "media_json": _jsonable(media) if media is not None else None,
        "views": _safe_int(getattr(msg, "views", None)),
        "forwards": _safe_int(getattr(msg, "forwards", None)),
        "reply_count": reply_count,
        "edit_date": _jsonable(edit_dt) if edit_dt else None,
        "message_json": _jsonable(
            {
                "id": message_id,
                "date": dt,
                "edit_date": edit_dt,
                "sender_id": getattr(msg, "sender_id", None),
                "text": raw_text,
                "raw": getattr(msg, "message", None),
                "views": getattr(msg, "views", None),
                "forwards": getattr(msg, "forwards", None),
                "reply_to_msg_id": getattr(msg, "reply_to_msg_id", None),
                "fwd_from": getattr(msg, "fwd_from", None),
                "entities": entities,
                "media": media,
            }
        ),
        "last_seen_at": _utc_now_iso(),
    }
    return row
