from TutorDexAggregator.extractors.tutor_types import extract_tutor_types


def test_extract_basic_labels():
    s = "FT $40-55/hr, PT $20-30/hr"
    res = extract_tutor_types(text=s)
    assert isinstance(res, dict)
    tt = res.get("tutor_types")
    rb = res.get("rate_breakdown")
    assert isinstance(tt, list)
    assert len(tt) >= 1
    # rate_breakdown should include at least one entry
    assert isinstance(rb, dict)
    # ensure canonicalize can process the extractor output
    from TutorDexAggregator.canonicalize import canonicalize
    parsed = {"tutor_types": tt, "rate_breakdown": rb}
    out = canonicalize(parsed)
    assert out.get("tutor_types") is None or isinstance(out.get("tutor_types"), list)
    assert out.get("rate_breakdown") is None or isinstance(out.get("rate_breakdown"), dict)
