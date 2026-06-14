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
