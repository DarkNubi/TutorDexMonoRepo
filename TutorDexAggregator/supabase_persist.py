import os
import logging
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple, List
import json
import hashlib

import requests

try:
    # Running from `TutorDexAggregator/` with that folder on sys.path.
    from logging_setup import bind_log_context, log_event, setup_logging, timed  # type: ignore
    from utils.timestamp_utils import utc_now_iso, parse_iso_dt, max_iso_ts  # type: ignore
    from utils.field_coercion import truthy, safe_str, coerce_text_list  # type: ignore
    from utils.supabase_client import (  # type: ignore
        SupabaseConfig, load_config_from_env, SupabaseRestClient, coerce_rows
    )
    from services.row_builder import build_assignment_row, compute_parse_quality  # type: ignore
    from services.merge_policy import merge_patch_body  # type: ignore
except Exception:
    # Imported as `TutorDexAggregator.*` from repo root (e.g., unit tests).
    from TutorDexAggregator.logging_setup import bind_log_context, log_event, setup_logging, timed  # type: ignore
    from TutorDexAggregator.utils.timestamp_utils import utc_now_iso, parse_iso_dt, max_iso_ts  # type: ignore
    from TutorDexAggregator.utils.field_coercion import truthy, safe_str, coerce_text_list  # type: ignore
    from TutorDexAggregator.utils.supabase_client import (  # type: ignore
        SupabaseConfig, load_config_from_env, SupabaseRestClient, coerce_rows
    )
    from TutorDexAggregator.services.row_builder import build_assignment_row, compute_parse_quality  # type: ignore
    from TutorDexAggregator.services.merge_policy import merge_patch_body  # type: ignore

setup_logging()
logger = logging.getLogger("supabase_persist")

try:
    from observability_metrics import worker_supabase_fail_total, versions as _obs_versions  # type: ignore
except Exception:
    worker_supabase_fail_total = None  # type: ignore
    _obs_versions = None  # type: ignore


# Duplicate detection integration
def _should_run_duplicate_detection() -> bool:
    """Check if duplicate detection should run (environment variable)"""
    return truthy(os.environ.get("DUPLICATE_DETECTION_ENABLED"))


def _run_duplicate_detection_async(assignment_id: int, cfg: "SupabaseConfig"):
    """
    Run duplicate detection asynchronously (non-blocking)
    
    This runs in a separate thread to avoid blocking the main persist operation.
    Failures in duplicate detection do not affect assignment persistence.
    """
    import threading
    
    def _detect():
        try:
            from duplicate_detector import detect_duplicates_for_assignment  # type: ignore
            
            group_id = detect_duplicates_for_assignment(
                assignment_id,
                supabase_url=cfg.url,
                supabase_key=cfg.key
            )
            
            if group_id:
                logger.info(
                    f"Duplicate detection completed for assignment {assignment_id}",
                    extra={"assignment_id": assignment_id, "duplicate_group_id": group_id}
                )
            else:
                logger.debug(
                    f"No duplicates found for assignment {assignment_id}",
                    extra={"assignment_id": assignment_id}
                )
        except Exception as e:
            logger.warning(
                f"Duplicate detection failed for assignment {assignment_id}: {e}",
                extra={"assignment_id": assignment_id, "error": str(e)}
            )
    
    # Run in background thread (non-blocking)
    thread = threading.Thread(target=_detect, daemon=True)
    thread.start()



def _freshness_enabled() -> bool:
    """Check if freshness tier feature is enabled."""
    return truthy(os.environ.get("FRESHNESS_TIER_ENABLED"))


def _nominatim_disabled() -> bool:
    """Check if Nominatim geocoding is disabled."""
    return truthy(os.environ.get("DISABLE_NOMINATIM"))


@lru_cache(maxsize=2048)
def _geocode_sg_postal(postal_code: str, *, timeout: int = 10) -> Optional[Tuple[float, float]]:
    """
    Geocode Singapore postal code using Nominatim API.
    
    Returns (lat, lon) tuple or None if geocoding fails.
    Caches results to avoid repeated API calls.
    """
    if _nominatim_disabled():
        return None
    pc = normalize_sg_postal_code(postal_code)
    if not pc:
        return None

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": f"Singapore {pc}", "format": "jsonv2", "limit": 1, "countrycodes": "sg"}
    headers = {"User-Agent": os.environ.get("NOMINATIM_USER_AGENT") or "TutorDexAggregator/1.0"}

    max_attempts = int(os.environ.get("NOMINATIM_RETRIES") or "3")
    backoff_s = float(os.environ.get("NOMINATIM_BACKOFF_SECONDS") or "1.0")

    resp = None
    for attempt in range(max(1, min(max_attempts, 6))):
        try:
            resp = requests.get(url, params=params, headers=headers, timeout=timeout)
        except Exception:
            logger.debug("postal_geocode_failed", exc_info=True)
            resp = None

        if resp is None:
            # transient network issue
            if attempt < max_attempts - 1:
                try:
                    import time
                    time.sleep(min(10.0, backoff_s * (2**attempt)))
                except Exception:
                    pass
            continue

        if resp.status_code in {429, 503} and attempt < max_attempts - 1:
            try:
                import time
                time.sleep(min(10.0, backoff_s * (2**attempt)))
            except Exception:
                pass
            continue

        if resp.status_code >= 400:
            return None
        break

    if resp is None:
        return None

    try:
        data = resp.json()
    except Exception:
        return None
    if not isinstance(data, list) or not data or not isinstance(data[0], dict):
        return None

    try:
        lat = float(data[0].get("lat"))
        lon = float(data[0].get("lon"))
        return (lat, lon)
    except Exception:
        return None


# Imported from services.row_builder: compute_parse_quality, derive_agency, derive_external_id, build_assignment_row


# Imported from services.merge_policy: merge_patch_body







def _upsert_agency(client: SupabaseRestClient, *, name: str, channel_link: Optional[str]) -> Optional[int]:
    """
    Find or create agency by name/channel_link.
    
    Returns agency_id or None if operation fails.
    """
    if not name:
        return None

    # Try lookup by channel_link first (if present), else by name.
    if channel_link:
        q = f"agencies?select=id&channel_link=eq.{requests.utils.quote(channel_link, safe='')}&limit=1"
        try:
            r = client.get(q, timeout=15)
            if r.status_code < 400:
                rows = coerce_rows(r)
                if rows:
                    return rows[0].get("id")
        except Exception:
            logger.debug("Agency lookup by channel_link failed", exc_info=True)

    q2 = f"agencies?select=id&name=eq.{requests.utils.quote(name, safe='')}&limit=1"
    try:
        r2 = client.get(q2, timeout=15)
        if r2.status_code < 400:
            rows = coerce_rows(r2)
            if rows:
                return rows[0].get("id")
    except Exception:
        logger.debug("Agency lookup by name failed", exc_info=True)

    try:
        ins = client.post(
            "agencies",
            [{"name": name, "channel_link": channel_link}],
            timeout=20,
            prefer="return=representation",
        )
        if ins.status_code < 400:
            rows = coerce_rows(ins)
            if rows:
                return rows[0].get("id")
    except Exception:
        logger.debug("Agency insert failed", exc_info=True)
        return None
    return None


def persist_assignment_to_supabase(payload: Dict[str, Any], *, cfg: Optional[SupabaseConfig] = None) -> Dict[str, Any]:
    cfg = cfg or load_config_from_env()
    if not cfg.enabled:
        return {"ok": False, "skipped": True, "reason": "supabase_disabled"}

    cid = payload.get("cid") or "<no-cid>"
    msg_id = payload.get("message_id")
    channel = payload.get("channel_link") or payload.get("channel_username")

    pv = str(payload.get("pipeline_version") or "").strip()
    sv = str(payload.get("schema_version") or "").strip()
    if _obs_versions and not pv:
        pv = _obs_versions().pipeline_version
    if _obs_versions and not sv:
        sv = _obs_versions().schema_version
    pv = pv or "-"
    sv = sv or "-"

    row = build_assignment_row(payload, geocode_func=_geocode_sg_postal)
    external_id = row.get("external_id")
    agency_name = row.get("agency_name")
    agency_link = row.get("agency_link")

    with bind_log_context(
        cid=str(cid),
        message_id=msg_id,
        channel=str(channel) if channel else None,
        assignment_id=str(external_id) if external_id else None,
        step="supabase",
        component="supabase",
        pipeline_version=pv,
        schema_version=sv,
    ):
        t_all = timed()

        client = SupabaseRestClient(cfg)
        if not external_id or not agency_name:
            res = {
                "ok": False,
                "skipped": True,
                "reason": "missing_external_id_or_agency_name",
                "external_id": external_id,
                "agency_name": agency_name,
            }
            log_event(logger, logging.WARNING, "supabase_skipped", **res)
            return res

        # If the normalized schema exists, try to create/resolve agency_id.
        try:
            t0 = timed()
            agency_id = _upsert_agency(client, name=str(agency_name), channel_link=str(agency_link) if agency_link else None)
            agency_ms = round((timed() - t0) * 1000.0, 2)
            if agency_id:
                row["agency_id"] = agency_id
                log_event(logger, logging.DEBUG, "supabase_agency_resolved", agency_id=agency_id, agency_ms=agency_ms)
            else:
                log_event(logger, logging.DEBUG, "supabase_agency_unresolved", agency_ms=agency_ms)
        except Exception:
            logger.debug("Agency upsert failed (continuing without agency_id)", exc_info=True)

        now_iso = utc_now_iso()

        select = ",".join(
            [
                "id",
                "agency_id",
                "external_id",
                "published_at",
                "source_last_seen",
                "last_seen",
                "bump_count",
                "parse_quality_score",
                "message_id",
                "message_link",
                "address",
                "postal_code",
                "nearest_mrt",
                "learning_mode",
                "learning_mode_raw_text",
                "assignment_code",
                "academic_display_text",
                "lesson_schedule",
                "start_date",
                "time_availability_note",
                "time_availability_explicit",
                "time_availability_estimated",
                "rate_min",
                "rate_max",
                "rate_raw_text",
                "tutor_types",
                "rate_breakdown",
                "additional_remarks",
                "signals_subjects",
                "signals_levels",
                "signals_specific_student_levels",
                "signals_streams",
                "signals_academic_requests",
                "signals_confidence_flags",
                "canonical_json",
                "meta",
                "status",
            ]
        )
        query = f"{cfg.assignments_table}?select={select}&external_id=eq.{requests.utils.quote(str(external_id), safe='')}"
        if row.get("agency_id") is not None:
            query += f"&agency_id=eq.{int(row['agency_id'])}"
        else:
            query += f"&agency_name=eq.{requests.utils.quote(str(agency_name), safe='')}"
        query += "&limit=1"

        try:
            t0 = timed()
            existing_resp = client.get(query, timeout=15)
            get_ms = round((timed() - t0) * 1000.0, 2)
        except Exception as e:
            log_event(
                logger,
                logging.ERROR,
                "supabase_get_failed",
                external_id=str(external_id),
                agency_name=str(agency_name),
                error=str(e),
            )
            if worker_supabase_fail_total:
                try:
                    worker_supabase_fail_total.labels(operation="get", pipeline_version=pv, schema_version=sv).inc()
                except Exception:
                    pass
            return {"ok": False, "error": str(e)}

        existing_rows = _coerce_rows(existing_resp) if existing_resp.status_code < 400 else []
        if existing_rows:
            existing = existing_rows[0]
            last_seen = parse_iso_dt(existing.get("last_seen"))
            bump_count = int(existing.get("bump_count") or 0)
            existing_source_last_seen = safe_str(existing.get("source_last_seen"))
            source_type = str(payload.get("source_type") or "").strip().lower()
            tutorcity_changed = False
            if source_type == "tutorcity_api":
                try:
                    prev_meta = existing.get("meta") if isinstance(existing.get("meta"), dict) else None
                    prev_fp = safe_str(prev_meta.get("tutorcity_fingerprint")) if isinstance(prev_meta, dict) else None
                    incoming_meta = row.get("meta") if isinstance(row.get("meta"), dict) else None
                    incoming_fp = safe_str(incoming_meta.get("tutorcity_fingerprint")) if isinstance(incoming_meta, dict) else None
                    tutorcity_changed = bool(incoming_fp and incoming_fp != prev_fp)
                except Exception:
                    tutorcity_changed = False

            should_bump = True
            if last_seen:
                elapsed = (datetime.now(timezone.utc) - last_seen.astimezone(timezone.utc)).total_seconds()
                should_bump = elapsed >= cfg.bump_min_seconds
                if not should_bump:
                    log_event(
                        logger,
                        logging.DEBUG,
                        "supabase_bump_suppressed",
                        external_id=str(external_id),
                        agency=str(agency_name),
                        last_seen=existing.get("last_seen"),
                        elapsed_s=round(elapsed, 2),
                        min_seconds=cfg.bump_min_seconds,
                    )

            patch_body: Dict[str, Any] = {"last_seen": now_iso}
            if should_bump:
                patch_body["bump_count"] = bump_count + 1

            patch_body.update(merge_patch_body(existing=existing, incoming_row=row, force_upgrade=bool(tutorcity_changed)))

            # `source_last_seen` = last upstream bump/edit/repost.
            # - For Telegram: keep monotonic based on upstream timestamp (edit_date).
            # - For TutorCity API: only update when the upstream payload fingerprint changed (true update),
            #   so polling doesn't continuously bump freshness.
            incoming_source_last_seen = safe_str(row.get("source_last_seen"))
            if source_type == "tutorcity_api":
                if tutorcity_changed:
                    patch_body["source_last_seen"] = now_iso
                else:
                    patch_body["source_last_seen"] = existing_source_last_seen
            else:
                patch_body["source_last_seen"] = max_iso_ts(existing_source_last_seen, incoming_source_last_seen) or existing_source_last_seen
            if patch_body.get("source_last_seen") is None:
                patch_body.pop("source_last_seen", None)

            try:
                t0 = timed()
                patch_resp = client.patch(
                    f"{cfg.assignments_table}?id=eq.{existing.get('id')}",
                    patch_body,
                    timeout=20,
                    prefer="return=representation",
                )
                patch_ms = round((timed() - t0) * 1000.0, 2)
            except Exception as e:
                log_event(logger, logging.ERROR, "supabase_patch_failed", row_id=existing.get("id"), error=str(e))
                if worker_supabase_fail_total:
                    try:
                        worker_supabase_fail_total.labels(operation="patch", pipeline_version=pv, schema_version=sv).inc()
                    except Exception:
                        pass
                return {"ok": False, "error": str(e)}

            ok = patch_resp.status_code < 400
            if not ok and patch_resp.status_code == 400 and ("PGRST204" in patch_resp.text or "schema cache" in patch_resp.text):
                patch_body.pop("postal_lat", None)
                patch_body.pop("postal_lon", None)
                patch_body.pop("subjects_canonical", None)
                patch_body.pop("subjects_general", None)
                patch_body.pop("canonicalization_version", None)
                patch_body.pop("canonicalization_debug", None)
                patch_body.pop("published_at", None)
                patch_body.pop("source_last_seen", None)
                try:
                    t0 = timed()
                    patch_resp = client.patch(
                        f"{cfg.assignments_table}?id=eq.{existing.get('id')}",
                        patch_body,
                        timeout=20,
                        prefer="return=representation",
                    )
                    patch_ms = round((timed() - t0) * 1000.0, 2)
                    ok = patch_resp.status_code < 400
                except Exception as e:
                    log_event(logger, logging.ERROR, "supabase_patch_failed", row_id=existing.get("id"), error=str(e))
                    if worker_supabase_fail_total:
                        try:
                            worker_supabase_fail_total.labels(operation="patch", pipeline_version=pv, schema_version=sv).inc()
                        except Exception:
                            pass
                    return {"ok": False, "error": str(e)}
            if not ok:
                log_event(logger, logging.WARNING, "supabase_patch_status", status_code=patch_resp.status_code, body=patch_resp.text[:500])
            res = {"ok": ok, "action": "updated", "status_code": patch_resp.status_code, "get_ms": get_ms, "patch_ms": patch_ms}
            res["total_ms"] = round((timed() - t_all) * 1000.0, 2)
            log_event(logger, logging.INFO if ok else logging.WARNING, "supabase_persist_result", **res)
            
            # Duplicate detection (after successful update, only if re-extraction occurred)
            if ok and _should_run_duplicate_detection():
                _run_duplicate_detection_async(existing.get("id"), cfg)
            
            return res

        row_to_insert = dict(row)
        row_to_insert["last_seen"] = now_iso
        row_to_insert.setdefault("published_at", now_iso)
        row_to_insert.setdefault("source_last_seen", row_to_insert.get("published_at") or now_iso)
        row_to_insert.setdefault("bump_count", 0)
        row_to_insert.setdefault("status", "open")

        try:
            t0 = timed()
            insert_resp = client.post(
                cfg.assignments_table,
                [row_to_insert],
                timeout=20,
                prefer="return=representation",
            )
            insert_ms = round((timed() - t0) * 1000.0, 2)
        except Exception as e:
            log_event(logger, logging.ERROR, "supabase_insert_failed", external_id=str(external_id), agency_name=str(agency_name), error=str(e))
            if worker_supabase_fail_total:
                try:
                    worker_supabase_fail_total.labels(operation="insert", pipeline_version=pv, schema_version=sv).inc()
                except Exception:
                    pass
            return {"ok": False, "error": str(e)}

        ok = insert_resp.status_code < 400
        if not ok and insert_resp.status_code == 400 and ("PGRST204" in insert_resp.text or "schema cache" in insert_resp.text):
            row_to_insert.pop("postal_lat", None)
            row_to_insert.pop("postal_lon", None)
            row_to_insert.pop("subjects_canonical", None)
            row_to_insert.pop("subjects_general", None)
            row_to_insert.pop("canonicalization_version", None)
            row_to_insert.pop("canonicalization_debug", None)
            row_to_insert.pop("published_at", None)
            row_to_insert.pop("source_last_seen", None)
            try:
                t0 = timed()
                insert_resp = client.post(
                    cfg.assignments_table,
                    [row_to_insert],
                    timeout=20,
                    prefer="return=representation",
                )
                insert_ms = round((timed() - t0) * 1000.0, 2)
                ok = insert_resp.status_code < 400
            except Exception as e:
                log_event(logger, logging.ERROR, "supabase_insert_failed", external_id=str(external_id), agency_name=str(agency_name), error=str(e))
                if worker_supabase_fail_total:
                    try:
                        worker_supabase_fail_total.labels(operation="insert", pipeline_version=pv, schema_version=sv).inc()
                    except Exception:
                        pass
                return {"ok": False, "error": str(e)}
        if not ok:
            log_event(logger, logging.WARNING, "supabase_insert_status", status_code=insert_resp.status_code, body=insert_resp.text[:500])
        res = {"ok": ok, "action": "inserted", "status_code": insert_resp.status_code, "get_ms": get_ms, "insert_ms": insert_ms}
        res["total_ms"] = round((timed() - t_all) * 1000.0, 2)
        log_event(logger, logging.INFO if ok else logging.WARNING, "supabase_persist_result", **res)
        
        # Duplicate detection (after successful insert)
        if ok and _should_run_duplicate_detection():
            inserted_rows = _coerce_rows(insert_resp) if insert_resp.status_code < 400 else []
            if inserted_rows and inserted_rows[0].get("id"):
                _run_duplicate_detection_async(inserted_rows[0]["id"], cfg)
        
        return res


def mark_assignment_closed(payload: Dict[str, Any], *, cfg: Optional[SupabaseConfig] = None) -> Dict[str, Any]:
    """
    Best-effort close of an assignment when we observe a Telegram delete.
    Uses the same external_id derivation as normal persistence to avoid schema drift.
    """
    cfg = cfg or load_config_from_env()
    if not cfg.enabled:
        return {"ok": False, "skipped": True, "reason": "supabase_disabled"}

    cid = payload.get("cid") or "<no-cid>"
    msg_id = payload.get("message_id")
    channel = payload.get("channel_link") or payload.get("channel_username")

    with bind_log_context(cid=str(cid), message_id=msg_id, channel=str(channel) if channel else None, step="supabase.close"):
        client = SupabaseRestClient(cfg)
        row = build_assignment_row(payload, geocode_func=_geocode_sg_postal)
        external_id = row.get("external_id")
        agency_name = row.get("agency_name")
        agency_link = row.get("agency_link")
        if not external_id or not agency_name:
            res = {
                "ok": False,
                "skipped": True,
                "reason": "missing_external_id_or_agency_name",
                "external_id": external_id,
                "agency_name": agency_name,
            }
            log_event(logger, logging.DEBUG, "supabase_close_skipped", **res)
            return res

        query = f"{cfg.assignments_table}?select=id,status,last_seen&external_id=eq.{requests.utils.quote(str(external_id), safe='')}"
        if row.get("agency_id") is not None:
            query += f"&agency_id=eq.{int(row['agency_id'])}"
        else:
            query += f"&agency_name=eq.{requests.utils.quote(str(agency_name), safe='')}"
        query += "&limit=1"

        try:
            existing_resp = client.get(query, timeout=10)
            existing_rows = _coerce_rows(existing_resp) if existing_resp.status_code < 400 else []
        except Exception as e:
            log_event(logger, logging.WARNING, "supabase_close_lookup_failed", error=str(e))
            return {"ok": False, "error": str(e), "action": "lookup_failed"}

        if not existing_rows:
            log_event(logger, logging.INFO, "supabase_close_not_found", external_id=external_id, agency_name=agency_name)
            return {"ok": False, "skipped": True, "reason": "not_found"}

        row_id = existing_rows[0].get("id")
        patch_body = {"status": "closed", "last_seen": utc_now_iso()}

        try:
            patch_resp = client.patch(f"{cfg.assignments_table}?id=eq.{row_id}", patch_body, timeout=10, prefer="return=representation")
            ok = patch_resp.status_code < 400
        except Exception as e:
            log_event(logger, logging.WARNING, "supabase_close_failed", row_id=row_id, error=str(e))
            return {"ok": False, "error": str(e), "action": "close_failed"}

        res = {"ok": ok, "action": "closed" if ok else "close_failed", "status_code": patch_resp.status_code if 'patch_resp' in locals() else None}
        log_event(logger, logging.INFO if ok else logging.WARNING, "supabase_close_result", **res)
        return res
