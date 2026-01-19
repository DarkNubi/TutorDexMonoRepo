"""
Backfill `subjects_canonical` / `subjects_general` for existing assignments using taxonomy v2.

Why:
- The website/backend filter and matching now use stable subject codes.
- Older rows may have only `signals_subjects` (labels) and no taxonomy arrays.

Usage:
  python utilities/backfill_subjects_taxonomy_v2.py --limit 500
  python utilities/backfill_subjects_taxonomy_v2.py --limit 2000 --status open
  python utilities/backfill_subjects_taxonomy_v2.py --limit 500 --dry-run

Env (same as supabase_persist):
  SUPABASE_ENABLED=1
  SUPABASE_URL_HOST=... (host Python) and/or SUPABASE_URL_DOCKER=... (Docker)
  SUPABASE_URL=... (fallback)
  SUPABASE_SERVICE_ROLE_KEY=...
  SUPABASE_ASSIGNMENTS_TABLE=assignments (optional)
  SUBJECT_TAXONOMY_DEBUG=1 (optional; includes canonicalization_debug jsonb)
"""

import argparse
import logging
import sys
from typing import Any, Dict, List, Optional, Tuple

from pathlib import Path

from shared.config import load_aggregator_config

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
if str(PARENT) not in sys.path:
    sys.path.insert(0, str(PARENT))

from logging_setup import log_event, setup_logging  # noqa: E402
from supabase_persist import SupabaseRestClient, SupabaseConfig, load_config_from_env  # noqa: E402
from taxonomy.canonicalize_subjects import canonicalize_subjects  # noqa: E402

setup_logging()
logger = logging.getLogger("backfill_subjects_taxonomy_v2")


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


def _first_non_empty(items: Any) -> Optional[str]:
    if items is None:
        return None
    if isinstance(items, str):
        s = items.strip()
        return s or None
    if isinstance(items, (list, tuple)):
        for x in items:
            s = _first_non_empty(x)
            if s:
                return s
        return None
    s = str(items).strip()
    return s or None


def fetch_candidates(client: SupabaseRestClient, *, table: str, status: str, limit: int) -> List[Dict[str, Any]]:
    # Prefer rows missing v2 arrays or version.
    query = (
        f"{table}"
        "?select=id,external_id,agency_telegram_channel_name,status,last_seen,signals_levels,signals_subjects,subjects_canonical,subjects_general,canonicalization_version,meta"
        f"&status=eq.{status}"
        "&or=(canonicalization_version.is.null,subjects_canonical.eq.{},subjects_general.eq.{})"
        "&order=last_seen.desc"
        f"&limit={int(limit)}"
    )
    resp = client.get(query, timeout=30)
    if resp.status_code >= 400:
        raise RuntimeError(f"fetch_failed status={resp.status_code} body={resp.text[:400]}")
    return _coerce_rows(resp)


def patch_row(
    client: SupabaseRestClient,
    *,
    table: str,
    row_id: int,
    subjects_canonical: List[str],
    subjects_general: List[str],
    canonicalization_version: int,
    canonicalization_debug: Optional[Dict[str, Any]],
) -> None:
    body: Dict[str, Any] = {
        "subjects_canonical": subjects_canonical,
        "subjects_general": subjects_general,
        "canonicalization_version": int(canonicalization_version),
    }
    if canonicalization_debug and bool(load_aggregator_config().subject_taxonomy_debug):
        body["canonicalization_debug"] = canonicalization_debug
    resp = client.patch(f"{table}?id=eq.{int(row_id)}", body, timeout=20, prefer="return=minimal")
    if resp.status_code >= 400:
        raise RuntimeError(f"patch_failed id={row_id} status={resp.status_code} body={resp.text[:400]}")


def _derive_inputs(row: Dict[str, Any]) -> Tuple[Optional[str], List[str], Dict[str, Any]]:
    meta = row.get("meta") if isinstance(row.get("meta"), dict) else {}
    src_mapped = meta.get("source_mapped") if isinstance(meta.get("source_mapped"), dict) else None
    if src_mapped:
        lvl = _first_non_empty(src_mapped.get("level"))
        subs_raw = src_mapped.get("subjects")
        if isinstance(subs_raw, list):
            subs = [str(s).strip() for s in subs_raw if str(s).strip()]
        else:
            subs = [str(subs_raw).strip()] if str(subs_raw or "").strip() else []
        dbg = {"source": "meta.source_mapped", "level": lvl, "subjects": subs}
        return lvl, subs, dbg

    levels = row.get("signals_levels")
    lvl = _first_non_empty(levels)
    subs = row.get("signals_subjects") or []
    if isinstance(subs, list):
        subjects = [str(s).strip() for s in subs if str(s).strip()]
    else:
        subjects = [str(subs).strip()] if str(subs or "").strip() else []
    dbg = {"source": "signals_*", "level": lvl, "subjects": subjects}
    return lvl, subjects, dbg


def main() -> None:
    p = argparse.ArgumentParser(description="Backfill subjects taxonomy v2 columns on assignments")
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
        if row_id is None:
            skipped += 1
            continue

        lvl, subjects, input_dbg = _derive_inputs(r)
        if not subjects:
            skipped += 1
            continue

        res = canonicalize_subjects(level=lvl, subjects=subjects)
        canon = res.get("subjects_canonical") or []
        general = res.get("subjects_general") or []
        ver = int(res.get("canonicalization_version") or 2)
        dbg = res.get("debug") if isinstance(res.get("debug"), dict) else {}
        dbg = {"input": input_dbg, **dbg}

        if args.dry_run:
            updated += 1
            log_event(
                logger,
                logging.INFO,
                "backfill_dry_run_update",
                id=row_id,
                external_id=r.get("external_id"),
                subjects_canonical=canon,
                subjects_general=general,
                canonicalization_version=ver,
            )
            continue

        try:
            patch_row(
                client,
                table=table,
                row_id=int(row_id),
                subjects_canonical=list(canon),
                subjects_general=list(general),
                canonicalization_version=ver,
                canonicalization_debug=dbg,
            )
            updated += 1
        except Exception as e:
            failed += 1
            log_event(logger, logging.WARNING, "backfill_patch_failed", id=row_id, error=str(e))

    log_event(logger, logging.INFO, "backfill_done", updated=updated, skipped=skipped, failed=failed, dry_run=bool(args.dry_run))


if __name__ == "__main__":
    main()
