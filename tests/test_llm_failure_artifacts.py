import sys
from pathlib import Path
from typing import Any


def _ensure_aggregator_sys_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    agg_dir = repo_root / "TutorDexAggregator"
    agg_path = str(agg_dir)
    if agg_path in sys.path:
        sys.path.remove(agg_path)
    sys.path.insert(0, agg_path)
    sys.modules.pop("logging_setup", None)
    sys.modules.pop("extract_key_info", None)


class _StructuredLLMError(RuntimeError):
    error_type = "llm_invalid_json"

    def __init__(self) -> None:
        super().__init__("bad json")
        self.details = {
            "model_output": {
                "chars": 11,
                "sha256": "abc",
                "snippet": "{bad json}",
                "truncated": False,
            }
        }


def test_extract_with_llm_returns_structured_error_payload(monkeypatch):
    _ensure_aggregator_sys_path()
    from workers import llm_processor

    monkeypatch.setenv("LLM_MODEL_NAME", "test-model")

    def _extract_func(*args: Any, **kwargs: Any) -> dict:
        raise _StructuredLLMError()

    parsed, error_type, latency, payload = llm_processor.extract_with_llm(
        "raw text",
        "t.me/test",
        cid="cid",
        circuit_breaker=None,
        extract_func=_extract_func,
        metrics=None,
    )

    assert parsed is None
    assert error_type == "llm_invalid_json"
    assert latency >= 0
    assert payload is not None
    assert payload["error"] == "llm_invalid_json"
    assert payload["message"] == "bad json"
    assert payload["details"]["model_output"]["snippet"] == "{bad json}"


def test_extract_preferred_json_object_prefers_after_think():
    _ensure_aggregator_sys_path()
    from extract_key_info import extract_preferred_json_object

    text = """
<think>
The model considered {"wrong": true} while reasoning.
</think>
{"assignment_code": "0706pe", "rate": {"min": 40, "max": 55}}
"""

    assert extract_preferred_json_object(text) == '{"assignment_code": "0706pe", "rate": {"min": 40, "max": 55}}'


def test_extract_preferred_json_object_prefers_last_balanced_json_without_closed_think():
    _ensure_aggregator_sys_path()
    from extract_key_info import extract_preferred_json_object

    text = """
<think>
The model considered {"wrong": true} while reasoning but forgot to close the tag.
Final answer:
{"assignment_code": "0606ep", "academic_display_text": "Sec 1 G3 Science"}
"""

    assert extract_preferred_json_object(text) == '{"assignment_code": "0606ep", "academic_display_text": "Sec 1 G3 Science"}'


def test_fill_lesson_schedule_from_frequency_line():
    _ensure_aggregator_sys_path()
    from workers.enrichment_pipeline import fill_lesson_schedule_from_text

    parsed, meta = fill_lesson_schedule_from_text(
        {"assignment_code": "0706p", "lesson_schedule": None},
        "Code ID: 0706p\nFrequency: 1.5 Hr, 1x A Week\nRate: $45-65/Hr",
    )

    assert parsed["lesson_schedule"] == ["1.5 Hr, 1x A Week"]
    assert meta["changed"] is True
    assert meta["source"] == "explicit_frequency_line"


def test_fill_learning_mode_from_location_area_online():
    _ensure_aggregator_sys_path()
    from workers.enrichment_pipeline import fill_learning_mode_from_text

    parsed, meta = fill_learning_mode_from_text(
        {"assignment_code": "NT29838"},
        "Looking for Online Tutor\n🔻 Location/Area: Online Tuition\nLesson Per Week: Once a week",
    )

    assert parsed["learning_mode"]["mode"] == "Online"
    assert meta["changed"] is True


def test_fill_address_from_location_area_line_skips_online():
    _ensure_aggregator_sys_path()
    from workers.enrichment_pipeline import fill_address_from_text

    parsed, meta = fill_address_from_text(
        {"assignment_code": "NT29838"},
        "🔻 Location/Area: Lorong Lew Lian\nRate: $45/hr",
    )

    assert parsed["address"] == ["Lorong Lew Lian"]
    assert meta["source"] == "explicit_address_line"

    online_parsed, online_meta = fill_address_from_text(
        {"assignment_code": "NT29838"},
        "🔻 Location/Area: Online Tuition\nRate: $45/hr",
    )

    assert online_parsed.get("address") is None
    assert online_meta["changed"] is False


def test_compact_tuition_assignment_lines_fill_schedule_and_address():
    _ensure_aggregator_sys_path()
    from workers.enrichment_pipeline import fill_address_from_text, fill_lesson_schedule_from_text

    text = """0706si: N1 Abacus @ 414 Jurong West Street 42 (S)640414
1.5 Hrs, 1-2x A Week; $55-70/Hr
"""

    parsed, schedule_meta = fill_lesson_schedule_from_text({"assignment_code": "0706si"}, text)
    parsed, address_meta = fill_address_from_text(parsed, text)

    assert parsed["lesson_schedule"] == ["1.5 Hrs, 1-2x A Week"]
    assert parsed["address"] == ["414 Jurong West Street 42 (S)640414"]
    assert schedule_meta["changed"] is True
    assert address_meta["changed"] is True
