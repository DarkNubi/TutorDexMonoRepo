import logging
import sys
from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, Optional

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from logging_setup import log_event, setup_logging
from supabase_persist import SupabaseRestClient, load_config_from_env


setup_logging()
logger = logging.getLogger("check_freshness_tiers")


def _get_exact_count(client: SupabaseRestClient, table: str, *, where_qs: str) -> Optional[int]:
    url = f"{table}?select=id&{where_qs}"
    try:
        resp = client.head(url, prefer="count=exact", timeout=20)
    except Exception:
        logger.debug("count_request_failed", exc_info=True)
        return None

    if resp.status_code >= 400:
        log_event(logger, logging.WARNING, "count_request_status", status_code=resp.status_code, body=resp.text[:400])
        return None

    content_range = resp.headers.get("Content-Range") or resp.headers.get("content-range") or ""
    if "/" in content_range:
        try:
            return int(content_range.split("/")[-1])
        except Exception:
            return None
    return None


def main() -> None:
    cfg = load_config_from_env()
    if not cfg.enabled:
        print({"ok": False, "skipped": True, "reason": "supabase_disabled"})
        return

    client = SupabaseRestClient(cfg)
    table = cfg.assignments_table

    counts: Dict[str, Any] = OrderedDict()
    counts["open_total"] = _get_exact_count(client, table, where_qs="status=eq.open")

    for tier in ("green", "yellow", "orange", "red"):
        counts[f"open_{tier}"] = _get_exact_count(
            client, table, where_qs=f"status=eq.open&freshness_tier=eq.{tier}"
        )

    counts["closed_total"] = _get_exact_count(client, table, where_qs="status=eq.closed")
    counts["expired_total"] = _get_exact_count(client, table, where_qs="status=eq.expired")

    print({"ok": True, "counts": counts})


if __name__ == "__main__":
    main()
