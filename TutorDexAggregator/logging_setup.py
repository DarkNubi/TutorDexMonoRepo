import contextlib
import contextvars
import asyncio
import json
import logging
import os
import time
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Iterator, Optional

from shared.config import load_aggregator_config


_cid_var: contextvars.ContextVar[str] = contextvars.ContextVar("tutordex_cid", default="-")
_message_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("tutordex_message_id", default="-")
_channel_var: contextvars.ContextVar[str] = contextvars.ContextVar("tutordex_channel", default="-")
_step_var: contextvars.ContextVar[str] = contextvars.ContextVar("tutordex_step", default="-")
_assignment_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("tutordex_assignment_id", default="-")
_pipeline_version_var: contextvars.ContextVar[str] = contextvars.ContextVar("tutordex_pipeline_version", default="-")
_schema_version_var: contextvars.ContextVar[str] = contextvars.ContextVar("tutordex_schema_version", default="-")
_component_var: contextvars.ContextVar[str] = contextvars.ContextVar("tutordex_component", default="-")
_trace_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("tutordex_trace_id", default="-")
_span_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("tutordex_span_id", default="-")


def _env_bool(name: str, default: bool) -> bool:
    v = os.getenv(name)
    if v is None:
        return default
    s = str(v).strip().lower()
    if not s:
        return default
    return s in {"1", "true", "t", "yes", "y", "on"}


@contextlib.contextmanager
def bind_log_context(
    *,
    cid: Optional[str] = None,
    message_id: Optional[str] = None,
    channel: Optional[str] = None,
    step: Optional[str] = None,
    assignment_id: Optional[str] = None,
    pipeline_version: Optional[str] = None,
    schema_version: Optional[str] = None,
    component: Optional[str] = None,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
) -> Iterator[None]:
    tokens = []
    try:
        if cid is not None:
            tokens.append((_cid_var, _cid_var.set(str(cid))))
        if message_id is not None:
            tokens.append((_message_id_var, _message_id_var.set(str(message_id))))
        if channel is not None:
            tokens.append((_channel_var, _channel_var.set(str(channel))))
        if step is not None:
            tokens.append((_step_var, _step_var.set(str(step))))
        if assignment_id is not None:
            tokens.append((_assignment_id_var, _assignment_id_var.set(str(assignment_id))))
        if pipeline_version is not None:
            tokens.append((_pipeline_version_var, _pipeline_version_var.set(str(pipeline_version))))
        if schema_version is not None:
            tokens.append((_schema_version_var, _schema_version_var.set(str(schema_version))))
        if component is not None:
            tokens.append((_component_var, _component_var.set(str(component))))
        if trace_id is not None:
            tokens.append((_trace_id_var, _trace_id_var.set(str(trace_id))))
        if span_id is not None:
            tokens.append((_span_id_var, _span_id_var.set(str(span_id))))
        yield
    finally:
        for var, token in reversed(tokens):
            try:
                var.reset(token)
            except Exception:
                logging.getLogger("logging_setup").exception("Failed to reset log context var=%s", getattr(var, "name", "<unknown>"))


def set_step(step: str) -> None:
    _step_var.set(str(step) if step is not None else "-")


class _ContextFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "cid"):
            record.cid = _cid_var.get()
        if not hasattr(record, "message_id"):
            record.message_id = _message_id_var.get()
        if not hasattr(record, "channel"):
            record.channel = _channel_var.get()
        if not hasattr(record, "step"):
            record.step = _step_var.get()
        if not hasattr(record, "assignment_id"):
            record.assignment_id = _assignment_id_var.get()
        if not hasattr(record, "pipeline_version"):
            record.pipeline_version = _pipeline_version_var.get()
        if not hasattr(record, "schema_version"):
            record.schema_version = _schema_version_var.get()
        if not hasattr(record, "component"):
            record.component = _component_var.get()
        if not hasattr(record, "trace_id"):
            record.trace_id = _trace_id_var.get()
        if not hasattr(record, "span_id"):
            record.span_id = _span_id_var.get()
        if not hasattr(record, "event"):
            record.event = record.msg if isinstance(record.msg, str) else record.name
        if not hasattr(record, "data"):
            record.data = None
        return True


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, datefmt="%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "component": getattr(record, "component", "-"),
            "event": getattr(record, "event", record.getMessage()),
            "msg": record.getMessage(),
            "cid": getattr(record, "cid", "-"),
            "message_id": getattr(record, "message_id", "-"),
            "channel": getattr(record, "channel", "-"),
            "step": getattr(record, "step", "-"),
            "assignment_id": getattr(record, "assignment_id", "-"),
            "pipeline_version": getattr(record, "pipeline_version", "-"),
            "schema_version": getattr(record, "schema_version", "-"),
            "trace_id": getattr(record, "trace_id", "-"),
            "span_id": getattr(record, "span_id", "-"),
        }
        data = getattr(record, "data", None)
        if isinstance(data, dict) and data:
            payload["data"] = data

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


class _TextFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        data = getattr(record, "data", None)
        if isinstance(data, dict) and data:
            try:
                return f"{base} data={json.dumps(data, ensure_ascii=False, separators=(',', ':'))}"
            except Exception:
                return f"{base} data=<unserializable>"
        return base


def log_event(logger: logging.Logger, level: int, event: str, **data: Any) -> None:
    logger.log(level, event, extra={"event": event, "data": data or None})


def timed() -> float:
    return time.perf_counter()


async def run_in_thread(func, /, *args: Any, **kwargs: Any) -> Any:
    ctx = contextvars.copy_context()
    return await asyncio.to_thread(ctx.run, func, *args, **kwargs)


def setup_logging(
    *,
    log_dir: Optional[str] = None,
    log_file: Optional[str] = None,
    level: Optional[str] = None,
) -> None:
    """
    Configure project-wide logging (console + rotating file).

    Configuration is loaded via `shared.config.load_aggregator_config()` with the usual `.env` and
    environment variable priority (Pydantic-Settings). CLI args override config values.

    Notes:
      - Idempotent; calling multiple times is safe.
      - Avoid logging secrets (bot tokens, session strings, API keys).
    """
    try:
        cfg = load_aggregator_config()
    except Exception:
        cfg = None

    root = logging.getLogger()
    if getattr(root, "_tutordex_configured", False):
        return

    level_name = (level or (cfg.log_level if cfg else None) or "INFO").upper().strip()
    log_level = getattr(logging, level_name, logging.INFO)
    root.setLevel(log_level)

    log_json = bool(cfg.log_json) if cfg else False
    context_filter = _ContextFilter()

    base_fmt = (
        "%(asctime)s %(levelname)s %(name)s "
        "cid=%(cid)s msg_id=%(message_id)s channel=%(channel)s step=%(step)s "
        "%(message)s"
    )
    formatter: logging.Formatter = _JsonFormatter() if log_json else _TextFormatter(
        fmt=base_fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    def _add_handler(h: logging.Handler) -> None:
        h.setLevel(log_level)
        h.addFilter(context_filter)
        h.setFormatter(formatter)
        root.addHandler(h)

    if (bool(cfg.log_to_console) if cfg else True):
        _add_handler(logging.StreamHandler())

    if (bool(cfg.log_to_file) if cfg else True):
        here = Path(__file__).resolve().parent
        chosen_dir = Path(log_dir or (cfg.log_dir if cfg else None) or (here / "logs"))
        chosen_dir.mkdir(parents=True, exist_ok=True)

        filename = log_file or (cfg.log_file if cfg else None) or "tutordex_aggregator.log"
        path = chosen_dir / filename

        max_bytes = int(cfg.log_max_bytes) if cfg else 5_000_000
        backup_count = int(cfg.log_backup_count) if cfg else 5

        try:
            _add_handler(
                RotatingFileHandler(
                    path,
                    maxBytes=max_bytes,
                    backupCount=backup_count,
                    encoding="utf-8",
                )
            )
        except (PermissionError, OSError):
            # Common when containers create the logs directory/file as root.
            # Degrade safely to console-only logging instead of crashing imports.
            logging.getLogger("logging_setup").warning("Failed to enable file logging for %s; continuing with console only.", path, exc_info=True)

    root._tutordex_configured = True
    try:
        file_handler_paths = []
        for h in root.handlers:
            if hasattr(h, "baseFilename"):
                file_handler_paths.append(getattr(h, "baseFilename"))
        log_event(
            root,
            logging.INFO,
            "logging_configured",
            log_level=level_name,
            json=log_json,
            to_console=_env_bool("LOG_TO_CONSOLE", True),
            to_file=_env_bool("LOG_TO_FILE", True),
            file_paths=file_handler_paths or None,
        )
    except Exception:
        logging.getLogger("logging_setup").exception("Failed to emit logging_configured event")
