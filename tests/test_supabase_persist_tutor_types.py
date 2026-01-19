

def test_sanitize_example():
    # We will import via executing a small wrapper since the helper is nested; instead test end-to-end build row
    from TutorDexAggregator.supabase_persist import _build_assignment_row

    parsed = {
        "tutor_types": [{"canonical": "part-timer", "original": "PT", "confidence": "0.85"}],
        "rate_breakdown": {"part-timer": {"min": "20", "max": 30.0, "original_text": "$20-30/hr", "confidence": "0.8"}},
    }
    payload = {"parsed": parsed, "raw_text": "FT $40-55/hr, PT $20-30/hr",
               "channel_link": "t.me/example", "date": "2026-01-01T00:00:00Z", "channel_title": "Example"}
    row = _build_assignment_row(payload)
    assert "tutor_types" in row
    assert isinstance(row["tutor_types"], list)
    assert row["tutor_types"][0]["canonical"] == "part-timer"
    assert "rate_breakdown" in row
    assert isinstance(row["rate_breakdown"], dict)
    assert row["rate_breakdown"]["part-timer"]["min"] == 20
    assert row["rate_breakdown"]["part-timer"]["max"] == 30
