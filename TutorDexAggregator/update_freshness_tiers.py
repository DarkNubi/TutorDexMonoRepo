import argparse
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List

from logging_setup import log_event, setup_logging, timed
from supabase_persist import SupabaseRestClient, load_config_from_env


setup_logging()
logger = logging.getLogger("update_freshness_tiers")

try:
    from dotenv import load_dotenv  # type: ignore
except Exception:
    load_dotenv = None

HERE = Path(__file__).resolve().parent
ENV_PATH = HERE / ".env"
if load_dotenv and ENV_PATH.exists():
    load_dotenv(dotenv_path=ENV_PATH)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


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
    yellow_hours: int = 36,
    orange_hours: int = 84,
    red_hours: int = 168,
    expire_action: str = "none",  # none|closed|expired
    dry_run: bool = False,
) -> Dict[str, Any]:
    cfg = load_config_from_env()
    if not cfg.enabled:
        return {"ok": False, "skipped": True, "reason": "supabase_disabled"}

    client = SupabaseRestClient(cfg)
    now = _utc_now()
    t0 = timed()

    yellow_cutoff = now - timedelta(hours=int(yellow_hours))
    orange_cutoff = now - timedelta(hours=int(orange_hours))
    red_cutoff = now - timedelta(hours=int(red_hours))

    def patch_where(where_qs: str, body: Dict[str, Any]) -> Dict[str, Any]:
        if dry_run:
            return {"ok": True, "dry_run": True, "where": where_qs, "body": body}
        resp = client.patch(where_qs, body, timeout=30, prefer="return=representation")
        ok = resp.status_code < 400
        n = None
        try:
            n = len(resp.json())
        except Exception:
            n = None
        return {"ok": ok, "status_code": resp.status_code, "updated": n}

    # Green: last_seen >= yellow_cutoff
    green_q = f"{cfg.assignments_table}?status=eq.open&last_seen=gte.{_iso(yellow_cutoff)}"
    yellow_q = f"{cfg.assignments_table}?status=eq.open&last_seen=lt.{_iso(yellow_cutoff)}&last_seen=gte.{_iso(orange_cutoff)}"
    orange_q = f"{cfg.assignments_table}?status=eq.open&last_seen=lt.{_iso(orange_cutoff)}&last_seen=gte.{_iso(red_cutoff)}"
    red_q = f"{cfg.assignments_table}?status=eq.open&last_seen=lt.{_iso(red_cutoff)}"

    log_event(
        logger,
        logging.INFO,
        "freshness_update_start",
        yellow_hours=yellow_hours,
        orange_hours=orange_hours,
        red_hours=red_hours,
        expire_action=expire_action,
        dry_run=dry_run,
    )

    out: Dict[str, Any] = {"ok": True, "dry_run": dry_run, "expire_action": expire_action}
    out["green"] = patch_where(green_q, {"freshness_tier": "green"})
    out["yellow"] = patch_where(yellow_q, {"freshness_tier": "yellow"})
    out["orange"] = patch_where(orange_q, {"freshness_tier": "orange"})

    if expire_action in {"closed", "expired"}:
        out["red"] = patch_where(red_q, {"freshness_tier": "red", "status": expire_action})
    else:
        out["red"] = patch_where(red_q, {"freshness_tier": "red"})

    out["total_ms"] = round((timed() - t0) * 1000.0, 2)
    log_event(logger, logging.INFO, "freshness_update_done", **out)
    return out


def main() -> None:
    p = argparse.ArgumentParser(description="Update freshness tiers in Supabase based on assignments.last_seen.")
    p.add_argument("--yellow-hours", type=int, default=36)
    p.add_argument("--orange-hours", type=int, default=84)
    p.add_argument("--red-hours", type=int, default=168)
    p.add_argument("--expire-action", default="none", choices=["none", "closed", "expired"])
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    res = update_tiers(
        yellow_hours=args.yellow_hours,
        orange_hours=args.orange_hours,
        red_hours=args.red_hours,
        expire_action=args.expire_action,
        dry_run=args.dry_run,
    )
    print(res)


if __name__ == "__main__":
    main()
