from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, List, Optional, Tuple

import requests


def _env(name: str, default: str = "") -> str:
    v = os.environ.get(name)
    return str(v).strip() if v is not None else default


def _env_int(name: str) -> Optional[int]:
    v = _env(name, "")
    if not v:
        return None
    try:
        return int(v)
    except Exception:
        return None


BOT_TOKEN = _env("ALERT_BOT_TOKEN") or _env("GROUP_BOT_TOKEN")
CHAT_ID = _env("ALERT_CHAT_ID")
THREAD_ID = _env_int("ALERT_THREAD_ID")
PREFIX = _env("ALERT_PREFIX", "[TutorDex]")


def _format_alertmanager(payload: Dict[str, Any]) -> str:
    status = str(payload.get("status") or "").upper() or "FIRING"
    common = payload.get("commonLabels") if isinstance(payload.get("commonLabels"), dict) else {}
    alertname = str(common.get("alertname") or "Alert")
    component = str(common.get("component") or "-")
    channel = str(common.get("channel") or "")
    pipeline_version = str(common.get("pipeline_version") or "")
    schema_version = str(common.get("schema_version") or "")

    lines: List[str] = []
    lines.append(f"<b>{PREFIX}</b> <b>{status}</b>: {alertname}")
    lines.append(f"<b>Component</b>: {component}")
    if channel:
        lines.append(f"<b>Channel</b>: {channel}")
    if pipeline_version:
        lines.append(f"<b>Pipeline</b>: {pipeline_version}")
    if schema_version:
        lines.append(f"<b>Schema</b>: {schema_version}")

    alerts = payload.get("alerts") if isinstance(payload.get("alerts"), list) else []
    for a in alerts[:10]:
        if not isinstance(a, dict):
            continue
        ann = a.get("annotations") if isinstance(a.get("annotations"), dict) else {}
        summary = str(ann.get("summary") or "").strip()
        desc = str(ann.get("description") or "").strip()
        if summary or desc:
            lines.append(f"• {summary} — {desc}".strip(" —"))
    if len(alerts) > 10:
        lines.append(f"…and {len(alerts) - 10} more")
    return "\n".join(lines)


def _send_telegram(text: str) -> Tuple[bool, Dict[str, Any]]:
    if not BOT_TOKEN or not CHAT_ID:
        return False, {"error": "missing_ALERT_BOT_TOKEN_or_ALERT_CHAT_ID"}
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    body: Dict[str, Any] = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
        "disable_notification": False,
    }
    if THREAD_ID is not None:
        body["message_thread_id"] = int(THREAD_ID)
    resp = requests.post(url, json=body, timeout=10)
    try:
        data = resp.json()
    except Exception:
        data = {"status_code": resp.status_code, "text": resp.text[:300]}
    return resp.status_code < 400, {"status_code": resp.status_code, "data": data}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/alert":
            self.send_response(404)
            self.end_headers()
            return

        try:
            n = int(self.headers.get("content-length") or "0")
        except Exception:
            n = 0
        raw = self.rfile.read(max(0, n))
        try:
            payload = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            payload = {}

        text = _format_alertmanager(payload if isinstance(payload, dict) else {})
        ok, meta = _send_telegram(text)

        out = {"ok": ok, "meta": meta}
        body = json.dumps(out, ensure_ascii=False).encode("utf-8")
        self.send_response(200 if ok else 500)
        self.send_header("content-type", "application/json; charset=utf-8")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt: str, *args: Any) -> None:
        return


def main() -> None:
    host = "0.0.0.0"
    port = int(_env("PORT", "8080") or "8080")
    HTTPServer((host, port), Handler).serve_forever()


if __name__ == "__main__":
    main()

