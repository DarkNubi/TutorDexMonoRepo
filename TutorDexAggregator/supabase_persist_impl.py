import os
import logging
from dataclasses import dataclass
from typing import Any, Dict, Optional
from datetime import datetime, timezone

import requests
from shared.config import load_aggregator_config
from shared.supabase_client import SupabaseClient, SupabaseConfig as ClientConfig, coerce_rows

try:
    # Running from `TutorDexAggregator/` with that folder on sys.path.
    from logging_setup import bind_log_context, log_event, setup_logging, timed  # type: ignore
    from utils.timestamp_utils import utc_now_iso, parse_iso_dt, max_iso_ts  # type: ignore
    from utils.field_coercion import truthy, safe_str  # type: ignore
    from services.row_builder import build_assignment_row  # type: ignore
    from services.merge_policy import merge_patch_body  # type: ignore
    from services.persistence_operations import upsert_agency  # type: ignore
    from services.geocoding_service import geocode_sg_postal  # type: ignore
    from services.event_publisher import should_run_duplicate_detection, run_duplicate_detection_async  # type: ignore
    from utils.field_coercion import normalize_sg_postal_code  # type: ignore
except Exception:
    # Imported as `TutorDexAggregator.*` from repo root (e.g., unit tests).
    from TutorDexAggregator.logging_setup import bind_log_context, log_event, setup_logging, timed  # type: ignore
    from TutorDexAggregator.utils.timestamp_utils import utc_now_iso, parse_iso_dt, max_iso_ts  # type: ignore
    from TutorDexAggregator.utils.field_coercion import truthy, safe_str  # type: ignore
    from TutorDexAggregator.services.row_builder import build_assignment_row  # type: ignore
    from TutorDexAggregator.services.merge_policy import merge_patch_body  # type: ignore
    from TutorDexAggregator.services.persistence_operations import upsert_agency  # type: ignore
    from TutorDexAggregator.services.geocoding_service import geocode_sg_postal  # type: ignore
    from TutorDexAggregator.services.event_publisher import should_run_duplicate_detection, run_duplicate_detection_async  # type: ignore
    from TutorDexAggregator.utils.field_coercion import normalize_sg_postal_code  # type: ignore

setup_logging()
logger = logging.getLogger("supabase_persist")
_CFG = load_aggregator_config()

try:
    from observability_metrics import worker_supabase_fail_total, versions as _obs_versions  # type: ignore
except Exception:
    worker_supabase_fail_total = None  # type: ignore
    _obs_versions = None  # type: ignore


def _normalize_sg_postal_code(postal_code: str) -> str:
    """Compatibility shim for legacy callers/tests."""
    return str(normalize_sg_postal_code(postal_code) or "").strip()


def _geocode_sg_postal(postal_code: str, *, timeout: int = 10):
    """Compatibility shim for legacy callers/tests."""
    return geocode_sg_postal(postal_code, timeout=timeout)


def _build_assignment_row(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Compatibility shim for legacy callers/tests."""
    return build_assignment_row(payload, geocode_func=_geocode_sg_postal)


def _merge_patch_body(*, existing: Dict[str, Any], incoming_row: Dict[str, Any], force_upgrade: bool = False) -> Dict[str, Any]:
    """Compatibility shim for legacy callers/tests."""
    return merge_patch_body(existing=existing, incoming_row=incoming_row, force_upgrade=force_upgrade)


@dataclass(frozen=True)
class SupabaseConfig:
    """Configuration for Supabase persistence."""

    url: str
    key: str
    assignments_table: str = "assignments"
    enabled: bool = False
    bump_min_seconds: int = 6 * 60 * 60  # 6 hours
    timeout: int = 30
    max_retries: int = 3

    def to_client_config(self) -> ClientConfig:
        return ClientConfig(
            url=self.url,
            key=self.key,
            timeout=int(self.timeout),
            max_retries=int(self.max_retries),
            enabled=bool(self.enabled),
        )


def load_config_from_env() -> SupabaseConfig:
    url = _CFG.supabase_rest_url
    key = _CFG.supabase_auth_key
    assignments_table = str(_CFG.supabase_assignments_table or "assignments").strip()
    enabled = bool(_CFG.supabase_enabled) and bool(url and key and assignments_table)
    bump_min_seconds = int(_CFG.supabase_bump_min_seconds or (6 * 60 * 60))
    return SupabaseConfig(
        url=url,
        key=key,
        assignments_table=assignments_table,
        enabled=enabled,
        bump_min_seconds=bump_min_seconds,
    )


def SupabaseRestClient(cfg: SupabaseConfig) -> SupabaseClient:
    """Compatibility shim: returns the unified shared Supabase client."""
    return SupabaseClient(cfg.to_client_config())


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

    row = build_assignment_row(payload, geocode_func=geocode_sg_postal)
    external_id = row.get("external_id")
    agency_telegram_channel_name = row.get("agency_telegram_channel_name")
    agency_display_name = row.get("agency_display_name")
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
        if not external_id or not agency_telegram_channel_name:
            res = {
                "ok": False,
                "skipped": True,
                "reason": "missing_external_id_or_agency_telegram_channel_name",
                "external_id": external_id,
                "agency_telegram_channel_name": agency_telegram_channel_name,
            }
            log_event(logger, logging.WARNING, "supabase_skipped", **res)
            return res

        # If the normalized schema exists, try to create/resolve agency_id.
        try:
            t0 = timed()
            agency_id = upsert_agency(
                client,
                agency_display_name=str(agency_display_name) if agency_display_name else None,
                agency_telegram_channel_name=str(agency_telegram_channel_name),
                channel_link=str(agency_link) if agency_link else None,
            )
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
                "agency_display_name",
                "agency_telegram_channel_name",
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
            query += f"&agency_telegram_channel_name=eq.{requests.utils.quote(str(agency_telegram_channel_name), safe='')}"
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
                agency_telegram_channel_name=str(agency_telegram_channel_name),
                error=str(e),
            )
            if worker_supabase_fail_total:
                try:
                    worker_supabase_fail_total.labels(operation="get", pipeline_version=pv, schema_version=sv).inc()
                except Exception:
                    # Metrics must never break runtime
                    pass
            return {"ok": False, "error": str(e)}

        existing_rows = coerce_rows(existing_resp) if existing_resp.status_code < 400 else []
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
                        agency=str(agency_telegram_channel_name),
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
                    # Metrics must never break runtime
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
                    # Metrics must never break runtime
                    pass
                    return {"ok": False, "error": str(e)}
            if not ok:
                log_event(logger, logging.WARNING, "supabase_patch_status", status_code=patch_resp.status_code, body=patch_resp.text[:500])
            res = {"ok": ok, "action": "updated", "status_code": patch_resp.status_code, "get_ms": get_ms, "patch_ms": patch_ms}
            res["total_ms"] = round((timed() - t_all) * 1000.0, 2)
            log_event(logger, logging.INFO if ok else logging.WARNING, "supabase_persist_result", **res)

            # Duplicate detection (after successful update, only if re-extraction occurred)
            if ok and should_run_duplicate_detection():
                run_duplicate_detection_async(existing.get("id"), cfg)

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
            log_event(
                logger,
                logging.ERROR,
                "supabase_insert_failed",
                external_id=str(external_id),
                agency_telegram_channel_name=str(agency_telegram_channel_name),
                error=str(e),
            )
            if worker_supabase_fail_total:
                try:
                    worker_supabase_fail_total.labels(operation="insert", pipeline_version=pv, schema_version=sv).inc()
                except Exception:
                    # Metrics must never break runtime
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
                log_event(
                    logger,
                    logging.ERROR,
                    "supabase_insert_failed",
                    external_id=str(external_id),
                    agency_telegram_channel_name=str(agency_telegram_channel_name),
                    error=str(e),
                )
                if worker_supabase_fail_total:
                    try:
                        worker_supabase_fail_total.labels(operation="insert", pipeline_version=pv, schema_version=sv).inc()
                except Exception:
                    # Metrics must never break runtime
                    pass
                return {"ok": False, "error": str(e)}
        if not ok:
            log_event(logger, logging.WARNING, "supabase_insert_status", status_code=insert_resp.status_code, body=insert_resp.text[:500])
        res = {"ok": ok, "action": "inserted", "status_code": insert_resp.status_code, "get_ms": get_ms, "insert_ms": insert_ms}
        res["total_ms"] = round((timed() - t_all) * 1000.0, 2)
        log_event(logger, logging.INFO if ok else logging.WARNING, "supabase_persist_result", **res)

        # Duplicate detection (after successful insert)
        if ok and should_run_duplicate_detection():
            inserted_rows = coerce_rows(insert_resp) if insert_resp.status_code < 400 else []
            if inserted_rows and inserted_rows[0].get("id"):
                run_duplicate_detection_async(inserted_rows[0]["id"], cfg)

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
        row = build_assignment_row(payload, geocode_func=geocode_sg_postal)
        external_id = row.get("external_id")
        agency_telegram_channel_name = row.get("agency_telegram_channel_name")
        agency_link = row.get("agency_link")
        if not external_id or not agency_telegram_channel_name:
            res = {
                "ok": False,
                "skipped": True,
                "reason": "missing_external_id_or_agency_telegram_channel_name",
                "external_id": external_id,
                "agency_telegram_channel_name": agency_telegram_channel_name,
            }
            log_event(logger, logging.DEBUG, "supabase_close_skipped", **res)
            return res

        query = f"{cfg.assignments_table}?select=id,status,last_seen&external_id=eq.{requests.utils.quote(str(external_id), safe='')}"
        if row.get("agency_id") is not None:
            query += f"&agency_id=eq.{int(row['agency_id'])}"
        else:
            query += f"&agency_telegram_channel_name=eq.{requests.utils.quote(str(agency_telegram_channel_name), safe='')}"
        query += "&limit=1"

        try:
            existing_resp = client.get(query, timeout=10)
            existing_rows = coerce_rows(existing_resp) if existing_resp.status_code < 400 else []
        except Exception as e:
            log_event(logger, logging.WARNING, "supabase_close_lookup_failed", error=str(e))
            return {"ok": False, "error": str(e), "action": "lookup_failed"}

        if not existing_rows:
            log_event(
                logger,
                logging.INFO,
                "supabase_close_not_found",
                external_id=external_id,
                agency_telegram_channel_name=agency_telegram_channel_name,
            )
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
