import sys
from pathlib import Path
from types import SimpleNamespace


def _ensure_aggregator_sys_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    agg_dir = str(repo_root / "TutorDexAggregator")
    if agg_dir in sys.path:
        sys.path.remove(agg_dir)
    sys.path.insert(0, agg_dir)


def test_tutorcity_respects_side_effect_toggles(monkeypatch):
    _ensure_aggregator_sys_path()
    import importlib

    mod = importlib.import_module("utilities.tutorcity_fetch")

    cfg = SimpleNamespace(
        tutorcity_api_url=None,
        tutorcity_limit=50,
        tutorcity_timeout_seconds=30,
        tutorcity_user_agent=None,
        enable_broadcast=False,
        enable_dms=False,
    )
    base_cfg = SimpleNamespace(url="http://sb", key="key", assignments_table="assignments", enabled=True)

    row = {
        "assignment_code": "TC1",
        "subjects": ["12"],
        "level": "2",
        "year": "P5",
        "address": "Woodlands",
        "postal_code": "730000",
        "availability": "weekday evenings",
        "hourly_rate": "$40/h",
    }

    calls = {"broadcast": 0, "dm": 0}
    monkeypatch.setattr(mod, "load_aggregator_config", lambda: cfg)
    monkeypatch.setattr(mod, "load_config_from_env", lambda: base_cfg)
    monkeypatch.setattr(mod, "fetch_api", lambda *a, **k: [row])
    monkeypatch.setattr(mod, "persist_assignment_to_supabase", lambda *a, **k: {"ok": True, "action": "inserted"})
    monkeypatch.setattr(
        mod,
        "broadcast_assignments",
        SimpleNamespace(send_broadcast=lambda payload: calls.__setitem__("broadcast", calls["broadcast"] + 1)),
    )
    monkeypatch.setattr(mod, "send_dms", lambda payload: calls.__setitem__("dm", calls["dm"] + 1))
    monkeypatch.setattr(sys, "argv", ["tutorcity_fetch.py", "--limit", "1"])

    mod.main()

    assert calls == {"broadcast": 0, "dm": 0}


def test_freshness_requires_explicit_telegram_side_effect_gates(monkeypatch):
    _ensure_aggregator_sys_path()
    import importlib

    mod = importlib.import_module("update_freshness_tiers")

    supa_cfg = SimpleNamespace(enabled=True, assignments_table="assignments")
    agg_cfg = SimpleNamespace(
        freshness_propagate_telegram_enabled=False,
        freshness_delete_expired_telegram_enabled=False,
    )

    class _Resp:
        status_code = 200
        text = ""

        def json(self):
            return []

    class _Client:
        def __init__(self, cfg):
            self.cfg = cfg

        def patch(self, *args, **kwargs):
            return _Resp()

        def get(self, *args, **kwargs):
            raise AssertionError("Telegram delete path should not query extra rows when disabled")

    calls = {"delete": 0}
    monkeypatch.setattr(mod, "load_config_from_env", lambda: supa_cfg)
    monkeypatch.setattr(mod, "load_aggregator_config", lambda: agg_cfg)
    monkeypatch.setattr(mod, "SupabaseRestClient", _Client)
    monkeypatch.setattr(
        mod,
        "delete_expired_broadcast_messages",
        lambda **kwargs: calls.__setitem__("delete", calls["delete"] + 1),
    )

    res = mod.update_tiers(expire_action="expired", delete_expired_telegram=True)

    assert calls["delete"] == 0
    assert res["telegram_delete"]["skipped"] is True
    assert res["telegram_delete"]["reason"] == "freshness_delete_expired_telegram_disabled"
    assert res["telegram_propagation"]["skipped"] is True
    assert res["telegram_propagation"]["reason"] == "freshness_propagate_telegram_disabled"
