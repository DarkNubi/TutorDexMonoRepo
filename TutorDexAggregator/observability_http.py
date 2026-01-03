from __future__ import annotations

import json
import threading
from typing import Any, Callable, Dict, Optional, Tuple
from wsgiref.simple_server import make_server

from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


HealthHandler = Callable[[], Tuple[bool, Dict[str, Any]]]


def _json_response(start_response, status_code: int, payload: Dict[str, Any]) -> list[bytes]:
    status = "200 OK" if status_code == 200 else f"{status_code} ERROR"
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "application/json; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def _text_response(start_response, status_code: int, text: str) -> list[bytes]:
    status = "200 OK" if status_code == 200 else f"{status_code} ERROR"
    body = (text or "").encode("utf-8")
    start_response(
        status,
        [
            ("Content-Type", "text/plain; charset=utf-8"),
            ("Content-Length", str(len(body))),
        ],
    )
    return [body]


def start_observability_http_server(
    *,
    host: str = "0.0.0.0",
    port: int,
    component: str,
    health_handlers: Optional[Dict[str, HealthHandler]] = None,
) -> None:
    handlers = dict(health_handlers or {})

    def app(environ, start_response):
        path = (environ.get("PATH_INFO") or "/").strip()
        if path == "/metrics":
            output = generate_latest()
            start_response(
                "200 OK",
                [
                    ("Content-Type", CONTENT_TYPE_LATEST),
                    ("Content-Length", str(len(output))),
                ],
            )
            return [output]

        if path in handlers:
            ok, extra = handlers[path]()
            payload = {"ok": bool(ok), "component": component}
            if isinstance(extra, dict) and extra:
                payload.update(extra)
            return _json_response(start_response, 200 if ok else 503, payload)

        if path in {"/health", "/healthz"}:
            return _json_response(start_response, 200, {"ok": True, "component": component})

        return _text_response(start_response, 404, "not found")

    def run() -> None:
        httpd = make_server(host, int(port), app)
        httpd.serve_forever()

    t = threading.Thread(target=run, name=f"observability_http_{component}", daemon=True)
    t.start()

