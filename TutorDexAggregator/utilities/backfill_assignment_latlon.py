"""
Backfill assignment `postal_lat`/`postal_lon` in Supabase for rows that already have a SG postal code.

Why:
- Older rows may have `postal_code` but missing `postal_lat/postal_lon` (schema added later, or geocode was disabled).
- Website distance display + nearest sorting require assignment coords to compute distance.

Usage:
  python utilities/backfill_assignment_latlon.py --limit 500
  python utilities/backfill_assignment_latlon.py --limit 2000 --status open
  python utilities/backfill_assignment_latlon.py --limit 200 --dry-run
  python utilities/backfill_assignment_latlon.py --limit 500 --force-nominatim

Env (same as supabase_persist):
  SUPABASE_ENABLED=1
  SUPABASE_URL_HOST=... (host Python) and/or SUPABASE_URL_DOCKER=... (Docker)
  SUPABASE_URL=... (fallback)
  SUPABASE_SERVICE_ROLE_KEY=...
  SUPABASE_ASSIGNMENTS_TABLE=assignments (optional)
  DISABLE_NOMINATIM=1 (optional; if set, geocoding is skipped unless --force-nominatim is used)
  NOMINATIM_USER_AGENT=... (recommended)
"""

import argparse
import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

import requests

from pathlib import Path

from shared.config import load_aggregator_config

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from logging_setup import log_event, setup_logging
from supabase_persist import SupabaseRestClient, SupabaseConfig, load_config_from_env, _geocode_sg_postal, _normalize_sg_postal_code

setup_logging()
logger = logging.getLogger("backfill_assignment_latlon")

def _geocode_sg_postal_force(postal_code: str, *, timeout: int = 10) -> Optional[Tuple[float, float]]:
    pc = _normalize_sg_postal_code(postal_code)
    if not pc:
        return None
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": f"Singapore {pc}", "format": "jsonv2", "limit": 1, "countrycodes": "sg"}
    headers = {"User-Agent": (str(load_aggregator_config().nominatim_user_agent or "").strip() or "TutorDexAggregator/1.0")}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    except Exception:
        return None
    if resp.status_code >= 400:
        return None
    try:
        data = resp.json()
    except Exception:
        return None
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None
    try:
        return (float(data[0].get("lat")), float(data[0].get("lon")))
    except Exception:
        return None


def _coerce_rows(resp) -> List[Dict[str, Any]]:
    try:
        data = resp.json()
    except Exception:
        return []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def fetch_candidates(client: SupabaseRestClient, *, table: str, status: str, limit: int) -> List[Dict[str, Any]]:
    # Only rows with postal_code and missing lat/lon.
    # Use PostgREST filter syntax.
    query = (
        f"{table}"
        "?select=id,external_id,agency_telegram_channel_name,postal_code,postal_lat,postal_lon,status,last_seen"
        f"&status=eq.{status}"
        "&postal_code=not.is.null"
        "&or=(postal_lat.is.null,postal_lon.is.null)"
        "&order=last_seen.desc"
        f"&limit={int(limit)}"
    )
    resp = client.get(query, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"fetch_failed status={resp.status_code} body={resp.text[:400]}")
    return _coerce_rows(resp)


def patch_row(client: SupabaseRestClient, *, table: str, row_id: int, lat: float, lon: float) -> None:
    body = {"postal_lat": float(lat), "postal_lon": float(lon)}
    resp = client.patch(f"{table}?id=eq.{int(row_id)}", body, timeout=20, prefer="return=minimal")
    if resp.status_code >= 400:
        raise RuntimeError(f"patch_failed id={row_id} status={resp.status_code} body={resp.text[:400]}")


def main() -> None:
    p = argparse.ArgumentParser(description="Backfill assignment postal_lat/postal_lon from postal_code")
    p.add_argument("--limit", type=int, default=500, help="Max rows to process per run")
    p.add_argument("--status", type=str, default="open", help="Assignment status filter (default: open)")
    p.add_argument("--dry-run", action="store_true", help="Log what would be updated without writing")
    p.add_argument(
        "--force-nominatim",
        action="store_true",
        help="Geocode even if DISABLE_NOMINATIM is set (uses Nominatim directly in this script).",
    )
    args = p.parse_args()

    base_cfg = load_config_from_env()
    cfg = SupabaseConfig(
        url=base_cfg.url,
        key=base_cfg.key,
        assignments_table=base_cfg.assignments_table,
        enabled=base_cfg.enabled,
        bump_min_seconds=base_cfg.bump_min_seconds,
    )
    if not cfg.enabled:
        raise SystemExit(
            "SUPABASE is disabled/misconfigured (set SUPABASE_ENABLED, SUPABASE_SERVICE_ROLE_KEY, and one of SUPABASE_URL_HOST / SUPABASE_URL_DOCKER / SUPABASE_URL)."
        )

    client = SupabaseRestClient(cfg)
    table = cfg.assignments_table or "assignments"
    status = (args.status or "open").strip()
    limit = max(1, int(args.limit))

    rows = fetch_candidates(client, table=table, status=status, limit=limit)
    log_event(logger, logging.INFO, "backfill_candidates", count=len(rows), status=status, limit=limit, dry_run=bool(args.dry_run))
    if not rows:
        return

    updated = 0
    skipped = 0
    failed = 0

    for r in rows:
        row_id = r.get("id")
        postal_code = r.get("postal_code")
        if row_id is None:
            skipped += 1
            continue
        pc = _normalize_sg_postal_code(postal_code)
        if not pc:
            skipped += 1
            continue
        coords: Optional[Tuple[float, float]] = None
        try:
            coords = _geocode_sg_postal_force(pc) if args.force_nominatim else _geocode_sg_postal(pc)
        except Exception:
            coords = None
        if not coords:
            failed += 1
            log_event(
                logger,
                logging.INFO,
                "backfill_geocode_failed",
                id=row_id,
                external_id=r.get("external_id"),
                agency_telegram_channel_name=r.get("agency_telegram_channel_name"),
                postal_code=str(pc),
            )
            continue

        lat, lon = coords
        if args.dry_run:
            updated += 1
            log_event(
                logger,
                logging.INFO,
                "backfill_dry_run_update",
                id=row_id,
                external_id=r.get("external_id"),
                postal_code=str(pc),
                postal_lat=float(lat),
                postal_lon=float(lon),
            )
            continue

        try:
            patch_row(client, table=table, row_id=int(row_id), lat=lat, lon=lon)
            updated += 1
        except Exception as e:
            failed += 1
            log_event(logger, logging.WARNING, "backfill_patch_failed", id=row_id, error=str(e))

    log_event(
        logger,
        logging.INFO,
        "backfill_done",
        updated=updated,
        skipped=skipped,
        failed=failed,
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    main()
