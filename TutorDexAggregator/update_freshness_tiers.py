import argparse
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
import re

from shared.config import load_aggregator_config

from logging_setup import log_event, setup_logging, timed
from supabase_persist import SupabaseRestClient, load_config_from_env


setup_logging()
logger = logging.getLogger("update_freshness_tiers")

HERE = Path(__file__).resolve().parent


def _iso(dt: datetime) -> str:
    # PostgREST filter values are embedded in the URL; avoid "+" by using "Z".
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _coerce_rows(resp) -> List[Dict[str, Any]]:
    try:
        data = resp.json()
    except Exception:
        return []
    return data if isinstance(data, list) else []


def update_tiers(
    *,
    green_hours: int = 24,
    yellow_hours: int = 36,
    orange_hours: int = 48,
    red_hours: int = 72,
    expire_hours: int = 168,
    expire_action: str = "none",  # none|closed|expired
    delete_expired_telegram: bool = False,
    delete_batch_limit: int = 200,
    dry_run: bool = False,
) -> Dict[str, Any]:
    cfg = load_config_from_env()
    if not cfg.enabled:
        return {"ok": False, "skipped": True, "reason": "supabase_disabled"}

    client = SupabaseRestClient(cfg)
    now = _utc_now()
    t0 = timed()

    green_cutoff = now - timedelta(hours=int(green_hours))
    yellow_cutoff = now - timedelta(hours=int(yellow_hours))
    orange_cutoff = now - timedelta(hours=int(orange_hours))
    red_cutoff = now - timedelta(hours=int(red_hours))
    expire_cutoff = now - timedelta(hours=int(expire_hours))

    def patch_where(where_qs: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if dry_run:
            return {"ok": True, "dry_run": True, "where": where_qs, "body": body}
        resp = client.patch(where_qs, body, timeout=30, prefer="return=representation")
        ok = resp.status_code < 400
        updated = None
        rows: List[Dict[str, Any]] = []
        if ok:
            try:
                rows = _coerce_rows(resp)
                updated = len(rows)
            except Exception:
                updated = None
        else:
            log_event(
                logger,
                logging.WARNING,
                "freshness_patch_failed",
                status_code=resp.status_code,
                where=where_qs,
                body=body,
                resp_body=(resp.text or "")[:500],
            )
        return {"ok": ok, "status_code": resp.status_code, "updated": updated, "rows": rows}

    # Freshness tiers should reflect upstream bumps/edits, not when we reprocessed history.
    # Use `source_last_seen` when present; fall back to published_at/created_at/last_seen for older rows.
    green_q = (
        f"{cfg.assignments_table}?status=eq.open"
        f"&or=(source_last_seen.gte.{_iso(green_cutoff)},and(source_last_seen.is.null,published_at.gte.{_iso(green_cutoff)}),and(source_last_seen.is.null,published_at.is.null,created_at.gte.{_iso(green_cutoff)}),and(source_last_seen.is.null,published_at.is.null,created_at.is.null,last_seen.gte.{_iso(green_cutoff)}))"
    )
    yellow_q = (
        f"{cfg.assignments_table}?status=eq.open"
        f"&or=(and(source_last_seen.lt.{_iso(green_cutoff)},source_last_seen.gte.{_iso(yellow_cutoff)}),and(source_last_seen.is.null,published_at.lt.{_iso(green_cutoff)},published_at.gte.{_iso(yellow_cutoff)}),and(source_last_seen.is.null,published_at.is.null,created_at.lt.{_iso(green_cutoff)},created_at.gte.{_iso(yellow_cutoff)}),and(source_last_seen.is.null,published_at.is.null,created_at.is.null,last_seen.lt.{_iso(green_cutoff)},last_seen.gte.{_iso(yellow_cutoff)}))"
    )
    orange_q = (
        f"{cfg.assignments_table}?status=eq.open"
        f"&or=(and(source_last_seen.lt.{_iso(yellow_cutoff)},source_last_seen.gte.{_iso(orange_cutoff)}),and(source_last_seen.is.null,published_at.lt.{_iso(yellow_cutoff)},published_at.gte.{_iso(orange_cutoff)}),and(source_last_seen.is.null,published_at.is.null,created_at.lt.{_iso(yellow_cutoff)},created_at.gte.{_iso(orange_cutoff)}),and(source_last_seen.is.null,published_at.is.null,created_at.is.null,last_seen.lt.{_iso(yellow_cutoff)},last_seen.gte.{_iso(orange_cutoff)}))"
    )
    red_q = (
        f"{cfg.assignments_table}?status=eq.open"
        f"&or=(and(source_last_seen.lt.{_iso(orange_cutoff)},source_last_seen.gte.{_iso(red_cutoff)}),and(source_last_seen.is.null,published_at.lt.{_iso(orange_cutoff)},published_at.gte.{_iso(red_cutoff)}),and(source_last_seen.is.null,published_at.is.null,created_at.lt.{_iso(orange_cutoff)},created_at.gte.{_iso(red_cutoff)}),and(source_last_seen.is.null,published_at.is.null,created_at.is.null,last_seen.lt.{_iso(orange_cutoff)},last_seen.gte.{_iso(red_cutoff)}))"
    )
    expired_q = (
        f"{cfg.assignments_table}?status=eq.open"
        f"&or=(source_last_seen.lt.{_iso(expire_cutoff)},and(source_last_seen.is.null,published_at.lt.{_iso(expire_cutoff)}),and(source_last_seen.is.null,published_at.is.null,created_at.lt.{_iso(expire_cutoff)}),and(source_last_seen.is.null,published_at.is.null,created_at.is.null,last_seen.lt.{_iso(expire_cutoff)}))"
    )

    log_event(
        logger,
        logging.INFO,
        "freshness_update_start",
        green_hours=green_hours,
        yellow_hours=yellow_hours,
        orange_hours=orange_hours,
        red_hours=red_hours,
        expire_hours=expire_hours,
        expire_action=expire_action,
        delete_expired_telegram=delete_expired_telegram,
        delete_batch_limit=delete_batch_limit,
        dry_run=dry_run,
    )

    out: Dict[str, Any] = {"ok": True, "dry_run": dry_run, "expire_action": expire_action}
    out["green"] = patch_where(green_q, {"freshness_tier": "green"})
    out["yellow"] = patch_where(yellow_q, {"freshness_tier": "yellow"})
    out["orange"] = patch_where(orange_q, {"freshness_tier": "orange"})
    out["red"] = patch_where(red_q, {"freshness_tier": "red"})

    # Propagate freshness changes to any previously-sent broadcast Telegram messages
    # so that the emoji + label shown in broadcasts stays in sync.
    def _propagate(rows: List[Dict[str, Any]], emoji: str, label: str) -> Dict[str, Any]:
        if not rows:
            return {"ok": True, "skipped": True, "reason": "no_rows"}
        token = _bot_token()
        if not token:
            return {"ok": False, "reason": "missing_GROUP_BOT_TOKEN"}

        external_ids = [str(r.get("external_id") or "").strip() for r in rows if isinstance(r, dict) and r.get("external_id")]
        external_ids = [x for x in external_ids if x]
        if not external_ids:
            return {"ok": True, "skipped": True, "reason": "no_external_ids"}

        results = {"updated": 0, "failed": 0, "skipped": 0}
        # Query broadcast_messages for these external_ids
        for ext in external_ids:
            # Fetch broadcast message rows for this external_id
            bqs = (
                "broadcast_messages?select=external_id,sent_chat_id,sent_message_id,message_html,deleted_at"
                f"&external_id=eq.{requests.utils.quote(ext, safe='')}"
                "&deleted_at=is.null"
                "&limit=100"
            )
            bresp = client.get(bqs, timeout=30)
            if bresp.status_code >= 400:
                results["failed"] += 1
                continue
            try:
                bmsgs = bresp.json() if isinstance(bresp.json(), list) else []
            except Exception:
                results["failed"] += 1
                continue

            for bm in bmsgs:
                if not isinstance(bm, dict):
                    results["skipped"] += 1
                    continue
                chat_id = bm.get("sent_chat_id")
                message_id = bm.get("sent_message_id")
                message_html = bm.get("message_html") or ""
                if not chat_id or not message_id:
                    results["skipped"] += 1
                    continue

                # Replace existing freshness line if present, otherwise insert after first line
                new_text = message_html
                try:
                    pattern = re.compile(r'^(?:🟢|🟡|🟠|🔴)\s.*', flags=re.M)
                    if pattern.search(new_text):
                        new_text = pattern.sub(f"{emoji} {label}", new_text, count=1)
                    else:
                        parts = new_text.splitlines()
                        if parts:
                            parts.insert(1, f"{emoji} {label}")
                            new_text = "\n".join(parts)
                        else:
                            new_text = f"{emoji} {label}\n" + new_text
                except Exception:
                    results["skipped"] += 1
                    continue

                if dry_run:
                    results["updated"] += 1
                    continue

                # Call Telegram editMessageText
                try:
                    edit_url = f"{_telegram_api_base(token)}/editMessageText"
                    resp = requests.post(edit_url, json={"chat_id": int(chat_id), "message_id": int(message_id),
                                         "text": new_text, "parse_mode": "HTML", "disable_web_page_preview": True}, timeout=15)
                except Exception:
                    results["failed"] += 1
                    continue

                try:
                    data = resp.json()
                except Exception:
                    data = {"ok": False}

                if resp.status_code >= 400 or not bool(data.get("ok")):
                    results["failed"] += 1
                    continue

                # Update stored message_html in broadcast_messages for record-keeping
                try:
                    presp = client.patch(f"broadcast_messages?external_id=eq.{requests.utils.quote(ext, safe='')}", {
                                         "message_html": new_text}, timeout=20, prefer="return=minimal")
                    # ignore failures here; it's best-effort
                except Exception:
                    pass

                results["updated"] += 1

        return {"ok": True, **results}

    # Propagate for each tier change
    try:
        out["propagate_green"] = _propagate(out["green"].get("rows", []), "🟢", "Likely open")
        out["propagate_yellow"] = _propagate(out["yellow"].get("rows", []), "🟡", "Probably open")
        out["propagate_orange"] = _propagate(out["orange"].get("rows", []), "🟠", "Uncertain")
        out["propagate_red"] = _propagate(out["red"].get("rows", []), "🔴", "Likely closed")
    except Exception:
        log_event(logger, logging.WARNING, "freshness_propagation_failed", exc_info=True)

    if expire_action in {"closed", "expired"}:
        out["expired"] = patch_where(expired_q, {"freshness_tier": "red", "status": expire_action})
    else:
        out["expired"] = {"ok": True, "skipped": True, "reason": "expire_action_none"}

    if delete_expired_telegram and expire_action in {"closed", "expired"}:
        out["telegram_delete"] = delete_expired_broadcast_messages(
            client=client,
            assignments_table=cfg.assignments_table,
            expire_action=expire_action,
            expired_before=_iso(expire_cutoff),
            now_iso=_iso(now),
            dry_run=dry_run,
            limit=int(delete_batch_limit),
        )
    else:
        out["telegram_delete"] = {"ok": True, "skipped": True}

    out["total_ms"] = round((timed() - t0) * 1000.0, 2)
    log_event(logger, logging.INFO, "freshness_update_done", **out)
    return out


def _bot_token() -> str:
    return str(load_aggregator_config().group_bot_token or "").strip()


def _telegram_api_base(token: str) -> str:
    return f"https://api.telegram.org/bot{token.strip()}"


def _telegram_delete_message(*, token: str, chat_id: int, message_id: int, timeout_s: int = 15) -> Dict[str, Any]:
    url = f"{_telegram_api_base(token)}/deleteMessage"
    try:
        resp = requests.post(url, json={"chat_id": int(chat_id), "message_id": int(message_id)}, timeout=timeout_s)
    except Exception as e:
        return {"ok": False, "error": str(e)}

    try:
        data = resp.json()
    except Exception:
        data = {"text": (resp.text or "")[:500]}

    if resp.status_code >= 400 or not bool(data.get("ok")):
        return {
            "ok": False,
            "status_code": resp.status_code,
            "telegram": {
                "error_code": data.get("error_code"),
                "description": data.get("description"),
            },
        }
    return {"ok": True, "status_code": resp.status_code}


def _coerce_int(value: Any) -> Optional[int]:
    try:
        if value is None:
            return None
        return int(value)
    except Exception:
        return None


def delete_expired_broadcast_messages(
    *,
    client: SupabaseRestClient,
    assignments_table: str,
    expire_action: str,
    expired_before: str,
    now_iso: str,
    dry_run: bool,
    limit: int,
) -> Dict[str, Any]:
    token = _bot_token()
    if not token:
        return {"ok": False, "skipped": True, "reason": "missing_group_bot_token"}
    if not token:
        return {"ok": False, "reason": "missing_GROUP_BOT_TOKEN"}

    # 1) Find expired/closed assignments (by status + last_seen cutoff) and map to broadcast_messages via external_id.
    qs = (
        f"{assignments_table}"
        f"?select=external_id"
        f"&status=eq.{expire_action}"
        f"&last_seen=lt.{expired_before}"
        f"&external_id=not.is.null"
        f"&order=last_seen.asc"
        f"&limit={max(1, int(limit))}"
    )
    resp = client.get(qs, timeout=30)
    if resp.status_code >= 400:
        return {"ok": False, "reason": "assignments_query_failed", "status_code": resp.status_code, "body": (resp.text or "")[:500]}

    rows = _coerce_rows(resp)
    external_ids = [str(r.get("external_id") or "").strip() for r in rows if isinstance(r, dict)]
    external_ids = [x for x in external_ids if x]
    if not external_ids:
        return {"ok": True, "deleted": 0, "skipped": 0, "reason": "no_expired_assignments"}

    # 2) Fetch broadcast message rows that haven't been deleted yet.
    in_list = ",".join([requests.utils.quote(x, safe="") for x in external_ids])
    bqs = (
        "broadcast_messages?select=external_id,sent_chat_id,sent_message_id,deleted_at"
        f"&external_id=in.({in_list})"
        "&deleted_at=is.null"
        f"&limit={max(1, int(limit))}"
    )
    bresp = client.get(bqs, timeout=30)
    if bresp.status_code >= 400:
        return {"ok": False, "reason": "broadcast_messages_query_failed", "status_code": bresp.status_code, "body": (bresp.text or "")[:500]}

    bmsgs = _coerce_rows(bresp)
    if not bmsgs:
        return {"ok": True, "deleted": 0, "skipped": len(external_ids), "reason": "no_pending_broadcast_messages"}

    deleted = 0
    failed = 0
    skipped = 0
    for bm in bmsgs:
        if not isinstance(bm, dict):
            skipped += 1
            continue
        external_id = str(bm.get("external_id") or "").strip()
        chat_id = _coerce_int(bm.get("sent_chat_id"))
        message_id = _coerce_int(bm.get("sent_message_id"))
        if not external_id or chat_id is None or message_id is None:
            skipped += 1
            continue

        if dry_run:
            deleted += 1
            continue

        res = _telegram_delete_message(token=token, chat_id=chat_id, message_id=message_id)
        if not res.get("ok"):
            failed += 1
            log_event(logger, logging.WARNING, "telegram_delete_failed", external_id=external_id, chat_id=chat_id, message_id=message_id, res=res)
            continue

        # Mark as deleted to avoid retry loops.
        presp = client.patch(
            f"broadcast_messages?external_id=eq.{requests.utils.quote(external_id, safe='')}",
            {"deleted_at": now_iso},
            timeout=20,
            prefer="return=minimal",
        )
        if presp.status_code >= 400:
            failed += 1
            log_event(logger, logging.WARNING, "broadcast_messages_mark_deleted_failed",
                      external_id=external_id, status_code=presp.status_code, body=(presp.text or "")[:300])
            continue

        deleted += 1

    return {"ok": failed == 0, "deleted": deleted, "failed": failed, "skipped": skipped, "considered": len(bmsgs)}


def main() -> None:
    p = argparse.ArgumentParser(description="Update freshness tiers in Supabase based on assignments.last_seen.")
    p.add_argument("--green-hours", type=int, default=24)
    p.add_argument("--yellow-hours", type=int, default=36)
    p.add_argument("--orange-hours", type=int, default=48)
    p.add_argument("--red-hours", type=int, default=72)
    p.add_argument("--expire-hours", type=int, default=168)
    p.add_argument("--expire-action", default="none", choices=["none", "closed", "expired"])
    p.add_argument("--delete-expired-telegram", action="store_true")
    p.add_argument("--delete-batch-limit", type=int, default=200)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    res = update_tiers(
        green_hours=args.green_hours,
        yellow_hours=args.yellow_hours,
        orange_hours=args.orange_hours,
        red_hours=args.red_hours,
        expire_hours=args.expire_hours,
        expire_action=args.expire_action,
        delete_expired_telegram=bool(args.delete_expired_telegram),
        delete_batch_limit=int(args.delete_batch_limit),
        dry_run=args.dry_run,
    )
    print(res)


if __name__ == "__main__":
    main()
