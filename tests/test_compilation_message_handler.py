"""
Tests for compilation-message handler (LLM identifier verification + splitting).
"""

from TutorDexAggregator.compilation_message_handler import (
    confirm_compilation_identifiers,
    normalize_identifier,
    order_verified_identifiers,
    split_compilation_message,
    verify_identifiers,
)


def test_normalize_identifier_colon_tail():
    assert normalize_identifier("Assignment Code: 1234") == "1234"
    assert normalize_identifier("Job ID: ABC123") == "ABC123"


def test_normalize_identifier_brackets():
    assert normalize_identifier("[Job 7782]") == "Job 7782"


def test_verify_identifiers_requires_verbatim_and_boundaries():
    raw = "Postal: 642196\nJob ID: ABC123\n"
    res = verify_identifiers(raw_message=raw, candidates=["ABC123", "4219", "XYZ999"])
    assert res["verified"] == ["ABC123"]
    dropped = {d["code"]: d["reason"] for d in res["dropped"]}
    assert dropped["4219"] == "not_verbatim_in_message"
    assert dropped["XYZ999"] == "not_verbatim_in_message"


def test_split_compilation_message_by_verified_identifiers():
    raw = (
        "Here are the jobs\n\n"
        "Job ID: ABC123\n"
        "Subject: P5 Math\n\n"
        "Job ID: XYZ789\n"
        "Subject: Sec 2 English\n"
    )
    verified = ["Job ID: ABC123", "Job ID: XYZ789"]
    ordered = order_verified_identifiers(raw_message=raw, verified=verified)
    segments = split_compilation_message(raw_message=raw, identifiers=ordered)
    assert len(segments) == 2
    assert segments[0]["identifier_normalized"] == "ABC123"
    assert "ABC123" in segments[0]["text"]
    assert "XYZ789" not in segments[0]["text"]
    assert segments[1]["identifier_normalized"] == "XYZ789"
    assert "XYZ789" in segments[1]["text"]


def test_confirm_compilation_identifiers_verifies_and_confirms(monkeypatch):
    raw = "Job ID: ABC123\n...\nJob ID: XYZ789\n..."

    def _fake_chat_completion(*args, **kwargs) -> str:
        return '{"assignment_codes":[{"code":"Job ID: ABC123"},{"code":"Job ID: XYZ789"}]}'

    # Patch the imported symbol used by compilation_message_handler.
    import TutorDexAggregator.compilation_message_handler as mod

    monkeypatch.setattr(mod, "chat_completion", _fake_chat_completion)
    out = confirm_compilation_identifiers(raw_message=raw, cid="c1", channel="t.me/x")
    assert out["confirmed"] is True
    assert out["verified"] == ["Job ID: ABC123", "Job ID: XYZ789"]


def test_confirm_compilation_identifiers_downgrades_when_less_than_two_verified(monkeypatch):
    raw = "Job ID: ABC123\n..."

    def _fake_chat_completion(*args, **kwargs) -> str:
        # Hallucinated second id that does not exist in the raw message.
        return '{"assignment_codes":[{"code":"Job ID: ABC123"},{"code":"Job ID: NOPE999"}]}'

    import TutorDexAggregator.compilation_message_handler as mod

    monkeypatch.setattr(mod, "chat_completion", _fake_chat_completion)
    out = confirm_compilation_identifiers(raw_message=raw, cid="c1", channel="t.me/x")
    assert out["confirmed"] is False
    assert out["verified"] == ["Job ID: ABC123"]

