import json
import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional


def _truthy(value: Optional[str]) -> bool:
    if value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


def _env(name: str, default: str) -> str:
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip()


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        for key in ("request_id", "method", "path", "status_code", "latency_ms", "client_ip", "uid"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)

        return json.dumps(payload, ensure_ascii=False)


def setup_logging(service_name: str = "tutordex_backend") -> None:
    level = _env("LOG_LEVEL", "INFO").upper()
    log_to_console = _truthy(_env("LOG_TO_CONSOLE", "true"))
    log_to_file = _truthy(_env("LOG_TO_FILE", "true"))
    log_json = _truthy(_env("LOG_JSON", "false"))

    log_dir = Path(_env("LOG_DIR", str(Path(__file__).resolve().parent / "logs")))
    log_file = _env("LOG_FILE", f"{service_name}.log")
    max_bytes = int(_env("LOG_MAX_BYTES", "5000000"))
    backup_count = int(_env("LOG_BACKUP_COUNT", "5"))

    fmt = JsonFormatter() if log_json else logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))

    for h in list(root.handlers):
        root.removeHandler(h)

    if log_to_console:
        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        root.addHandler(sh)

    if log_to_file:
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            fh = RotatingFileHandler(
                filename=str(log_dir / log_file),
                maxBytes=max_bytes,
                backupCount=backup_count,
                encoding="utf-8",
            )
            fh.setFormatter(fmt)
            root.addHandler(fh)
        except Exception:
            # If file logging fails (permissions, etc), keep console logging.
            root.exception("Failed to initialize file logging")

