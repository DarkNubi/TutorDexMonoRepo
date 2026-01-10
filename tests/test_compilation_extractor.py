"""
Tests for compilation code extraction.
"""

import pytest
from TutorDexAggregator.compilation_extractor import (
    extract_assignment_codes,
    should_process_compilation,
)


class TestExtractAssignmentCodes:
    """Test extraction of assignment codes from compilation messages."""

    def test_extract_job_id_format(self):
        text = """
Job ID: ABC123
Job ID: XYZ789
Job ID: DEF456
        """
        codes, meta = extract_assignment_codes(text)
        assert len(codes) == 3
        assert "ABC123" in codes
        assert "XYZ789" in codes
        assert "DEF456" in codes
        assert meta["ok"] is True
        assert meta["codes_count"] == 3

    def test_extract_assignment_code_format(self):
        text = """
Assignment Code: NT29838
Assignment Code: FT12345
        """
        codes, meta = extract_assignment_codes(text)
        assert len(codes) == 2
        assert "NT29838" in codes
        assert "FT12345" in codes

    def test_deduplication(self):
        # Same code appears multiple times
        text = """
Job ID: ABC123
Job ID: XYZ789
Job ID: ABC123
        """
        codes, meta = extract_assignment_codes(text)
        assert len(codes) == 2  # De-duplicated
        assert codes == ["ABC123", "XYZ789"]
        assert meta["total_matches"] >= 3  # Records all matches (may be more due to multiple patterns)

    def test_mixed_formats(self):
        text = """
Job ID: ABC123
Assignment Code: XYZ789
Code: DEF456
        """
        codes, meta = extract_assignment_codes(text)
        assert len(codes) >= 2  # At least the obvious ones

    def test_case_insensitive(self):
        text = """
job id: abc123
JOB ID: xyz789
        """
        codes, meta = extract_assignment_codes(text)
        assert "ABC123" in codes  # Normalized to uppercase
        assert "XYZ789" in codes

    def test_empty_text(self):
        codes, meta = extract_assignment_codes("")
        assert codes == []
        assert meta["ok"] is False

    def test_no_codes(self):
        text = "This is just a regular message with no codes."
        codes, meta = extract_assignment_codes(text)
        assert codes == []
        assert meta["ok"] is True

    def test_filters_short_codes(self):
        # Very short codes are likely false positives
        text = "Job ID: AB"  # Only 2 chars
        codes, meta = extract_assignment_codes(text)
        assert len(codes) == 0

    def test_filters_pure_numeric(self):
        # Pure numeric codes are likely not assignment codes
        text = "ID: 12345"
        codes, meta = extract_assignment_codes(text)
        # Should be filtered out as it's pure numeric
        assert "12345" not in codes

    def test_real_compilation_example(self):
        # Based on actual compilation from the issue
        text = """
🔥 Calling All Tutors!

There are many Tuition job opportunities. Apply now!

✅ Primary 5 English @ Kingsford Waterbay - Job ID: NT29838
✅ Primary 3 English @ Chai Chee - Assignment Code: FT12345
✅ Primary 6 English @ Jurong West - Code: SG99999
        """
        codes, meta = extract_assignment_codes(text)
        assert len(codes) >= 2  # Should find at least a couple
        assert meta["ok"] is True


class TestShouldProcessCompilation:
    """Test logic for determining if compilation should be processed."""

    def test_with_codes(self):
        codes = ["ABC123", "XYZ789"]
        assert should_process_compilation(codes) is True

    def test_single_code(self):
        codes = ["ABC123"]
        assert should_process_compilation(codes, min_codes=1) is True

    def test_no_codes(self):
        codes = []
        assert should_process_compilation(codes) is False

    def test_custom_threshold(self):
        codes = ["ABC123", "XYZ789"]
        assert should_process_compilation(codes, min_codes=3) is False
        assert should_process_compilation(codes, min_codes=2) is True
