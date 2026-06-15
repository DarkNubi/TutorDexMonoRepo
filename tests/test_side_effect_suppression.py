import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _ensure_aggregator_sys_path() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    agg_dir = repo_root / "TutorDexAggregator"
    agg_path = str(agg_dir)
    if agg_path in sys.path:
        sys.path.remove(agg_path)
    sys.path.insert(0, agg_path)


def test_side_effects_suppressed_for_requeued_extractions():
    _ensure_aggregator_sys_path()
    from workers.side_effects import side_effect_suppression_reason

    reason = side_effect_suppression_reason(
        {"date": datetime.now(timezone.utc).isoformat()},
        {"requeue_reason": "online_location_validation_fix_raw_text"},
    )

    assert reason == "requeued_extraction"


def test_side_effects_suppressed_for_historical_source_messages():
    _ensure_aggregator_sys_path()
    from workers.side_effects import side_effect_suppression_reason

    old_date = datetime.now(timezone.utc) - timedelta(hours=25)

    assert side_effect_suppression_reason({"date": old_date.isoformat()}, {}) == "historical_source_message"


def test_side_effects_allowed_for_fresh_source_messages():
    _ensure_aggregator_sys_path()
    from workers.side_effects import side_effect_suppression_reason

    fresh_date = datetime.now(timezone.utc) - timedelta(minutes=10)

    assert side_effect_suppression_reason({"date": fresh_date.isoformat()}, {}) is None
