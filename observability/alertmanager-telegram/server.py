from __future__ import annotations

import html
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
ENVIRONMENT = _env("APP_ENV", "dev").upper()


def _esc(s: Any) -> str:
    return html.escape(str(s or ""), quote=False).strip()


def _format_alertmanager(payload: Dict[str, Any]) -> str:
    status = str(payload.get("status") or "").upper() or "FIRING"
    common = payload.get("commonLabels") if isinstance(payload.get("commonLabels"), dict) else {}
    alertname = str(common.get("alertname") or "Alert")
    component = str(common.get("component") or "-")
    channel = str(common.get("channel") or "")
    pipeline_version = str(common.get("pipeline_version") or "")
    schema_version = str(common.get("schema_version") or "")

    lines: List[str] = []
    lines.append(f"<b>{_esc(PREFIX)} [{_esc(ENVIRONMENT)}]</b> <b>{_esc(status)}</b>: {_esc(alertname)}")
    if status == "RESOLVED":
        lines.append("<i>Note: RESOLVED messages include the last observed value before the alert cleared.</i>")
    lines.append(f"<b>Component</b>: {_esc(component)}")
    if channel:
        lines.append(f"<b>Channel</b>: {_esc(channel)}")
    if pipeline_version:
        lines.append(f"<b>Pipeline</b>: {_esc(pipeline_version)}")
    if schema_version:
        lines.append(f"<b>Schema</b>: {_esc(schema_version)}")

    alerts = payload.get("alerts") if isinstance(payload.get("alerts"), list) else []
    for a in alerts[:10]:
        if not isinstance(a, dict):
            continue
        ann = a.get("annotations") if isinstance(a.get("annotations"), dict) else {}
        summary = _esc(ann.get("summary"))
        desc = _esc(ann.get("description"))
        if summary and desc:
            lines.append(f"• {summary} — {desc}")
        elif summary:
            lines.append(f"• {summary}")
        elif desc:
            lines.append(f"• {desc}")
    if len(alerts) > 10:
        lines.append(f"…and {len(alerts) - 10} more")

    # Telegram sendMessage limit is 4096 characters. Truncate on line boundaries to avoid
    # breaking HTML tags/entities.
    text = "\n".join(lines)
    max_len = _env_int("TELEGRAM_MAX_CHARS") or 3900
    suffix = "\n…(truncated)"
    if len(text) <= max_len:
        return text

    out_lines: List[str] = []
    for ln in lines:
        candidate = "\n".join(out_lines + [ln]) + suffix
        if len(candidate) > max_len:
            break
        out_lines.append(ln)
    return "\n".join(out_lines) + suffix


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

    timeout_s = float(_env("TELEGRAM_TIMEOUT_SECONDS", "20") or "20")
    try:
        resp = requests.post(url, json=body, timeout=timeout_s)
    except requests.RequestException as e:
        return False, {"status_code": 599, "error": type(e).__name__, "detail": str(e)[:200]}
    try:
        data = resp.json()
    except Exception:
        data = {"status_code": resp.status_code, "text": resp.text[:300]}
    ok = resp.status_code < 400 and bool(isinstance(data, dict) and data.get("ok") is True)
    return ok, {"status_code": resp.status_code, "data": data}


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
        # If Telegram isn't configured, don't cause Alertmanager to retry forever.
        if not ok and meta.get("error") == "missing_ALERT_BOT_TOKEN_or_ALERT_CHAT_ID":
            self.send_response(200)
        else:
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
