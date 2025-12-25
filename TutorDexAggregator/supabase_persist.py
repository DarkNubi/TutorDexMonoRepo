import os
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Dict, Optional, Tuple, List
import re

import requests

from logging_setup import bind_log_context, log_event, setup_logging, timed
from taxonomy.canonicalize_subjects import (
    canonicalize_subjects_for_assignment_row,
    subject_taxonomy_debug_enabled,
    subject_taxonomy_enabled,
)

setup_logging()
logger = logging.getLogger("supabase_persist")
_SG_POSTAL_RE = re.compile(r"\b(\d{6})\b")


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _freshness_enabled() -> bool:
    return _truthy(os.environ.get("FRESHNESS_TIER_ENABLED"))


def _nominatim_disabled() -> bool:
    return str(os.environ.get("DISABLE_NOMINATIM", "")).strip().lower() in {"1", "true", "yes", "y", "on"}


def _normalize_sg_postal_code(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    if not s:
        return None
    digits = re.sub(r"\D+", "", s)
    m = _SG_POSTAL_RE.search(digits)
    return m.group(1) if m else None


@lru_cache(maxsize=2048)
def _geocode_sg_postal(postal_code: str, *, timeout: int = 10) -> Optional[Tuple[float, float]]:
    if _nominatim_disabled():
        return None
    pc = _normalize_sg_postal_code(postal_code)
    if not pc:
        return None

    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": f"Singapore {pc}", "format": "jsonv2", "limit": 1, "countrycodes": "sg"}
    headers = {"User-Agent": os.environ.get("NOMINATIM_USER_AGENT") or "TutorDexAggregator/1.0"}

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=timeout)
    except Exception:
        logger.debug("postal_geocode_failed", exc_info=True)
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
        lat = float(data[0].get("lat"))
        lon = float(data[0].get("lon"))
        return (lat, lon)
    except Exception:
        return None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    s = str(value).strip()
    try:
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s)
    except Exception:
        return None


def _safe_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _first_text(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            s = _first_text(item)
            if s:
                return s
        return None
    return _safe_str(value)


def _coerce_text_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    if isinstance(value, (list, tuple)):
        out: List[str] = []
        for x in value:
            out.extend(_coerce_text_list(x))
        # de-dup preserve order
        seen = set()
        uniq: List[str] = []
        for t in out:
            s = str(t).strip()
            if not s or s in seen:
                continue
            seen.add(s)
            uniq.append(s)
        return uniq
    v = str(value).strip()
    return [v] if v else []


def _truthy_text(value: Any) -> bool:
    return any(_coerce_text_list(value))


def _compute_parse_quality(row_like: Dict[str, Any]) -> int:
    # Simple heuristic score used to prevent low-quality reposts from overwriting richer data.
    score = 0
    if _truthy_text(row_like.get("subjects")) or _truthy_text(row_like.get("subject")):
        score += 2
    if _truthy_text(row_like.get("level")):
        score += 2
    if _truthy_text(row_like.get("address")) or _truthy_text(row_like.get("postal_code")) or _truthy_text(row_like.get("nearest_mrt")):
        score += 2
    if row_like.get("rate_min") is not None or row_like.get("rate_max") is not None or _truthy_text(row_like.get("hourly_rate")):
        score += 1
    if _truthy_text(row_like.get("frequency")) or _truthy_text(row_like.get("duration")):
        score += 1
    if row_like.get("time_slots") is not None or row_like.get("estimated_time_slots") is not None or _truthy_text(row_like.get("time_slots_note")):
        score += 1
    return int(score)


def _merge_patch_body(*, existing: Dict[str, Any], incoming_row: Dict[str, Any]) -> Dict[str, Any]:
    """
    Conservative merge:
    - Always update latest message pointers (message_id/message_link).
    - Allow filling missing fields.
    - Overwrite more broadly only when parse_quality_score improves.
    """
    old_score = existing.get("parse_quality_score")
    old_score_i = int(old_score) if isinstance(old_score, (int, float)) else _compute_parse_quality(existing)
    new_score_i = int(incoming_row.get("parse_quality_score") or 0)
    upgrade = new_score_i > old_score_i

    patch: Dict[str, Any] = {}

    # Always update "latest seen" identifiers for UI linking/debugging.
    for k in ("message_id", "message_link"):
        if k in incoming_row and incoming_row.get(k) is not None:
            patch[k] = incoming_row[k]

    # Only update heavy/raw blobs when we're upgrading quality.
    if upgrade:
        for k in ("raw_text", "payload_json", "parsed_json"):
            if k in incoming_row and incoming_row.get(k) is not None:
                patch[k] = incoming_row[k]

    for k, v in incoming_row.items():
        if k in {"external_id", "agency_name", "agency_id", "parse_quality_score"}:
            continue
        if v is None:
            continue

        if upgrade:
            patch[k] = v
            continue

        cur = existing.get(k)
        if cur is None:
            patch[k] = v
            continue
        if isinstance(cur, str) and not cur.strip():
            patch[k] = v
            continue
        if isinstance(cur, list) and len(cur) == 0:
            patch[k] = v
            continue

    # Union subjects when not upgrading (preserve + add).
    if not upgrade:
        existing_subjects = _coerce_text_list(existing.get("subjects") or [])
        incoming_subjects = _coerce_text_list(incoming_row.get("subjects") or [])
        if incoming_subjects:
            combined = _coerce_text_list(existing_subjects + incoming_subjects)
            if combined != existing_subjects:
                patch["subjects"] = combined
            if not _truthy_text(existing.get("subject")) and _truthy_text(incoming_row.get("subject")):
                patch["subject"] = incoming_row.get("subject")

    # Union canonical arrays when not upgrading (preserve + add).
    if not upgrade:
        for key in ("subjects_canonical", "subjects_general", "tags"):
            existing_vals = _coerce_text_list(existing.get(key) or [])
            incoming_vals = _coerce_text_list(incoming_row.get(key) or [])
            if incoming_vals:
                combined = _coerce_text_list(existing_vals + incoming_vals)
                if combined != existing_vals:
                    patch[key] = combined

    # Update score to reflect the merged record.
    merged_preview = dict(existing)
    merged_preview.update(patch)
    patch["parse_quality_score"] = _compute_parse_quality(merged_preview)

    # Freshness tier is optional; enable only after applying the DB migration.
    if _freshness_enabled():
        patch["freshness_tier"] = "green"

    return patch


def _derive_agency(payload: Dict[str, Any]) -> Tuple[Optional[str], Optional[str]]:
    link = _safe_str(payload.get("channel_link")) or _safe_str(payload.get("channel_username"))
    title = _safe_str(payload.get("channel_title"))
    if link and not link.startswith("t.me/") and not link.startswith("http"):
        link = link.lstrip("@")
        link = f"t.me/{link}"
    return title, link


def _derive_external_id(payload: Dict[str, Any]) -> str:
    parsed = payload.get("parsed") or {}
    assignment_code = _safe_str(parsed.get("assignment_code"))
    if assignment_code:
        # TutorCity API can return multiple rows with the same assignment_code but different subject sets.
        # Use a composite external_id to avoid collisions.
        if str(payload.get("source_type") or "").strip().lower() == "tutorcity_api":
            subs = parsed.get("subjects") or []
            if isinstance(subs, (list, tuple)) and subs:
                parts = [str(s).strip() for s in subs if str(s).strip()]
                if parts:
                    suffix = "+".join(sorted(set(parts)))
                    return f"{assignment_code}:{suffix}"
        return assignment_code

    channel_id = payload.get("channel_id")
    message_id = payload.get("message_id")
    if channel_id is not None and message_id is not None:
        return f"tg:{channel_id}:{message_id}"

    message_link = _safe_str(payload.get("message_link"))
    if message_link:
        return message_link

    cid = _safe_str(payload.get("cid"))
    if cid:
        return cid

    return f"unknown:{int(datetime.now(timezone.utc).timestamp())}"


def _build_assignment_row(payload: Dict[str, Any]) -> Dict[str, Any]:
    parsed = payload.get("parsed") or {}
    agency_name, agency_link = _derive_agency(payload)
    subjects = parsed.get("subjects")
    subject = _first_text(subjects)

    postal_code = _first_text(parsed.get("postal_code")) or _first_text(parsed.get("postal_code_estimated"))
    postal_lat = None
    postal_lon = None
    if postal_code:
        coords = _geocode_sg_postal(postal_code)
        if coords:
            postal_lat, postal_lon = coords

    row: Dict[str, Any] = {
        "external_id": _derive_external_id(payload),
        "agency_id": None,
        "agency_name": agency_name,
        "agency_link": agency_link,
        "channel_id": payload.get("channel_id"),
        "message_id": payload.get("message_id"),
        "message_link": _safe_str(payload.get("message_link")),
        "raw_text": _safe_str(payload.get("raw_text")),
        "subject": subject,
        "subjects": subjects if isinstance(subjects, list) else None,
        "level": _first_text(parsed.get("level")),
        "specific_student_level": _first_text(parsed.get("specific_student_level")),
        "type": _first_text(parsed.get("type")),
        "address": _first_text(parsed.get("address")),
        "postal_code": postal_code,
        "postal_lat": postal_lat,
        "postal_lon": postal_lon,
        "nearest_mrt": _first_text(parsed.get("nearest_mrt")),
        "learning_mode": _first_text(parsed.get("learning_mode")),
        "student_gender": _first_text(parsed.get("student_gender")),
        "tutor_gender": _first_text(parsed.get("tutor_gender")),
        "frequency": _safe_str(parsed.get("frequency")),
        "duration": _safe_str(parsed.get("duration")),
        "hourly_rate": _safe_str(parsed.get("hourly_rate")),
        "rate_min": parsed.get("rate_min"),
        "rate_max": parsed.get("rate_max"),
        "time_slots": parsed.get("time_slots"),
        "estimated_time_slots": parsed.get("estimated_time_slots"),
        "time_slots_note": _safe_str(parsed.get("time_slots_note")),
        "additional_remarks": _safe_str(parsed.get("additional_remarks")),
        "payload_json": payload,
        "parsed_json": parsed,
    }

    if subject_taxonomy_enabled():
        canon, general, ver, dbg = canonicalize_subjects_for_assignment_row(row)
        row["subjects_canonical"] = canon
        row["subjects_general"] = general
        row["canonicalization_version"] = int(ver)
        if subject_taxonomy_debug_enabled():
            row["canonicalization_debug"] = dbg

    row["parse_quality_score"] = _compute_parse_quality(row)
    if _freshness_enabled():
        row["freshness_tier"] = "green"
    return {k: v for k, v in row.items() if v is not None}


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    key: str
    assignments_table: str = "assignments"
    enabled: bool = False
    bump_min_seconds: int = 6 * 60 * 60  # 6 hours


def load_config_from_env() -> SupabaseConfig:
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or os.environ.get("SUPABASE_KEY") or "").strip()
    assignments_table = (os.environ.get("SUPABASE_ASSIGNMENTS_TABLE") or "assignments").strip()
    enabled = _truthy(os.environ.get("SUPABASE_ENABLED")) and bool(url and key and assignments_table)
    bump_min_seconds = int(os.environ.get("SUPABASE_BUMP_MIN_SECONDS") or str(6 * 60 * 60))
    return SupabaseConfig(
        url=url,
        key=key,
        assignments_table=assignments_table,
        enabled=enabled,
        bump_min_seconds=bump_min_seconds,
    )


class SupabaseRestClient:
    def __init__(self, cfg: SupabaseConfig):
        self.cfg = cfg
        self.base = f"{cfg.url}/rest/v1"
        self.session = requests.Session()
        self.session.headers.update(
            {
                "apikey": cfg.key,
                "authorization": f"Bearer {cfg.key}",
                "content-type": "application/json",
            }
        )

    def _url(self, path: str) -> str:
        return f"{self.base}/{path.lstrip('/')}"

    def get(self, path: str, *, timeout: int = 15) -> requests.Response:
        return self.session.get(self._url(path), timeout=timeout)

    def post(self, path: str, json_body: Any, *, timeout: int = 15, prefer: Optional[str] = None) -> requests.Response:
        headers = {}
        if prefer:
            headers["prefer"] = prefer
        return self.session.post(self._url(path), json=json_body, headers=headers, timeout=timeout)

    def patch(self, path: str, json_body: Any, *, timeout: int = 15, prefer: Optional[str] = None) -> requests.Response:
        headers = {}
        if prefer:
            headers["prefer"] = prefer
        return self.session.patch(self._url(path), json=json_body, headers=headers, timeout=timeout)


def _upsert_agency(client: SupabaseRestClient, *, name: str, channel_link: Optional[str]) -> Optional[int]:
    if not name:
        return None

    # Try lookup by channel_link first (if present), else by name.
    if channel_link:
        q = f"agencies?select=id&channel_link=eq.{requests.utils.quote(channel_link, safe='')}&limit=1"
        try:
            r = client.get(q, timeout=15)
            if r.status_code < 400:
                rows = _coerce_rows(r)
                if rows:
                    return rows[0].get("id")
        except Exception:
            logger.debug("Agency lookup by channel_link failed", exc_info=True)

    q2 = f"agencies?select=id&name=eq.{requests.utils.quote(name, safe='')}&limit=1"
    try:
        r2 = client.get(q2, timeout=15)
        if r2.status_code < 400:
            rows = _coerce_rows(r2)
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
            rows = _coerce_rows(ins)
            if rows:
                return rows[0].get("id")
    except Exception:
        logger.debug("Agency insert failed", exc_info=True)
        return None
    return None


def _coerce_rows(resp: requests.Response) -> List[Dict[str, Any]]:
    try:
        data = resp.json()
    except Exception:
        return []
    return data if isinstance(data, list) else []


def persist_assignment_to_supabase(payload: Dict[str, Any], *, cfg: Optional[SupabaseConfig] = None) -> Dict[str, Any]:
    cfg = cfg or load_config_from_env()
    if not cfg.enabled:
        return {"ok": False, "skipped": True, "reason": "supabase_disabled"}

    cid = payload.get("cid") or "<no-cid>"
    msg_id = payload.get("message_id")
    channel = payload.get("channel_link") or payload.get("channel_username")

    with bind_log_context(cid=str(cid), message_id=msg_id, channel=str(channel) if channel else None, step="supabase"):
        t_all = timed()

        client = SupabaseRestClient(cfg)
        row = _build_assignment_row(payload)

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

        now_iso = _utc_now_iso()

        select = ",".join(
            [
                "id",
                "agency_id",
                "external_id",
                "last_seen",
                "bump_count",
                "parse_quality_score",
                "message_id",
                "message_link",
                "subject",
                "subjects",
                "level",
                "specific_student_level",
                "type",
                "address",
                "postal_code",
                "nearest_mrt",
                "learning_mode",
                "student_gender",
                "tutor_gender",
                "frequency",
                "duration",
                "hourly_rate",
                "rate_min",
                "rate_max",
                "time_slots",
                "estimated_time_slots",
                "time_slots_note",
                "additional_remarks",
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
            return {"ok": False, "error": str(e)}

        existing_rows = _coerce_rows(existing_resp) if existing_resp.status_code < 400 else []
        if existing_rows:
            existing = existing_rows[0]
            last_seen = _parse_iso_dt(existing.get("last_seen"))
            bump_count = int(existing.get("bump_count") or 0)

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

            patch_body.update(_merge_patch_body(existing=existing, incoming_row=row))

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
                return {"ok": False, "error": str(e)}

            ok = patch_resp.status_code < 400
            if not ok and patch_resp.status_code == 400 and ("PGRST204" in patch_resp.text or "schema cache" in patch_resp.text):
                patch_body.pop("postal_lat", None)
                patch_body.pop("postal_lon", None)
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
                    return {"ok": False, "error": str(e)}
            if not ok:
                log_event(logger, logging.WARNING, "supabase_patch_status", status_code=patch_resp.status_code, body=patch_resp.text[:500])
            res = {"ok": ok, "action": "updated", "status_code": patch_resp.status_code, "get_ms": get_ms, "patch_ms": patch_ms}
            res["total_ms"] = round((timed() - t_all) * 1000.0, 2)
            log_event(logger, logging.INFO if ok else logging.WARNING, "supabase_persist_result", **res)
            return res

        row_to_insert = dict(row)
        row_to_insert["last_seen"] = now_iso
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
            return {"ok": False, "error": str(e)}

        ok = insert_resp.status_code < 400
        if not ok and insert_resp.status_code == 400 and ("PGRST204" in insert_resp.text or "schema cache" in insert_resp.text):
            row_to_insert.pop("postal_lat", None)
            row_to_insert.pop("postal_lon", None)
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
                return {"ok": False, "error": str(e)}
        if not ok:
            log_event(logger, logging.WARNING, "supabase_insert_status", status_code=insert_resp.status_code, body=insert_resp.text[:500])
        res = {"ok": ok, "action": "inserted", "status_code": insert_resp.status_code, "get_ms": get_ms, "insert_ms": insert_ms}
        res["total_ms"] = round((timed() - t_all) * 1000.0, 2)
        log_event(logger, logging.INFO if ok else logging.WARNING, "supabase_persist_result", **res)
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
        row = _build_assignment_row(payload)
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
        patch_body = {"status": "closed", "last_seen": _utc_now_iso()}

        try:
            patch_resp = client.patch(f"{cfg.assignments_table}?id=eq.{row_id}", patch_body, timeout=10, prefer="return=representation")
            ok = patch_resp.status_code < 400
        except Exception as e:
            log_event(logger, logging.WARNING, "supabase_close_failed", row_id=row_id, error=str(e))
            return {"ok": False, "error": str(e), "action": "close_failed"}

        res = {"ok": ok, "action": "closed" if ok else "close_failed", "status_code": patch_resp.status_code if 'patch_resp' in locals() else None}
        log_event(logger, logging.INFO if ok else logging.WARNING, "supabase_close_result", **res)
        return res
