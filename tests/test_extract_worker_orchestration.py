import sys
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict

import pytest


def _ensure_aggregator_sys_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    agg_dir = repo_root / "TutorDexAggregator"
    agg_path = str(agg_dir)
    if agg_path in sys.path:
        sys.path.remove(agg_path)
    sys.path.insert(0, agg_path)
    loaded_logging_setup = sys.modules.get("logging_setup")
    if loaded_logging_setup is not None and "TutorDexAggregator" not in str(getattr(loaded_logging_setup, "__file__", "")):
        sys.modules.pop("logging_setup", None)


@dataclass(frozen=True)
class _Version:
    pipeline_version: str
    schema_version: str


class _NoopMetric:
    def labels(self, **kwargs: Any) -> "_NoopMetric":
        return self

    def inc(self, *args: Any, **kwargs: Any) -> None:
        return None

    def set(self, *args: Any, **kwargs: Any) -> None:
        return None

    def observe(self, *args: Any, **kwargs: Any) -> None:
        return None


@pytest.fixture
def worker_main_module():
    _ensure_aggregator_sys_path()
    import importlib

    # Import as a "workers.*" module to match the file's bare imports.
    return importlib.import_module("workers.extract_worker_main")


def test_worker_oneshot_exits_when_no_jobs(monkeypatch, worker_main_module):
    cfg = SimpleNamespace(extraction_worker_oneshot=True)
    logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, debug=lambda *a, **k: None, log=lambda *a, **k: None)
    version = _Version(pipeline_version="pv-test", schema_version="sv-test")

    monkeypatch.setattr(worker_main_module, "bootstrap_worker", lambda: (cfg, logger, version, object()))
    monkeypatch.setattr(worker_main_module, "supabase_cfg", lambda _cfg: ("http://sb", "key"))

    captured: Dict[str, Any] = {}

    def _start_obs(*, port: int, component: str, health_handlers: Dict[str, Any]) -> None:
        captured["port"] = port
        captured["component"] = component
        captured["health_handlers"] = health_handlers

    monkeypatch.setattr(worker_main_module, "start_observability_http_server", _start_obs)

    claim_calls: Dict[str, Any] = {}

    def _claim_jobs(url: str, key: str, *, pipeline_version: str, limit: int, schema_version: str):
        claim_calls["args"] = (url, key)
        claim_calls["kwargs"] = {
            "pipeline_version": pipeline_version,
            "limit": limit,
            "schema_version": schema_version,
        }
        return []

    monkeypatch.setattr(worker_main_module, "claim_jobs", _claim_jobs)

    # Ensure we don't sleep in oneshot mode.
    monkeypatch.setattr(worker_main_module.time, "sleep", lambda _: (_ for _ in ()).throw(AssertionError("sleep called")))

    # Avoid queue metrics and requeue paths.
    monkeypatch.setattr(worker_main_module.time, "time", lambda: 0.0)

    events = []

    def _log_event(_logger: Any, _level: int, name: str, **fields: Any) -> None:
        events.append((name, fields))

    monkeypatch.setattr(worker_main_module, "log_event", _log_event)

    worker_main_module.main()

    assert captured["port"] == 9002
    assert captured["component"] == "worker"
    assert "/health/worker" in captured["health_handlers"]
    assert "/health/dependencies" in captured["health_handlers"]

    assert claim_calls["kwargs"]["pipeline_version"] == worker_main_module.DEFAULT_PIPELINE_VERSION
    assert claim_calls["kwargs"]["schema_version"] == "sv-test"
    assert any(name == "worker_oneshot_done" for (name, _fields) in events)


def test_worker_dependency_health_handler_uses_count_exact(monkeypatch, worker_main_module):
    cfg = SimpleNamespace(extraction_worker_oneshot=True)
    logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, debug=lambda *a, **k: None, log=lambda *a, **k: None)
    version = _Version(pipeline_version="pv-test", schema_version="sv-test")

    monkeypatch.setattr(worker_main_module, "bootstrap_worker", lambda: (cfg, logger, version, object()))
    monkeypatch.setattr(worker_main_module, "supabase_cfg", lambda _cfg: ("http://sb", "key"))
    monkeypatch.setattr(worker_main_module, "claim_jobs", lambda *a, **k: [])
    monkeypatch.setattr(worker_main_module.time, "sleep", lambda _: None)
    monkeypatch.setattr(worker_main_module.time, "time", lambda: 0.0)

    captured: Dict[str, Any] = {}

    def _start_obs(*, port: int, component: str, health_handlers: Dict[str, Any]) -> None:
        captured["health_handlers"] = health_handlers

    monkeypatch.setattr(worker_main_module, "start_observability_http_server", _start_obs)

    called: Dict[str, Any] = {}

    class _Resp:
        status_code = 200

    def _requests_get(url: str, *, headers: Dict[str, str], timeout: int):
        called["url"] = url
        called["headers"] = headers
        called["timeout"] = timeout
        return _Resp()

    monkeypatch.setattr(worker_main_module.requests, "get", _requests_get)

    worker_main_module.main()

    dep = captured["health_handlers"]["/health/dependencies"]
    ok, info = dep()

    assert ok is True
    assert info["status_code"] == 200
    assert called["url"].startswith("http://sb/rest/v1/telegram_extractions")
    assert called["headers"]["prefer"] == "count=exact"


def test_worker_stops_after_max_jobs(monkeypatch, worker_main_module):
    cfg = SimpleNamespace(extraction_worker_oneshot=False, extraction_worker_max_jobs=1)
    logger = SimpleNamespace(info=lambda *a, **k: None, warning=lambda *a, **k: None, debug=lambda *a, **k: None, log=lambda *a, **k: None)
    version = _Version(pipeline_version="pv-test", schema_version="sv-test")

    monkeypatch.setattr(worker_main_module, "bootstrap_worker", lambda: (cfg, logger, version, object()))
    monkeypatch.setattr(worker_main_module, "supabase_cfg", lambda _cfg: ("http://sb", "key"))
    monkeypatch.setattr(worker_main_module, "start_observability_http_server", lambda **kwargs: None)
    monkeypatch.setattr(worker_main_module, "_import_side_effects", lambda: (None, None))

    # Avoid queue metrics and requeue paths.
    monkeypatch.setattr(worker_main_module.time, "time", lambda: 0.0)

    # No-op metrics.
    for name in (
        "queue_pending",
        "queue_processing",
        "queue_ok",
        "queue_failed",
        "queue_oldest_pending_age_seconds",
        "queue_oldest_processing_age_seconds",
        "worker_job_latency_seconds",
        "worker_jobs_processed_total",
        "worker_requeued_stale_jobs_total",
    ):
        monkeypatch.setattr(worker_main_module, name, _NoopMetric())

    monkeypatch.setattr(worker_main_module, "requeue_stale_jobs", lambda *a, **k: 0)
    monkeypatch.setattr(worker_main_module, "get_queue_counts", lambda *a, **k: {})
    monkeypatch.setattr(worker_main_module, "get_oldest_created_age_seconds", lambda *a, **k: 0.0)

    jobs = [{"id": 1, "raw_id": 2, "channel_link": "t.me/x", "message_id": 3}]
    monkeypatch.setattr(worker_main_module, "claim_jobs", lambda *a, **k: list(jobs))
    monkeypatch.setattr(worker_main_module, "work_one", lambda **kwargs: "ok")

    worker_main_module.main()


def test_resolve_side_effect_toggles_respects_explicit_flags(worker_main_module):
    cfg = SimpleNamespace(
        enable_broadcast=False,
        enable_dms=False,
        dm_enabled=True,
        group_bot_token="token",
        aggregator_channel_id="-100123",
        model_fields_set={"enable_broadcast", "enable_dms"},
    )

    enable_broadcast, enable_dms = worker_main_module._resolve_side_effect_toggles(cfg)

    assert enable_broadcast is False
    assert enable_dms is False


def test_resolve_side_effect_toggles_fallbacks_to_configured_channels(worker_main_module):
    cfg = SimpleNamespace(
        dm_enabled=True,
        group_bot_token="token",
        bot_api_url=None,
        aggregator_channel_id="-100123",
        aggregator_channel_ids=None,
        model_fields_set=set(),
    )

    enable_broadcast, enable_dms = worker_main_module._resolve_side_effect_toggles(cfg)

    assert enable_broadcast is True
    assert enable_dms is True


def test_queue_metrics_filter_by_pipeline_version(monkeypatch):
    _ensure_aggregator_sys_path()
    import importlib

    supabase_ops = importlib.import_module("workers.supabase_operations")

    calls = []

    class _Resp:
        headers = {"content-range": "*/7"}

    def _requests_get(url: str, *, headers: Dict[str, str], timeout: int):
        calls.append(url)
        return _Resp()

    monkeypatch.setattr(supabase_ops.requests, "get", _requests_get)

    counts = supabase_ops.get_queue_counts("http://sb", "key", ["pending"], pipeline_version="pv-test")

    assert counts["pending"] == 7
    assert "status=eq.pending" in calls[0]
    assert "pipeline_version=eq.pv-test" in calls[0]


def test_oldest_queue_age_filters_by_pipeline_version(monkeypatch):
    _ensure_aggregator_sys_path()
    import importlib

    supabase_ops = importlib.import_module("workers.supabase_operations")

    captured = {}

    def _get_one(url: str, key: str, table: str, query: str, **kwargs: Any):
        captured["query"] = query
        return None

    monkeypatch.setattr(supabase_ops, "get_one", _get_one)

    assert supabase_ops.get_oldest_created_age_seconds("http://sb", "key", "processing", pipeline_version="pv-test") is None
    assert "status=eq.processing" in captured["query"]
    assert "pipeline_version=eq.pv-test" in captured["query"]
