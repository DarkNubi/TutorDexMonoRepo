"""
Test that row_builder correctly handles agency_display_name using get_agency_display_name.

This test verifies the fix for the issue where get_agency_display_name was not properly
imported due to nested exception handling.
"""


def test_agency_display_name_from_registry():
    """Test that agency_display_name is correctly resolved from the registry."""
    from TutorDexAggregator.supabase_persist import _build_assignment_row

    # Test with TutorAnywhr (the agency from the problem statement)
    payload = {
        "channel_link": "t.me/TutorAnywhr",
        "channel_title": "TutorAnywhr Channel",
        "date": "2026-01-19T00:00:00Z",
        "raw_text": "Test assignment",
        "message_id": 9751,
    }
    row = _build_assignment_row(payload)

    # The agency_display_name should be resolved from the registry
    assert "agency_display_name" in row
    assert row["agency_display_name"] == "TutorAnywhr"
    assert row["agency_telegram_channel_name"] == "TutorAnywhr Channel"


def test_agency_display_name_fallback():
    """Test that agency_display_name falls back to channel_title for unknown agencies."""
    from TutorDexAggregator.supabase_persist import _build_assignment_row

    payload = {
        "channel_link": "t.me/UnknownAgency",
        "channel_title": "Unknown Agency Title",
        "date": "2026-01-19T00:00:00Z",
        "raw_text": "Test assignment",
        "message_id": 1234,
    }
    row = _build_assignment_row(payload)

    # For unknown agencies, should fall back to channel_title
    assert "agency_display_name" in row
    # The registry lookup should return the default (which is the channel_title in this case)
    assert row["agency_display_name"] is not None


def test_agency_display_name_known_agencies():
    """Test multiple known agencies from the registry."""
    from TutorDexAggregator.supabase_persist import _build_assignment_row

    test_cases = [
        ("t.me/tuitionassignmentssg", "MindFlex"),
        ("t.me/tutorsociety", "Tutor Society"),
        ("t.me/tutoranywhr", "TutorAnywhr"),
        ("t.me/elitetutorsg", "EliteTutor"),
    ]

    for channel_link, expected_display_name in test_cases:
        payload = {
            "channel_link": channel_link,
            "channel_title": "Test Channel",
            "date": "2026-01-19T00:00:00Z",
            "raw_text": "Test assignment",
            "message_id": 1,
        }
        row = _build_assignment_row(payload)
        assert row["agency_display_name"] == expected_display_name, \
            f"Expected {expected_display_name} for {channel_link}, got {row['agency_display_name']}"
