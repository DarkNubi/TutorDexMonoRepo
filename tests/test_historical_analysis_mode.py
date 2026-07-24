from types import SimpleNamespace

from test_extract_worker_orchestration import _ensure_aggregator_sys_path


def _toggles(*, materialize_assignments: bool):
    return SimpleNamespace(
        materialize_assignments=materialize_assignments,
        enable_broadcast=False,
        enable_dms=False,
        max_attempts=3,
        use_normalized_text_for_llm=False,
    )


def test_analysis_only_marks_extraction_ok_without_materializing_assignment(monkeypatch):
    _ensure_aggregator_sys_path()
    import importlib

    module = importlib.import_module("workers.extract_worker_standard_persist")
    captured = {}

    def fake_mark_extraction(*args, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(module, "mark_extraction", fake_mark_extraction)

    result = module.persist_and_finalize(
        cfg=SimpleNamespace(),
        logger=SimpleNamespace(),
        version=SimpleNamespace(pipeline_version="historical-v1", schema_version="v1"),
        toggles=_toggles(materialize_assignments=False),
        url="https://supabase.invalid",
        key="redacted-test-key",
        extraction_id=123,
        existing_meta={},
        attempt=0,
        llm_model="test-model",
        channel_link="t.me/example",
        raw={"message_id": "42"},
        payload={"parsed": {"assignment_code": "A-42"}},
        with_prompt=lambda value: value,
        norm_meta={},
        postal_estimated_meta={},
        time_meta={},
        hard_meta={},
        signals_meta={},
        broadcast_assignments=None,
        send_dms=None,
    )

    assert result == "ok"
    assert captured["status"] == "ok"
    assert captured["canonical_json"] == {"assignment_code": "A-42"}
    assert captured["meta_patch"]["persist"]["action"] == "analysis_only"
