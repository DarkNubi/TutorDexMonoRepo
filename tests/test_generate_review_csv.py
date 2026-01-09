from scripts.generate_review_csv import make_rows


def test_make_rows_low_confidence():
    obj = {
        "external_id": "id1",
        "tutor_types": [{"canonical": "part-timer", "original": "PT", "confidence": 0.5}],
        "rate_breakdown": {"part-timer": {"min": 20, "max": 30, "original_text": "$20-30/hr"}},
    }
    rows = make_rows(obj, 0.6)
    assert isinstance(rows, list)
    assert len(rows) == 1
    r = rows[0]
    assert r["external_id"] == "id1"
    assert r["canonical"] == "part-timer"
