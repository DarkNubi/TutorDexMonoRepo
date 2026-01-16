import argparse
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from logging_setup import log_event, setup_logging, timed
from supabase_persist import load_config_from_env, SupabaseRestClient


setup_logging()
logger = logging.getLogger("expire_assignments")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    # PostgREST filter values are embedded in the URL; avoid "+" by using "Z".
    return dt.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _get_exact_count(client: SupabaseRestClient, table: str, *, cutoff_iso: str) -> Optional[int]:
    url = f"{table}?select=id&status=eq.open&last_seen=lt.{cutoff_iso}"
    try:
        resp = client.head(url, prefer="count=exact", timeout=20)
    except Exception:
        logger.debug("Expire count request failed", exc_info=True)
        return None

    if resp.status_code >= 400:
        return None
    content_range = resp.headers.get("Content-Range") or resp.headers.get("content-range") or ""
    # Format: 0-0/123 or */123
    if "/" in content_range:
        try:
            return int(content_range.split("/")[-1])
        except Exception:
            return None
    return None


def expire_open_assignments(*, days: int = 7, dry_run: bool = False) -> Dict[str, Any]:
    cfg = load_config_from_env()
    if not cfg.enabled:
        return {"ok": False, "skipped": True, "reason": "supabase_disabled"}

    client = SupabaseRestClient(cfg)
    cutoff = _utc_now() - timedelta(days=int(days))
    cutoff_iso = _iso(cutoff)
    table = cfg.assignments_table

    t0 = timed()
    count = _get_exact_count(client, table, cutoff_iso=cutoff_iso)

    if dry_run:
        res = {"ok": True, "dry_run": True, "cutoff": cutoff_iso, "would_close": count}
        res["total_ms"] = round((timed() - t0) * 1000.0, 2)
        log_event(logger, logging.INFO, "expire_dry_run", **res)
        return res

    try:
        t_patch = timed()
        resp = client.patch(
            f"{table}?status=eq.open&last_seen=lt.{cutoff_iso}",
            {"status": "closed"},
            timeout=30,
            prefer="return=representation",
        )
        patch_ms = round((timed() - t_patch) * 1000.0, 2)
    except Exception as e:
        log_event(logger, logging.ERROR, "expire_patch_failed", error=str(e))
        return {"ok": False, "error": str(e)}

    ok = resp.status_code < 400
    if not ok:
        log_event(logger, logging.WARNING, "expire_patch_status", status_code=resp.status_code, body=resp.text[:500])
        return {"ok": False, "status_code": resp.status_code, "body": resp.text[:500]}

    closed = None
    try:
        closed = len(resp.json())
    except Exception:
        closed = None

    res = {"ok": True, "cutoff": cutoff_iso, "closed": closed, "previously_open_older_than_cutoff": count}
    res["patch_ms"] = patch_ms
    res["total_ms"] = round((timed() - t0) * 1000.0, 2)
    log_event(logger, logging.INFO, "expire_done", **res)
    return res


def main() -> None:
    p = argparse.ArgumentParser(description="Close stale assignments in Supabase (status=open, last_seen older than N days).")
    p.add_argument("--days", type=int, default=7, help="Close if last_seen is older than this many days (default: 7)")
    p.add_argument("--dry-run", action="store_true", help="Only count how many would be closed")
    args = p.parse_args()

    res = expire_open_assignments(days=args.days, dry_run=args.dry_run)
    log_event(logger, logging.INFO, "expire_result", **res)
    print(res)


if __name__ == "__main__":
    main()
