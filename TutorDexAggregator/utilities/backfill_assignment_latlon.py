"""
Backfill assignment `postal_lat`/`postal_lon` in Supabase for rows that already have a SG postal code.

Why:
- Older rows may have `postal_code` but missing `postal_lat/postal_lon` (schema added later, or geocode was disabled).
- Website distance display + nearest sorting require assignment coords to compute distance.

Usage:
  python utilities/backfill_assignment_latlon.py --limit 500
  python utilities/backfill_assignment_latlon.py --limit 2000 --status open
  python utilities/backfill_assignment_latlon.py --limit 200 --dry-run

Env (same as supabase_persist):
  SUPABASE_ENABLED=1
  SUPABASE_URL=...
  SUPABASE_SERVICE_ROLE_KEY=...
  SUPABASE_ASSIGNMENTS_TABLE=assignments (optional)
  DISABLE_NOMINATIM=1 (optional; if set, geocoding will be skipped and this script will do nothing)
  NOMINATIM_USER_AGENT=... (recommended)
"""

import argparse
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from pathlib import Path

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from logging_setup import log_event, setup_logging
from supabase_persist import SupabaseRestClient, SupabaseConfig, load_config_from_env, _geocode_sg_postal, _normalize_sg_postal_code

setup_logging()
logger = logging.getLogger("backfill_assignment_latlon")


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
        "?select=id,external_id,agency_name,postal_code,postal_lat,postal_lon,status,last_seen"
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
        raise SystemExit("SUPABASE is disabled/misconfigured (set SUPABASE_ENABLED, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY).")

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
            coords = _geocode_sg_postal(pc)
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
                agency_name=r.get("agency_name"),
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

