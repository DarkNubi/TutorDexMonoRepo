"""
Monitor configured Telegram channels for:
- new messages (baseline)
- message edits
- message deletions

Stores detailed events + per-message stats in a local SQLite DB for later analysis.

Reads Telegram config from `TutorDexAggregator/.env` (same as `collector.py`):
- TELEGRAM_API_ID / TELEGRAM_API_HASH
- SESSION_STRING or TG_SESSION (session file)
- CHANNEL_LIST (JSON array or comma-separated)

Optional env vars:
- EDIT_MONITOR_DB_PATH (default: monitoring/telegram_message_edits.sqlite)
- EDIT_MONITOR_EVENTS_JSONL (optional jsonl append path for event logs)
- EDIT_MONITOR_INCLUDE_TEXT=true/false (default true)
- EDIT_MONITOR_MAX_TEXT_CHARS (default 20000)
- EDIT_MONITOR_HISTORIC_FETCH (default 50)
- EDIT_MONITOR_SUMMARY_INTERVAL_SECONDS (default 600)
"""

import asyncio
import hashlib
import json
import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from telethon import TelegramClient, events

from logging_setup import log_event, setup_logging, timed
from shared.config import load_aggregator_config


HERE = Path(__file__).resolve().parent


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def _utc_now_ts() -> int:
    return int(time.time())


def _dt_to_iso(dt: Optional[datetime]) -> Optional[str]:
    if not dt:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat()


def _truncate_text(s: str, *, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(s) <= max_chars:
        return s
    return s[: max(0, max_chars - 12)] + "...(truncated)"


def _text_hash(s: str) -> str:
    b = s.encode("utf-8", errors="replace")
    return hashlib.sha256(b).hexdigest()


def _change_stats(old: str, new: str) -> Dict[str, Any]:
    old_len = len(old)
    new_len = len(new)
    old_hash = _text_hash(old)
    new_hash = _text_hash(new)
    same = old_hash == new_hash
    return {
        "old_len": old_len,
        "new_len": new_len,
        "old_hash": old_hash,
        "new_hash": new_hash,
        "changed": not same,
        "delta_len": new_len - old_len,
    }


def _parse_channels() -> List[str]:
    cfg = load_aggregator_config()
    raw = str(cfg.channel_list or "").strip()
    if not raw:
        return []
    if raw.startswith("[") and raw.endswith("]"):
        try:
            items = json.loads(raw)
            if isinstance(items, list):
                return [str(x).strip().strip('"').strip("'") for x in items if str(x).strip()]
        except Exception:
            inner = raw[1:-1]
            return [x.strip().strip('"').strip("'") for x in inner.split(",") if x.strip()]
    return [x.strip() for x in raw.split(",") if x.strip()]


def _normalize_channel_ref(ch: str) -> str:
    s = ch.strip()
    if not s:
        return s
    if s.startswith("http://") or s.startswith("https://"):
        return s
    if s.startswith("t.me/"):
        return "https://" + s
    if s.startswith("@"):
        return "https://t.me/" + s[1:]
    return "https://t.me/" + s


@dataclass(frozen=True)
class MonitorConfig:
    api_id: int
    api_hash: str
    session_string: str
    session_name: str
    channels: List[str]
    db_path: Path
    events_jsonl_path: Optional[Path]
    include_text: bool
    max_text_chars: int
    historic_fetch: int
    summary_interval_s: int


def load_config() -> MonitorConfig:
    cfg = load_aggregator_config()
    api_id_raw = str(cfg.telegram_api_id or "").strip()
    try:
        api_id = int(api_id_raw) if api_id_raw else 0
    except Exception:
        api_id = 0
    api_hash = str(cfg.telegram_api_hash or "").strip()
    session_string = str(cfg.session_string or "").strip()
    session_name = str(cfg.telegram_session_name or "tutordex.session").strip() or "tutordex.session"
    channels = [_normalize_channel_ref(x) for x in _parse_channels()]

    db_path_raw = str(cfg.edit_monitor_db_path or "").strip()
    db_path = Path(db_path_raw) if db_path_raw else (HERE / "monitoring" / "telegram_message_edits.sqlite")
    events_jsonl_raw = str(cfg.edit_monitor_events_jsonl or "").strip()
    events_jsonl_path = Path(events_jsonl_raw) if events_jsonl_raw else None

    include_text = bool(cfg.edit_monitor_include_text)
    max_text_chars = int(cfg.edit_monitor_max_text_chars)
    historic_fetch = int(cfg.edit_monitor_historic_fetch)
    summary_interval_s = int(cfg.edit_monitor_summary_interval_seconds)

    if not api_id or not api_hash or not channels:
        raise SystemExit("Set TELEGRAM_API_ID, TELEGRAM_API_HASH and CHANNEL_LIST in .env or environment")
    return MonitorConfig(
        api_id=api_id,
        api_hash=api_hash,
        session_string=session_string,
        session_name=session_name,
        channels=channels,
        db_path=db_path,
        events_jsonl_path=events_jsonl_path,
        include_text=include_text,
        max_text_chars=max_text_chars,
        historic_fetch=historic_fetch,
        summary_interval_s=summary_interval_s,
    )


class EditsDb:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute("pragma journal_mode=WAL;")
        self.conn.execute("pragma synchronous=NORMAL;")
        self._migrate()

    def close(self) -> None:
        try:
            self.conn.close()
        except Exception:
            pass

    def _migrate(self) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            create table if not exists messages (
              channel_id text not null,
              message_id integer not null,
              channel_link text,
              channel_title text,
              message_date text,
              first_observed_ts integer not null,
              last_observed_ts integer not null,
              last_edit_date text,
              edit_count integer not null default 0,
              deleted integer not null default 0,
              deleted_ts integer,
              last_hash text,
              last_len integer,
              last_text text,
              primary key (channel_id, message_id)
            );
            """
        )
        cur.execute(
            """
            create table if not exists events (
              id integer primary key autoincrement,
              ts integer not null,
              event_type text not null,
              channel_id text,
              message_id integer,
              channel_link text,
              channel_title text,
              message_date text,
              edit_date text,
              old_hash text,
              new_hash text,
              old_len integer,
              new_len integer,
              delta_len integer,
              old_text text,
              new_text text
            );
            """
        )
        cur.execute("create index if not exists events_ts_idx on events(ts);")
        cur.execute("create index if not exists events_chan_msg_idx on events(channel_id, message_id, ts);")
        self.conn.commit()

    def upsert_message_baseline(
        self,
        *,
        channel_id: str,
        message_id: int,
        channel_link: str,
        channel_title: str,
        message_date_iso: Optional[str],
        observed_ts: int,
        text: str,
        include_text: bool,
    ) -> None:
        s = text or ""
        h = _text_hash(s)
        cur = self.conn.cursor()
        cur.execute(
            """
            insert into messages (
              channel_id, message_id, channel_link, channel_title, message_date,
              first_observed_ts, last_observed_ts, last_edit_date,
              edit_count, deleted, deleted_ts, last_hash, last_len, last_text
            )
            values (?, ?, ?, ?, ?, ?, ?, null, 0, 0, null, ?, ?, ?)
            on conflict(channel_id, message_id) do update set
              last_observed_ts=excluded.last_observed_ts,
              channel_link=coalesce(excluded.channel_link, messages.channel_link),
              channel_title=coalesce(excluded.channel_title, messages.channel_title),
              message_date=coalesce(messages.message_date, excluded.message_date),
              last_hash=excluded.last_hash,
              last_len=excluded.last_len,
              last_text=case when ? then excluded.last_text else messages.last_text end
            """,
            (
                channel_id,
                int(message_id),
                channel_link or None,
                channel_title or None,
                message_date_iso,
                int(observed_ts),
                int(observed_ts),
                h,
                len(s),
                s if include_text else None,
                1 if include_text else 0,
            ),
        )
        self.conn.commit()

    def record_edit(
        self,
        *,
        channel_id: str,
        message_id: int,
        channel_link: str,
        channel_title: str,
        message_date_iso: Optional[str],
        edit_date_iso: Optional[str],
        observed_ts: int,
        old_text: str,
        new_text: str,
        include_text: bool,
    ) -> Dict[str, Any]:
        stats = _change_stats(old_text, new_text)

        cur = self.conn.cursor()
        cur.execute(
            """
            insert into events (
              ts, event_type, channel_id, message_id, channel_link, channel_title, message_date, edit_date,
              old_hash, new_hash, old_len, new_len, delta_len, old_text, new_text
            )
            values (?, 'edit', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(observed_ts),
                channel_id,
                int(message_id),
                channel_link or None,
                channel_title or None,
                message_date_iso,
                edit_date_iso,
                stats["old_hash"],
                stats["new_hash"],
                stats["old_len"],
                stats["new_len"],
                stats["delta_len"],
                old_text if include_text else None,
                new_text if include_text else None,
            ),
        )

        cur.execute(
            """
            insert into messages (
              channel_id, message_id, channel_link, channel_title, message_date,
              first_observed_ts, last_observed_ts, last_edit_date,
              edit_count, deleted, deleted_ts, last_hash, last_len, last_text
            )
            values (?, ?, ?, ?, ?, ?, ?, ?, 1, 0, null, ?, ?, ?)
            on conflict(channel_id, message_id) do update set
              last_observed_ts=excluded.last_observed_ts,
              last_edit_date=excluded.last_edit_date,
              edit_count=messages.edit_count + 1,
              deleted=0,
              deleted_ts=null,
              channel_link=coalesce(excluded.channel_link, messages.channel_link),
              channel_title=coalesce(excluded.channel_title, messages.channel_title),
              message_date=coalesce(messages.message_date, excluded.message_date),
              last_hash=excluded.last_hash,
              last_len=excluded.last_len,
              last_text=case when ? then excluded.last_text else messages.last_text end
            """,
            (
                channel_id,
                int(message_id),
                channel_link or None,
                channel_title or None,
                message_date_iso,
                int(observed_ts),
                int(observed_ts),
                edit_date_iso,
                stats["new_hash"],
                stats["new_len"],
                new_text if include_text else None,
                1 if include_text else 0,
            ),
        )
        self.conn.commit()
        return stats

    def record_delete(
        self,
        *,
        channel_id: str,
        message_id: int,
        channel_link: str,
        channel_title: str,
        observed_ts: int,
    ) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            insert into events (ts, event_type, channel_id, message_id, channel_link, channel_title)
            values (?, 'delete', ?, ?, ?, ?)
            """,
            (int(observed_ts), channel_id, int(message_id), channel_link or None, channel_title or None),
        )
        cur.execute(
            """
            insert into messages (
              channel_id, message_id, channel_link, channel_title, message_date,
              first_observed_ts, last_observed_ts, last_edit_date,
              edit_count, deleted, deleted_ts, last_hash, last_len, last_text
            )
            values (?, ?, ?, ?, null, ?, ?, null, 0, 1, ?, null, null, null)
            on conflict(channel_id, message_id) do update set
              last_observed_ts=excluded.last_observed_ts,
              deleted=1,
              deleted_ts=?,
              channel_link=coalesce(excluded.channel_link, messages.channel_link),
              channel_title=coalesce(excluded.channel_title, messages.channel_title)
            """,
            (
                channel_id,
                int(message_id),
                channel_link or None,
                channel_title or None,
                int(observed_ts),
                int(observed_ts),
                int(observed_ts),
                int(observed_ts),
            ),
        )
        self.conn.commit()

    def record_new_event(
        self,
        *,
        channel_id: str,
        message_id: int,
        channel_link: str,
        channel_title: str,
        message_date_iso: Optional[str],
        observed_ts: int,
        text: str,
        include_text: bool,
    ) -> None:
        s = text or ""
        h = _text_hash(s)
        cur = self.conn.cursor()
        cur.execute(
            """
            insert into events (
              ts, event_type, channel_id, message_id, channel_link, channel_title, message_date,
              new_hash, new_len, new_text
            )
            values (?, 'new', ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(observed_ts),
                channel_id,
                int(message_id),
                channel_link or None,
                channel_title or None,
                message_date_iso,
                h,
                len(s),
                s if include_text else None,
            ),
        )
        self.conn.commit()

    def stats_snapshot(self) -> Dict[str, Any]:
        cur = self.conn.cursor()
        total = cur.execute("select count(1) from messages").fetchone()[0]
        edited = cur.execute("select count(1) from messages where edit_count > 0").fetchone()[0]
        deleted = cur.execute("select count(1) from messages where deleted = 1").fetchone()[0]
        ev_total = cur.execute("select count(1) from events").fetchone()[0]
        return {
            "messages_total": int(total or 0),
            "messages_edited": int(edited or 0),
            "messages_deleted": int(deleted or 0),
            "events_total": int(ev_total or 0),
        }


def _append_jsonl(path: Path, obj: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(obj, ensure_ascii=False)
    with path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


async def _seed_recent_messages(client: TelegramClient, db: EditsDb, cfg: MonitorConfig) -> None:
    for ch in cfg.channels:
        try:
            entity = await client.get_entity(ch)
        except Exception as e:
            log_event(logger, logging.WARNING, "seed_get_entity_failed", channel=ch, error=str(e))
            continue

        channel_id = _safe_str(getattr(entity, "id", "")) or _safe_str(ch)
        channel_link = ch
        channel_title = _safe_str(getattr(entity, "title", "")) or _safe_str(getattr(entity, "username", "")) or ""

        try:
            messages = await client.get_messages(entity, limit=max(0, int(cfg.historic_fetch)))
        except Exception as e:
            log_event(logger, logging.WARNING, "seed_get_messages_failed", channel=ch, error=str(e))
            continue

        now_ts = _utc_now_ts()
        for m in messages or []:
            try:
                mid = int(getattr(m, "id"))
            except Exception:
                continue
            text = _safe_str(getattr(m, "message", "")) or ""
            text = _truncate_text(text, max_chars=cfg.max_text_chars)
            msg_date_iso = _dt_to_iso(getattr(m, "date", None))
            db.upsert_message_baseline(
                channel_id=channel_id,
                message_id=mid,
                channel_link=channel_link,
                channel_title=channel_title,
                message_date_iso=msg_date_iso,
                observed_ts=now_ts,
                text=text,
                include_text=cfg.include_text,
            )
        log_event(logger, logging.INFO, "seed_channel_done", channel=ch, channel_id=channel_id, seeded=len(messages or []))


async def _summary_loop(db: EditsDb, cfg: MonitorConfig) -> None:
    while True:
        try:
            snap = db.stats_snapshot()
            log_event(logger, logging.INFO, "edit_monitor_summary", **snap)
        except Exception:
            logger.debug("summary_failed", exc_info=True)
        await asyncio.sleep(max(30, int(cfg.summary_interval_s)))


async def run() -> None:
    cfg = load_config()

    db = EditsDb(cfg.db_path)

    # Prefer StringSession if configured; else fall back to a session file.
    try:
        from telethon.sessions import StringSession  # type: ignore
    except Exception:
        StringSession = None

    session = None
    if cfg.session_string and StringSession is not None:
        session = StringSession(cfg.session_string)
    else:
        session = cfg.session_name

    client = TelegramClient(session, cfg.api_id, cfg.api_hash)

    log_event(
        logger,
        logging.INFO,
        "edit_monitor_start",
        channels=len(cfg.channels),
        db_path=str(cfg.db_path),
        include_text=cfg.include_text,
        historic_fetch=cfg.historic_fetch,
    )

    await client.start()
    await _seed_recent_messages(client, db, cfg)

    if cfg.events_jsonl_path:
        log_event(logger, logging.INFO, "events_jsonl_enabled", path=str(cfg.events_jsonl_path))

    async def resolve_channel_meta(event_chat) -> Tuple[str, str, str]:
        channel_id = _safe_str(getattr(event_chat, "id", "")) or ""
        username = _safe_str(getattr(event_chat, "username", "")) or ""
        title = _safe_str(getattr(event_chat, "title", "")) or username or ""
        link = f"https://t.me/{username}" if username else ""
        return channel_id, link, title

    @client.on(events.NewMessage)
    async def on_new_message(event) -> None:
        try:
            chat = await event.get_chat()
            channel_id, channel_link, channel_title = await resolve_channel_meta(chat)
            mid = int(event.message.id)
            msg_date_iso = _dt_to_iso(getattr(event.message, "date", None))
            text = _safe_str(getattr(event.message, "message", "")) or ""
            text = _truncate_text(text, max_chars=cfg.max_text_chars)
            now_ts = _utc_now_ts()

            db.upsert_message_baseline(
                channel_id=channel_id,
                message_id=mid,
                channel_link=channel_link,
                channel_title=channel_title,
                message_date_iso=msg_date_iso,
                observed_ts=now_ts,
                text=text,
                include_text=cfg.include_text,
            )
            db.record_new_event(
                channel_id=channel_id,
                message_id=mid,
                channel_link=channel_link,
                channel_title=channel_title,
                message_date_iso=msg_date_iso,
                observed_ts=now_ts,
                text=text if cfg.include_text else "",
                include_text=cfg.include_text,
            )
            if cfg.events_jsonl_path:
                _append_jsonl(
                    cfg.events_jsonl_path,
                    {
                        "ts": now_ts,
                        "event_type": "new",
                        "channel_id": channel_id,
                        "channel_link": channel_link,
                        "channel_title": channel_title,
                        "message_id": mid,
                        "message_date": msg_date_iso,
                        "text": text if cfg.include_text else None,
                    },
                )
        except Exception:
            logger.debug("on_new_message_failed", exc_info=True)

    @client.on(events.MessageEdited)
    async def on_message_edited(event) -> None:
        try:
            chat = await event.get_chat()
            channel_id, channel_link, channel_title = await resolve_channel_meta(chat)
            mid = int(event.message.id)
            msg_date_iso = _dt_to_iso(getattr(event.message, "date", None))
            edit_date_iso = _dt_to_iso(getattr(event.message, "edit_date", None))
            new_text = _safe_str(getattr(event.message, "message", "")) or ""
            new_text = _truncate_text(new_text, max_chars=cfg.max_text_chars)
            now_ts = _utc_now_ts()

            # Fetch current stored text (if any) to compute deltas. If missing, treat as baseline.
            cur = db.conn.cursor()
            row = cur.execute(
                "select last_text from messages where channel_id=? and message_id=?",
                (channel_id, int(mid)),
            ).fetchone()
            old_text = _safe_str(row[0]) if row and row[0] is not None else ""

            stats = db.record_edit(
                channel_id=channel_id,
                message_id=mid,
                channel_link=channel_link,
                channel_title=channel_title,
                message_date_iso=msg_date_iso,
                edit_date_iso=edit_date_iso,
                observed_ts=now_ts,
                old_text=old_text,
                new_text=new_text,
                include_text=cfg.include_text,
            )

            log_event(
                logger,
                logging.INFO,
                "message_edited",
                channel=channel_link or channel_title or channel_id,
                channel_id=channel_id,
                message_id=mid,
                message_date=msg_date_iso,
                edit_date=edit_date_iso,
                changed=stats.get("changed"),
                delta_len=stats.get("delta_len"),
            )

            if cfg.events_jsonl_path:
                _append_jsonl(
                    cfg.events_jsonl_path,
                    {
                        "ts": now_ts,
                        "event_type": "edit",
                        "channel_id": channel_id,
                        "channel_link": channel_link,
                        "channel_title": channel_title,
                        "message_id": mid,
                        "message_date": msg_date_iso,
                        "edit_date": edit_date_iso,
                        "old_hash": stats.get("old_hash"),
                        "new_hash": stats.get("new_hash"),
                        "old_len": stats.get("old_len"),
                        "new_len": stats.get("new_len"),
                        "delta_len": stats.get("delta_len"),
                        "old_text": old_text if cfg.include_text else None,
                        "new_text": new_text if cfg.include_text else None,
                    },
                )
        except Exception:
            logger.debug("on_message_edited_failed", exc_info=True)

    @client.on(events.MessageDeleted)
    async def on_message_deleted(event) -> None:
        try:
            chat = await event.get_chat()
            channel_id, channel_link, channel_title = await resolve_channel_meta(chat)
            now_ts = _utc_now_ts()
            ids = list(getattr(event, "deleted_ids", None) or getattr(event, "deleted_ids", []) or [])
            if not ids and getattr(event, "deleted_id", None) is not None:
                ids = [getattr(event, "deleted_id")]

            for mid in ids:
                try:
                    db.record_delete(
                        channel_id=channel_id,
                        message_id=int(mid),
                        channel_link=channel_link,
                        channel_title=channel_title,
                        observed_ts=now_ts,
                    )
                except Exception:
                    logger.debug("record_delete_failed", exc_info=True)

            log_event(
                logger,
                logging.INFO,
                "message_deleted",
                channel=channel_link or channel_title or channel_id,
                channel_id=channel_id,
                deleted_count=len(ids),
            )

            if cfg.events_jsonl_path:
                _append_jsonl(
                    cfg.events_jsonl_path,
                    {
                        "ts": now_ts,
                        "event_type": "delete",
                        "channel_id": channel_id,
                        "channel_link": channel_link,
                        "channel_title": channel_title,
                        "message_ids": [int(x) for x in ids],
                    },
                )
        except Exception:
            logger.debug("on_message_deleted_failed", exc_info=True)

    # Summary loop for quick health/stats while running.
    asyncio.create_task(_summary_loop(db, cfg))

    try:
        res = client.run_until_disconnected()
        if asyncio.iscoroutine(res):
            await res
    finally:
        db.close()


def main() -> None:
    setup_logging()
    global logger
    logger = logging.getLogger("monitor_message_edits")
    t0 = timed()
    try:
        asyncio.run(run())
    finally:
        log_event(logger, logging.INFO, "edit_monitor_exit", total_ms=round((timed() - t0) * 1000.0, 2))


if __name__ == "__main__":
    main()
