"""
Quick consistency check between raw Telegram rows and assignments for a recent window.

Usage:
  python utilities/check_recent_counts.py --minutes 60

Requires:
- SUPABASE_URL_HOST / SUPABASE_URL_DOCKER / SUPABASE_URL
- SUPABASE_SERVICE_ROLE_KEY (or SUPABASE_KEY)

This does not modify data; it only queries counts. If Supabase is disabled or env vars
are missing, the script exits with a message.
"""

import argparse
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Tuple

import requests

from shared.config import load_aggregator_config

AGG_DIR = Path(__file__).resolve().parents[1]
if str(AGG_DIR) not in sys.path:
    sys.path.insert(0, str(AGG_DIR))

from supabase_env import resolve_supabase_url  # noqa: E402
from shared.observability.exception_handler import swallow_exception


def _supabase_cfg() -> Optional[Tuple[str, str]]:
    url = resolve_supabase_url()
    key = str(load_aggregator_config().supabase_auth_key or "").strip()
    if not (url and key):
        return None
    return url, key


def _count(client: requests.Session, base: str, table: str, ts_column: str, since_iso: str) -> Optional[int]:
    # Use PostgREST count via Prefer header (exact).
    url = f"{base}/rest/v1/{table}?select=id&{ts_column}=gte.{since_iso}"
    resp = client.get(url, timeout=20, headers={"Prefer": "count=exact"})
    if resp.status_code >= 400:
        return None
    content_range = resp.headers.get("Content-Range") or ""
    # Format: items 0-24/25
    if "/" in content_range:
        try:
            return int(content_range.split("/")[-1])
        except Exception:
            pass
    try:
        data = resp.json()
        return len(data) if isinstance(data, list) else None
    except Exception:
        return None


def main() -> None:
    cfg = _supabase_cfg()
    if not cfg:
        print("Supabase env not set (SUPABASE_URL_HOST/SUPABASE_URL_DOCKER/SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY). Nothing to do.")
        return
    url, key = cfg
    p = argparse.ArgumentParser(description="Check recent raw vs assignments counts")
    p.add_argument("--minutes", type=int, default=60, help="Lookback window in minutes (default 60)")
    args = p.parse_args()

    since = datetime.now(timezone.utc) - timedelta(minutes=args.minutes)
    since_iso = since.isoformat()

    session = requests.Session()
    session.headers.update({"apikey": key, "authorization": f"Bearer {key}"})

    raw_count = _count(session, url, "telegram_messages_raw", "message_date", since_iso)
    assignments_count = _count(session, url, "assignments", "last_seen", since_iso)

    print(f"Lookback minutes: {args.minutes}")
    print(f"Since: {since_iso}")
    print(f"Raw messages (telegram_messages_raw.message_date >=): {raw_count}")
    print(f"Assignments (assignments.last_seen >=): {assignments_count}")
    if raw_count is not None and assignments_count is not None:
        delta = raw_count - assignments_count
        print(f"Delta (raw - assignments): {delta}")
    else:
        print("One of the counts is unavailable (permission or table missing).")


if __name__ == "__main__":
    main()
