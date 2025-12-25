import os
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Optional, List

import requests


logger = logging.getLogger("supabase_store")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class SupabaseConfig:
    url: str
    key: str
    enabled: bool = False


def load_supabase_config() -> SupabaseConfig:
    url = (os.environ.get("SUPABASE_URL") or "").strip().rstrip("/")
    key = (os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    enabled = _truthy(os.environ.get("SUPABASE_ENABLED")) and bool(url and key)
    return SupabaseConfig(url=url, key=key, enabled=enabled)


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

    def post(self, path: str, json_body: Any, *, timeout: int = 15, prefer: Optional[str] = None, extra_headers: Optional[Dict[str, str]] = None) -> requests.Response:
        headers = {}
        if prefer:
            headers["prefer"] = prefer
        if extra_headers:
            headers.update(extra_headers)
        return self.session.post(self._url(path), json=json_body, headers=headers, timeout=timeout)

    def patch(self, path: str, json_body: Any, *, timeout: int = 15, prefer: Optional[str] = None) -> requests.Response:
        headers = {}
        if prefer:
            headers["prefer"] = prefer
        return self.session.patch(self._url(path), json=json_body, headers=headers, timeout=timeout)


def _coerce_rows(resp: requests.Response) -> List[Dict[str, Any]]:
    try:
        data = resp.json()
    except Exception:
        return []
    return data if isinstance(data, list) else []


class SupabaseStore:
    def __init__(self, cfg: Optional[SupabaseConfig] = None):
        self.cfg = cfg or load_supabase_config()
        self.client = SupabaseRestClient(self.cfg) if self.cfg.enabled else None

    def enabled(self) -> bool:
        return bool(self.client)

    def upsert_user(self, *, firebase_uid: str, email: Optional[str], name: Optional[str]) -> Optional[int]:
        if not self.client:
            return None
        uid = str(firebase_uid).strip()
        if not uid:
            return None

        row = {"firebase_uid": uid, "updated_at": _utc_now_iso()}
        if email:
            row["email"] = str(email).strip()
        if name:
            row["name"] = str(name).strip()

        try:
            resp = self.client.post(
                "users?on_conflict=firebase_uid",
                [row],
                timeout=20,
                prefer="resolution=merge-duplicates,return=representation",
            )
        except Exception as e:
            logger.warning("Supabase users upsert failed uid=%s error=%s", uid, e)
            return None

        if resp.status_code >= 400:
            logger.warning("Supabase users upsert status=%s body=%s", resp.status_code, resp.text[:500])
            return None

        rows = _coerce_rows(resp)
        if rows:
            return rows[0].get("id")

        # fallback: query it
        q = f"users?select=id&firebase_uid=eq.{requests.utils.quote(uid, safe='')}&limit=1"
        r2 = self.client.get(q, timeout=15)
        if r2.status_code < 400:
            rr = _coerce_rows(r2)
            if rr:
                return rr[0].get("id")
        return None

    def upsert_preferences(self, *, user_id: int, prefs: Dict[str, Any]) -> bool:
        if not self.client:
            return False
        body = dict(prefs)
        body["user_id"] = int(user_id)
        body["updated_at"] = _utc_now_iso()

        try:
            resp = self.client.post(
                "user_preferences?on_conflict=user_id",
                [body],
                timeout=20,
                prefer="resolution=merge-duplicates,return=representation",
            )
        except Exception as e:
            logger.warning("Supabase prefs upsert failed user_id=%s error=%s", user_id, e)
            return False
        if resp.status_code >= 400:
            # Backward-compatible retry when DB schema hasn't been migrated yet.
            if resp.status_code == 400 and ("PGRST204" in resp.text or "schema cache" in resp.text):
                retry_body = dict(body)
                for k in ("postal_code", "postal_lat", "postal_lon"):
                    retry_body.pop(k, None)
                if retry_body != body:
                    try:
                        resp2 = self.client.post(
                            "user_preferences?on_conflict=user_id",
                            [retry_body],
                            timeout=20,
                            prefer="resolution=merge-duplicates,return=representation",
                        )
                        if resp2.status_code < 400:
                            return True
                        logger.warning("Supabase prefs upsert retry status=%s body=%s", resp2.status_code, resp2.text[:500])
                    except Exception as e:
                        logger.warning("Supabase prefs upsert retry failed user_id=%s error=%s", user_id, e)
            logger.warning("Supabase prefs upsert status=%s body=%s", resp.status_code, resp.text[:500])
            return False
        return True

    def get_preferences(self, *, user_id: int) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        base = f"user_preferences?user_id=eq.{int(user_id)}&limit=1"
        q1 = base + "&select=subjects,levels,subject_pairs,assignment_types,tutor_kinds,learning_modes,postal_code,postal_lat,postal_lon,updated_at"
        r = self.client.get(q1, timeout=15)
        if r.status_code == 400 and ("PGRST204" in r.text or "schema cache" in r.text):
            q2 = base + "&select=subjects,levels,subject_pairs,assignment_types,tutor_kinds,learning_modes,updated_at"
            r = self.client.get(q2, timeout=15)
        if r.status_code >= 400:
            return None
        rows = _coerce_rows(r)
        return rows[0] if rows else None

    def insert_event(self, *, user_id: Optional[int], assignment_id: Optional[int], event_type: str, meta: Optional[Dict[str, Any]] = None) -> bool:
        if not self.client:
            return False
        row: Dict[str, Any] = {"event_type": str(event_type).strip(), "event_time": _utc_now_iso()}
        if user_id is not None:
            row["user_id"] = int(user_id)
        if assignment_id is not None:
            row["assignment_id"] = int(assignment_id)
        if meta:
            row["meta"] = meta

        try:
            resp = self.client.post("analytics_events", [row], timeout=20, prefer="return=representation")
        except Exception as e:
            logger.warning("Supabase event insert failed error=%s", e)
            return False
        return resp.status_code < 400

    def resolve_assignment_id(self, *, external_id: str, agency_name: Optional[str] = None) -> Optional[int]:
        if not self.client:
            return None
        ext = str(external_id).strip()
        if not ext:
            return None
        q = f"assignments?select=id&external_id=eq.{requests.utils.quote(ext, safe='')}"
        if agency_name:
            q += f"&agency_name=eq.{requests.utils.quote(str(agency_name).strip(), safe='')}"
        q += "&limit=1"
        r = self.client.get(q, timeout=15)
        if r.status_code >= 400:
            return None
        rows = _coerce_rows(r)
        if rows:
            return rows[0].get("id")
        return None

    def increment_assignment_clicks(self, *, external_id: str, original_url: str, delta: int = 1) -> Optional[int]:
        """
        Atomic increment via RPC `increment_assignment_clicks` (must be installed in DB).
        Returns the new click count on success.
        """
        if not self.client:
            return None
        ext = str(external_id).strip()
        url = str(original_url).strip()
        if not ext or not url:
            return None

        body = {"p_external_id": ext, "p_original_url": url, "p_delta": int(delta)}
        try:
            resp = self.client.post("rpc/increment_assignment_clicks", body, timeout=20)  # type: ignore[arg-type]
        except Exception as e:
            logger.warning("Supabase increment clicks rpc failed external_id=%s error=%s", ext, e)
            return None
        if resp.status_code >= 400:
            logger.warning("Supabase increment clicks rpc status=%s body=%s", resp.status_code, resp.text[:500])
            return None

        try:
            data = resp.json()
        except Exception:
            return None

        # PostgREST may return a scalar or a list depending on config.
        if isinstance(data, (int, float)):
            return int(data)
        if isinstance(data, list) and data and isinstance(data[0], (int, float)):
            return int(data[0])
        if isinstance(data, dict) and "clicks" in data:
            try:
                return int(data["clicks"])
            except Exception:
                return None
        return None

    def list_open_assignments(
        self,
        *,
        limit: int = 50,
        cursor_last_seen: Optional[str] = None,
        cursor_id: Optional[int] = None,
        level: Optional[str] = None,
        specific_student_level: Optional[str] = None,
        subject: Optional[str] = None,
        agency_name: Optional[str] = None,
        learning_mode: Optional[str] = None,
        location_query: Optional[str] = None,
        min_rate: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        RPC wrapper for `public.list_open_assignments` (must be installed in DB).
        Returns: { "items": [...], "total": int }
        """
        if not self.client:
            return None

        payload: Dict[str, Any] = {
            "p_limit": int(limit),
            "p_cursor_last_seen": cursor_last_seen,
            "p_cursor_id": int(cursor_id) if cursor_id is not None else None,
            "p_level": level,
            "p_specific_student_level": specific_student_level,
            "p_subject": subject,
            "p_agency_name": agency_name,
            "p_learning_mode": learning_mode,
            "p_location_query": location_query,
            "p_min_rate": int(min_rate) if min_rate is not None else None,
        }
        # PostgREST treats missing keys as defaults; remove null keys to keep payload tidy.
        payload = {k: v for k, v in payload.items() if v is not None}

        try:
            resp = self.client.post("rpc/list_open_assignments", payload, timeout=25)  # type: ignore[arg-type]
        except Exception as e:
            logger.warning("Supabase list_open_assignments rpc failed error=%s", e)
            return None
        if resp.status_code >= 400:
            logger.warning("Supabase list_open_assignments rpc status=%s body=%s", resp.status_code, resp.text[:500])
            return None

        rows = _coerce_rows(resp)
        total = 0
        if rows:
            try:
                total = int(rows[0].get("total_count") or 0)
            except Exception:
                total = 0
        for r in rows:
            r.pop("total_count", None)

        return {"items": rows, "total": total}

    def open_assignment_facets(
        self,
        *,
        level: Optional[str] = None,
        specific_student_level: Optional[str] = None,
        subject: Optional[str] = None,
        agency_name: Optional[str] = None,
        learning_mode: Optional[str] = None,
        location_query: Optional[str] = None,
        min_rate: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        RPC wrapper for `public.open_assignment_facets` (must be installed in DB).
        Returns a JSON object with keys like: total, levels, subjects, agencies, learning_modes.
        """
        if not self.client:
            return None

        payload: Dict[str, Any] = {
            "p_level": level,
            "p_specific_student_level": specific_student_level,
            "p_subject": subject,
            "p_agency_name": agency_name,
            "p_learning_mode": learning_mode,
            "p_location_query": location_query,
            "p_min_rate": int(min_rate) if min_rate is not None else None,
        }
        payload = {k: v for k, v in payload.items() if v is not None}

        try:
            resp = self.client.post("rpc/open_assignment_facets", payload, timeout=25)  # type: ignore[arg-type]
        except Exception as e:
            logger.warning("Supabase open_assignment_facets rpc failed error=%s", e)
            return None
        if resp.status_code >= 400:
            logger.warning("Supabase open_assignment_facets rpc status=%s body=%s", resp.status_code, resp.text[:500])
            return None

        try:
            data = resp.json()
        except Exception:
            return None

        # PostgREST may return a JSON object or a list containing it.
        if isinstance(data, dict):
            return data
        if isinstance(data, list) and data and isinstance(data[0], dict):
            return data[0]
        return None

    def upsert_broadcast_message(
        self,
        *,
        external_id: str,
        original_url: str,
        sent_chat_id: int,
        sent_message_id: int,
        message_html: str,
    ) -> bool:
        if not self.client:
            return False
        ext = str(external_id).strip()
        url = str(original_url).strip()
        if not ext or not url:
            return False
        row = {
            "external_id": ext,
            "original_url": url,
            "sent_chat_id": int(sent_chat_id),
            "sent_message_id": int(sent_message_id),
            "message_html": str(message_html),
            "updated_at": _utc_now_iso(),
        }
        try:
            resp = self.client.post(
                "broadcast_messages?on_conflict=external_id",
                [row],
                timeout=20,
                prefer="resolution=merge-duplicates,return=representation",
            )
        except Exception as e:
            logger.warning("Supabase broadcast_messages upsert failed external_id=%s error=%s", ext, e)
            return False
        if resp.status_code >= 400:
            logger.warning("Supabase broadcast_messages upsert status=%s body=%s", resp.status_code, resp.text[:500])
            return False
        return True

    def get_broadcast_message(self, *, external_id: str) -> Optional[Dict[str, Any]]:
        if not self.client:
            return None
        ext = str(external_id).strip()
        if not ext:
            return None
        q = f"broadcast_messages?select=external_id,original_url,sent_chat_id,sent_message_id,message_html,last_rendered_clicks,last_edited_at&external_id=eq.{requests.utils.quote(ext, safe='')}&limit=1"
        try:
            resp = self.client.get(q, timeout=15)
        except Exception:
            return None
        if resp.status_code >= 400:
            return None
        rows = _coerce_rows(resp)
        return rows[0] if rows else None

    def mark_broadcast_edited(self, *, external_id: str, clicks: int, message_html: str) -> bool:
        if not self.client:
            return False
        ext = str(external_id).strip()
        if not ext:
            return False
        body = {
            "last_rendered_clicks": int(clicks),
            "last_edited_at": _utc_now_iso(),
            "message_html": str(message_html),
            "updated_at": _utc_now_iso(),
        }
        try:
            resp = self.client.patch(
                f"broadcast_messages?external_id=eq.{requests.utils.quote(ext, safe='')}",
                body,
                timeout=20,
                prefer="return=representation",
            )
        except Exception as e:
            logger.warning("Supabase broadcast_messages patch failed external_id=%s error=%s", ext, e)
            return False
        return resp.status_code < 400

