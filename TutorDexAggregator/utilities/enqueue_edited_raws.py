"""
Enqueue extraction jobs for Telegram messages that were edited.

Why:
- `collector.py live` already enqueues on edit events in real time.
- If the collector was down (or you backfilled raw later), edits may be present in
  `telegram_messages_raw.edit_date` but not yet reprocessed.

This script reads Supabase raw rows (no Telegram calls) and enqueues extraction jobs
via RPC `enqueue_telegram_extractions` with `force=true`.
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

try:
    from supabase_raw_persist import SupabaseRawStore  # type: ignore
except Exception:
    from TutorDexAggregator.supabase_raw_persist import SupabaseRawStore  # type: ignore


STATE_PATH_DEFAULT = (HERE.parent / "state" / "enqueue_edited_raws_state.json").resolve()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    if not s:
        return None
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _pipeline_version() -> str:
    # Keep consistent with collector/worker; any unique string works.
    return (os.environ.get("EXTRACTION_PIPELINE_VERSION") or "").strip() or "default"


def _load_state(path: Path) -> Dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_state(path: Path, state: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _parse_channels_arg(value: Optional[str]) -> List[str]:
    if not value:
        return []
    raw = value.strip()
    if not raw:
        return []
    # Accept JSON array or comma-separated.
    if raw.startswith("["):
        try:
            arr = json.loads(raw)
            if isinstance(arr, list):
                return [str(x).strip() for x in arr if str(x).strip()]
        except Exception:
            pass
    return [s.strip() for s in raw.split(",") if s.strip()]


def _normalize_channel_ref(value: str) -> str:
    v = (value or "").strip()
    if not v:
        return ""
    lv = v.lower()
    if lv.startswith("https://") or lv.startswith("http://"):
        v = v.rstrip("/").split("/")[-1]
        lv = v.lower()
    if lv.startswith("t.me/"):
        v = v.split("/", 1)[1]
    if v.startswith("@"):
        v = v[1:]
    return f"t.me/{v}".lower()


def _enqueue_rpc(store: SupabaseRawStore, *, channel_link: str, message_ids: List[str], force: bool) -> Dict[str, Any]:
    if not store.client:
        return {"ok": False, "reason": "supabase_disabled"}
    if not message_ids:
        return {"ok": True, "skipped": True, "reason": "no_messages"}

    payload = {
        "p_channel_link": channel_link,
        "p_message_ids": [str(x) for x in message_ids if str(x).strip()],
        "p_pipeline_version": _pipeline_version(),
        "p_force": bool(force),
    }
    resp = store.client.post("rpc/enqueue_telegram_extractions", payload, timeout=30)
    ok = resp.status_code < 400
    body: Any = None
    try:
        body = resp.json()
    except Exception:
        body = (resp.text or "")[:300]
    return {"ok": ok, "status_code": resp.status_code, "resp": body}


def main() -> int:
    p = argparse.ArgumentParser(description="Enqueue extraction jobs for edited Telegram raw messages (Supabase-only).")
    p.add_argument("--channels", help="Comma-separated or JSON array; defaults to CHANNEL_LIST env var.")
    p.add_argument("--since", help="ISO datetime (inclusive) based on raw.edit_date; default from checkpoint.")
    p.add_argument("--until", help="ISO datetime (exclusive-ish) based on raw.edit_date.")
    p.add_argument("--limit-per-channel", type=int, default=500, help="Max edited messages per channel per run.")
    p.add_argument("--state-file", default=str(STATE_PATH_DEFAULT), help="Checkpoint state JSON path.")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    store = SupabaseRawStore()
    if not store.enabled() or not store.client:
        raise SystemExit("Supabase raw store disabled/misconfigured (set SUPABASE_RAW_ENABLED=1 + service role key).")

    state_path = Path(args.state_file).expanduser()
    state = _load_state(state_path)
    checkpoint_s = str(state.get("last_edit_date") or "").strip() or None
    checkpoint_raw_id = state.get("last_raw_id")
    try:
        checkpoint_raw_id_i = int(checkpoint_raw_id) if checkpoint_raw_id is not None else None
    except Exception:
        checkpoint_raw_id_i = None

    since_dt = _parse_iso_dt(args.since) if args.since else _parse_iso_dt(checkpoint_s)
    until_dt = _parse_iso_dt(args.until) if args.until else None

    # Default: last 24h if no checkpoint.
    if since_dt is None:
        since_dt = _utc_now() - timedelta(hours=24)  # type: ignore[name-defined]

    channels = _parse_channels_arg(args.channels) if args.channels else []
    if not channels:
        channels = _parse_channels_arg(os.environ.get("CHANNEL_LIST") or "")
    channels = [_normalize_channel_ref(c) for c in channels]
    channels = [c for c in channels if c]
    if not channels:
        raise SystemExit("No channels provided (pass --channels or set CHANNEL_LIST in env).")

    latest_seen: Optional[datetime] = since_dt
    latest_raw_id: Optional[int] = checkpoint_raw_id_i
    total_enqueued = 0

    for ch in channels:
        lim = max(1, min(int(args.limit_per_channel), 5000))
        parts = [
            "select=id,message_id,edit_date",
            f"channel_link=eq.{requests.utils.quote(ch, safe='')}",
            "edit_date=not.is.null",
            "deleted_at=is.null",
        ]
        if checkpoint_s and not args.since:
            # Continue from checkpoint without re-enqueueing the same edge rows.
            # Tie-breaker is raw `id` (numeric, monotonic), not message_id (text).
            cutoff_iso = _iso(since_dt)
            if checkpoint_raw_id_i is not None:
                parts.append(
                    "or=("
                    f"edit_date.gt.{requests.utils.quote(cutoff_iso, safe='')},"
                    f"and(edit_date.eq.{requests.utils.quote(cutoff_iso, safe='')},id.gt.{int(checkpoint_raw_id_i)})"
                    ")"
                )
            else:
                parts.append(f"edit_date=gt.{requests.utils.quote(cutoff_iso, safe='')}")
        else:
            parts.append(f"edit_date=gte.{requests.utils.quote(_iso(since_dt), safe='')}")
        if until_dt is not None:
            parts.append(f"edit_date=lt.{requests.utils.quote(_iso(until_dt), safe='')}")
        parts.append("order=edit_date.asc,id.asc")
        parts.append(f"limit={lim}")
        q = f"{store.cfg.messages_table}?" + "&".join(parts)

        resp = store.client.get(q, timeout=30)
        if resp.status_code >= 400:
            print(f"ERROR channel={ch} status={resp.status_code} body={(resp.text or '')[:200]}")
            continue
        try:
            rows = resp.json()
        except Exception:
            rows = []
        if not isinstance(rows, list) or not rows:
            continue

        ids: List[str] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            rid = r.get("id")
            try:
                rid_i = int(rid) if rid is not None else None
            except Exception:
                rid_i = None
            mid = str(r.get("message_id") or "").strip()
            if mid:
                ids.append(mid)
            ed = _parse_iso_dt(str(r.get("edit_date") or "").strip())
            if ed and (latest_seen is None or ed > latest_seen):
                latest_seen = ed
                latest_raw_id = rid_i
            elif ed and latest_seen is not None and ed == latest_seen and rid_i is not None:
                if latest_raw_id is None or rid_i > latest_raw_id:
                    latest_raw_id = rid_i

        if not ids:
            continue

        if args.dry_run:
            print(f"DRY_RUN channel={ch} edited={len(ids)}")
            continue

        res = _enqueue_rpc(store, channel_link=ch, message_ids=ids, force=True)
        if not res.get("ok"):
            print(f"ERROR enqueue channel={ch} res={res}")
            continue
        total_enqueued += len(ids)
        print(f"OK channel={ch} enqueued={len(ids)}")

    # Advance checkpoint.
    if not args.dry_run and latest_seen is not None:
        state["last_edit_date"] = _iso(latest_seen)
        state["last_raw_id"] = int(latest_raw_id) if latest_raw_id is not None else None
        state["updated_at"] = _iso(_utc_now())
        _save_state(state_path, state)

    print({"ok": True, "total_enqueued": total_enqueued, "checkpoint": state.get("last_edit_date")})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
